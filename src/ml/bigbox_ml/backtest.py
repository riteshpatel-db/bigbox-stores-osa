"""Replay held-out weeks of true demand under a replenishment policy.

The world is the generator's own simulation. `capture()` re-runs the unmodified
`bigbox_gen.simulate.simulate()` with the generator's seeding; its random stream is separate from
defect injection, so it reproduces the published history exactly. It keeps the hourly true demand
of the replay window and reconstructs the exact state on the evening before it: on hand by age
(sales, expiry and damage are first-in-first-out, so the stock left is the newest receipts), the
purchase orders in flight with what the supplier actually delivered, and the incumbent's 28-day
sales history.

`replay()` then trades that same demand hour by hour under any policy, with the generator's
mechanics: perishables age and expire, damage, case packs, short and late supply. Supply and damage
draws come from streams seeded by day, so every policy faces the same supplier behaviour.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from bigbox_gen.config import Calendar
from bigbox_gen.masters import Masters, build_masters
from bigbox_gen.simulate import simulate, take_fifo

from .policy import Policy, levels, order_quantity

METRICS = [
    "cell_days",
    "trading_hours",
    "stockout_hours",
    "in_stock_at_close",
    "demand_units",
    "sold_units",
    "lost_units",
    "lost_sales",
    "lost_margin",
    "received_units",
    "expired_units",
    "damaged_units",
    "waste_cost",
    "closing_units",
    "closing_cost",
    "sold_cost",
    "order_lines",
]


def world(cfg: dict) -> tuple[Calendar, Masters, np.random.Generator]:
    """Calendar, masters and simulation stream, seeded exactly as bigbox_gen.run.generate()."""
    seeds = np.random.SeedSequence(cfg["seed"]).spawn(3)
    rng_masters, rng_sim = (np.random.default_rng(s) for s in seeds[:2])
    cal = Calendar.from_config(cfg)
    return cal, build_masters(cfg, cal, rng_masters), rng_sim


@dataclass
class Start:
    day: int  # first replayed day (simulation day index)
    inv: np.ndarray  # (C, W) units on hand by age in days at the close of day - 1
    on_order: np.ndarray  # (C,) units ordered and not yet received
    arrivals: dict[
        int, list[tuple[np.ndarray, np.ndarray, np.ndarray]]
    ]  # day: (cell, recv, ordered)
    sales_ring: np.ndarray  # (C, ma_days) observed units sold, slot d % ma_days


@dataclass
class Capture:
    start: Start
    dem_store: np.ndarray  # (D, C, H) true in-store demand, int32
    dem_online: np.ndarray  # (D, C, H) true online demand, int32
    active: np.ndarray  # (D, C) ranged and launched
    history: list[np.ndarray] = field(default_factory=list)  # per day (groups, METRICS)


@dataclass
class Cells:
    """Per-cell constants the replay and the metrics need."""

    lead: np.ndarray
    case: np.ndarray
    shelf: np.ndarray
    perishable: np.ndarray
    price: np.ndarray
    cost: np.ndarray
    damage_rate: np.ndarray
    active_from: np.ndarray
    group: np.ndarray  # metric group per cell
    n_groups: int

    @classmethod
    def of(cls, cfg: dict, m: Masters, group: np.ndarray, n_groups: int) -> Cells:
        sku = m.cell_sku
        cats = cfg["products"]["categories"]
        return cls(
            lead=m.sku_lead_time[sku].astype(np.int64),
            case=m.sku_case_pack[sku].astype(np.int64),
            shelf=m.sku_shelf_life[sku].astype(np.int64),
            perishable=m.sku_perishable[sku].astype(bool),
            price=m.sku_price[sku].astype(float),
            cost=m.sku_cost[sku].astype(float),
            damage_rate=np.array([c["damage_rate"] for c in cats])[m.sku_category[sku]],
            active_from=m.cell_active_from,
            group=group,
            n_groups=n_groups,
        )


def day_metrics(
    c: Cells,
    active: np.ndarray,
    dem_store: np.ndarray,
    dem_online: np.ndarray,
    sold: np.ndarray,
    shipped: np.ndarray,
    on_hand: np.ndarray,
    expired: np.ndarray,
    damaged: np.ndarray,
    received: np.ndarray,
    order_lines: np.ndarray,
) -> np.ndarray:
    """(n_groups, len(METRICS)) sums over the active cells of one day."""
    a = active.astype(float)
    demand = dem_store.sum(axis=1) + dem_online.sum(axis=1)
    units = sold.sum(axis=1) + shipped.sum(axis=1)
    lost = demand - units
    closing = on_hand[:, -1]
    waste = (expired + damaged) * c.cost
    per_cell = {
        "cell_days": a,
        "trading_hours": a * on_hand.shape[1],
        "stockout_hours": (on_hand == 0).sum(axis=1),
        "in_stock_at_close": closing > 0,
        "demand_units": demand,
        "sold_units": units,
        "lost_units": lost,
        "lost_sales": lost * c.price,
        "lost_margin": lost * (c.price - c.cost),
        "received_units": received,
        "expired_units": expired,
        "damaged_units": damaged,
        "waste_cost": waste,
        "closing_units": closing,
        "closing_cost": closing * c.cost,
        "sold_cost": units * c.cost,
        "order_lines": order_lines,
    }
    out = np.zeros((c.n_groups, len(METRICS)))
    for j, name in enumerate(METRICS):
        out[:, j] = np.bincount(
            c.group, weights=np.asarray(per_cell[name], dtype=float) * a, minlength=c.n_groups
        )
    return out


def capture(cfg: dict, c: Cells, first: int, last: int, log=print) -> Capture:
    """Re-run the generator's simulation to `last` and keep what the replay of first..last needs."""
    cal, m, rng = world(cfg)
    n, hours = m.n_cells, cal.hours
    width = max(int(m.sku_shelf_life.max()), 1)
    ma = cfg["incumbent_policy"]["ma_days"]
    ring = np.zeros((n, ma))
    receipts: dict[int, np.ndarray] = {}  # day: units received per cell (last `width` days)
    po_qty: dict[int, dict[int, int]] = {}  # order day: {po_line: ordered qty}, recent days only
    keep_days = int(m.sku_lead_time.max()) + cfg["supply"]["late_days"][1] + 1
    arrivals: dict[int, list] = {}
    days = last - first + 1
    dem_s = np.zeros((days, n, hours), dtype=np.int32)
    dem_o = np.zeros_like(dem_s)
    active = np.zeros((days, n), dtype=bool)
    close = None
    history = []
    for r in simulate(cfg, cal, m, rng):
        d = r.day
        if d < first:
            ring[:, d % ma] = r.sold.sum(axis=1) + r.shipped.sum(axis=1)
            receipts[d] = np.bincount(r.rcv_cell, weights=r.rcv_qty, minlength=n)
            receipts.pop(d - width, None)
            po_qty[d] = dict(
                zip((d * 100_000 + r.po_cell).tolist(), r.po_qty.tolist(), strict=True)
            )
            po_qty.pop(d - keep_days, None)
            if d == first - 1:
                close = r.on_hand[:, -1].astype(np.int64)
            continue
        i = d - first
        dem_s[i], dem_o[i], active[i] = r.dem_store, r.dem_online, r.active
        inflight = r.rcv_order_day < first
        if inflight.any():
            ordered = np.array(
                [po_qty[int(x) // 100_000][int(x)] for x in r.rcv_po_line[inflight]], dtype=np.int64
            )
            arrivals.setdefault(d, []).append((r.rcv_cell[inflight], r.rcv_qty[inflight], ordered))
        received = np.bincount(r.rcv_cell, weights=r.rcv_qty, minlength=n)
        history.append(
            day_metrics(
                c,
                r.active,
                r.dem_store,
                r.dem_online,
                r.sold,
                r.shipped,
                r.on_hand,
                r.expired,
                r.damaged,
                received,
                np.bincount(r.po_cell, minlength=n),
            )
        )
        if d == last:
            break
    if close is None:
        raise ValueError("first day must be after the simulation start")

    inv = np.zeros((n, width), dtype=np.int64)
    perish = c.perishable
    inv[~perish, 0] = close[~perish]
    left = np.where(perish, close, 0)
    for k in range(width):  # newest receipts first: FIFO leaves the newest stock
        got = receipts.get(first - 1 - k)
        if got is None:
            break
        take = np.minimum(got.astype(np.int64), left)
        inv[:, k] += np.where(perish, take, 0)
        left -= take
    if left.any():
        raise RuntimeError(f"{int((left > 0).sum())} perishable cells not explained by receipts")
    on_order = np.zeros(n, dtype=np.int64)
    for lst in arrivals.values():
        for cell, _, ordered in lst:
            np.add.at(on_order, cell, ordered)
    log(f"captured days {cal.date(first)} .. {cal.date(last)}: {n} cells")
    return Capture(
        start=Start(first, inv, on_order, arrivals, ring),
        dem_store=dem_s,
        dem_online=dem_o,
        active=active,
        history=history,
    )


OrderRule = Callable[[int, int, np.ndarray, np.ndarray, np.ndarray], np.ndarray]


class Incumbent:
    """The generator's nightly rule: 28-day moving average of observed sales, fixed safety days."""

    def __init__(self, cfg: dict, c: Cells, ring: np.ndarray):
        pol = cfg["incumbent_policy"]
        self.c, self.ring = c, ring.copy()
        self.ma, self.review, self.safety = pol["ma_days"], pol["review_days"], pol["safety_days"]
        self.min_stock = c.case * pol["min_presentation_cases"]

    def __call__(self, d, i, on_hand, on_order, sold_today):
        self.ring[:, d % self.ma] = sold_today
        f = self.ring.mean(axis=1)
        c = self.c
        rop = np.maximum(f * (c.lead + self.safety), self.min_stock)
        out = np.maximum(f * (c.lead + self.review + self.safety), self.min_stock)
        pos = on_hand + on_order
        return np.where(pos < rop, np.ceil((out - pos) / c.case) * c.case, 0).astype(np.int64)


class ForecastPolicy:
    """Policy (b): the ML forecast for the next days, variability-based safety stock."""

    def __init__(self, c: Cells, forecasts: np.ndarray, sigma: np.ndarray, p: Policy):
        self.c, self.f, self.sigma, self.p = c, forecasts, sigma, p

    def __call__(self, d, i, on_hand, on_order, sold_today):
        c = self.c
        rop, out = levels(
            self.f[i].astype(float), c.lead, c.shelf, c.perishable, self.sigma[i], c.case, self.p
        )
        return order_quantity(on_hand + on_order, rop, out, c.case)


def replay(cfg: dict, c: Cells, cap: Capture, rule: OrderRule, seed: int) -> list[np.ndarray]:
    """Trade the captured demand under `rule`; returns per-day (groups, METRICS) arrays."""
    sup = cfg["supply"]
    s = cap.start
    n = len(c.lead)
    inv = s.inv.copy()
    on_hand = inv.sum(axis=1)
    on_order = s.on_order.copy()
    arrivals = copy.deepcopy(s.arrivals)
    perish = np.flatnonzero(c.perishable)
    sl = c.shelf[perish]
    out = []
    for i in range(cap.dem_store.shape[0]):
        d = s.day + i
        expired = np.zeros(n, dtype=np.int64)
        if perish.size:
            expired[perish] = inv[perish, sl - 1]
            inv[perish, sl - 1] = 0
            inv[perish, 1:] = inv[perish, :-1]
            inv[perish, 0] = 0
        on_hand -= expired

        damaged = np.random.default_rng([seed, 1, d]).binomial(on_hand, c.damage_rate)
        take_fifo(inv, damaged)
        on_hand -= damaged

        received = np.zeros(n, dtype=np.int64)
        for cell, recv, ordered in arrivals.pop(d, []):
            np.add.at(inv[:, 0], cell, recv)
            np.add.at(on_hand, cell, recv)
            np.add.at(received, cell, recv)
            np.add.at(on_order, cell, -ordered)

        dem_s = cap.dem_store[i].astype(np.int64)
        dem_o = cap.dem_online[i].astype(np.int64)
        hours = dem_s.shape[1]
        sold = np.zeros((n, hours), dtype=np.int64)
        shipped = np.zeros_like(sold)
        snap = np.zeros_like(sold)
        for h in range(hours):
            x = np.minimum(dem_s[:, h], on_hand)
            take_fifo(inv, x)
            on_hand -= x
            o = np.minimum(dem_o[:, h], on_hand)
            take_fifo(inv, o)
            on_hand -= o
            sold[:, h], shipped[:, h], snap[:, h] = x, o, on_hand

        qty = rule(d, i, on_hand, on_order, sold.sum(axis=1) + shipped.sum(axis=1))
        qty = np.where(c.active_from <= d + 1, qty, 0)
        rs = np.random.default_rng([seed, 2, d])
        full = rs.random(n) < sup["full_fill_prob"]
        frac = rs.uniform(*sup["short_fill"], n)
        late = np.where(
            rs.random(n) < sup["late_prob"],
            rs.integers(sup["late_days"][0], sup["late_days"][1] + 1, n),
            0,
        )
        recv = np.where(full, qty, np.floor(qty / c.case * frac).astype(np.int64) * c.case)
        cells = np.flatnonzero(qty)
        arrival = d + c.lead[cells] + late[cells]
        for a in np.unique(arrival):
            sel = cells[arrival == a]
            arrivals.setdefault(int(a), []).append((sel, recv[sel], qty[sel]))
        on_order += qty
        out.append(
            day_metrics(
                c,
                cap.active[i],
                dem_s,
                dem_o,
                sold,
                shipped,
                snap,
                expired,
                damaged,
                received,
                (qty > 0).astype(float),
            )
        )
    return out
