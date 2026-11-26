"""Hour-by-hour simulation of demand, sales and inventory under the incumbent replenishment policy.

Every store x SKU cell is simulated at once with numpy vectors. Sales are min(demand, on_hand), so
demand is censored whenever the shelf is empty; the ground truth keeps the uncensored demand.
Perishable stock is tracked by age (one bucket per day) and sold first-in-first-out, so expiry
and waste emerge from the ordering policy instead of being painted on.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from .config import Calendar
from .masters import Masters


@dataclass
class DayResult:
    day: int
    active: np.ndarray  # (C,) bool: ranged and launched
    expected: np.ndarray  # (C,) expected demand units (no noise)
    discount: np.ndarray  # (C,) promo discount in force
    dem_store: np.ndarray  # (C, H) true in-store demand
    dem_online: np.ndarray  # (C, H) true online demand (= requested units)
    sold: np.ndarray  # (C, H) in-store units sold
    shipped: np.ndarray  # (C, H) online units shipped
    on_hand: np.ndarray  # (C, H) on hand at the end of each trading hour
    expired: np.ndarray  # (C,)
    damaged: np.ndarray  # (C,)
    rcv_cell: np.ndarray  # receipts arriving this morning
    rcv_qty: np.ndarray
    rcv_po_line: np.ndarray
    rcv_order_day: np.ndarray
    po_cell: np.ndarray  # replenishment orders raised tonight
    po_qty: np.ndarray
    po_due_day: np.ndarray
    po_arrival_day: np.ndarray  # due day + supplier lateness


def calendar_factors(cfg: dict, cal: Calendar, m: Masters) -> np.ndarray:
    """(n_days, n_categories) multiplier: day of week x annual seasonality x holidays."""
    dc = cfg["demand"]
    cats = cfg["products"]["categories"]
    days = [cal.date(i) for i in range(cal.n_days)]
    dow = np.array([dc["dow"][d.weekday()] for d in days])
    doy = np.array([d.timetuple().tm_yday for d in days])
    peak = np.array([(c["peak_month"] - 1) * 30.4 + 15 for c in cats])
    amp = np.array([c["season_amp"] for c in cats])
    season = 1 + amp[None, :] * np.cos(2 * np.pi * (doy[:, None] - peak[None, :]) / 365.25)
    hol = np.ones((cal.n_days, len(cats)))
    names = m.category_names
    for h in dc["holidays"]:
        cols = [names.index(c) for c in h["categories"]] if h["categories"] else range(len(names))
        lo, hi = max(cal.index(h["start"]), 0), min(cal.index(h["end"]), cal.last_day)
        if hi < lo:  # holiday outside the simulated calendar
            continue
        for c in cols:
            hol[lo : hi + 1, c] *= h["mult"]
    return dow[:, None] * season * hol


def take_fifo(inv: np.ndarray, qty: np.ndarray) -> None:
    """Remove qty units per cell from the age buckets, oldest first (in place)."""
    q = qty.astype(inv.dtype, copy=True)
    for k in range(inv.shape[1] - 1, -1, -1):
        t = np.minimum(q, inv[:, k])
        inv[:, k] -= t
        q -= t


def simulate(cfg: dict, cal: Calendar, m: Masters, rng: np.random.Generator) -> Iterator[DayResult]:
    pol, sup, dc = cfg["incumbent_policy"], cfg["supply"], cfg["demand"]
    cats = cfg["products"]["categories"]
    n_cells, n_hours = m.n_cells, cal.hours
    sku = m.cell_sku
    cat = m.sku_category[sku]
    case = m.sku_case_pack[sku].astype(np.int64)
    lead = m.sku_lead_time[sku].astype(np.int64)
    shelf = m.sku_shelf_life[sku]
    perish = np.flatnonzero(m.sku_perishable[sku])
    online_share = np.array([c["online_share"] for c in cats])[cat]
    damage_rate = np.array([c["damage_rate"] for c in cats])[cat]
    profile = np.array(dc["hour_profile"], dtype=float)
    profile /= profile.sum()
    factors = calendar_factors(cfg, cal, m)
    region = m.store_region[m.cell_store]
    promo_masks = [
        np.isin(sku, s) & np.isin(region, r)
        for s, r in zip(m.promo_skus, m.promo_regions, strict=True)
    ]
    width = max(int(shelf.max()), 1)
    review, safety, ma_days = pol["review_days"], pol["safety_days"], pol["ma_days"]
    min_stock = case * pol["min_presentation_cases"]

    # steady-state start: forecast = base rate, stock = order-up-to level
    base = m.cell_base_rate
    ring = np.tile(base[:, None], (1, ma_days))
    active0 = m.cell_active_from <= 0
    init = np.ceil(base * (lead + review + safety) / case) * case * active0
    inv = np.zeros((n_cells, width), dtype=np.int64)
    inv[:, 0] = init.astype(np.int64)
    on_hand = inv.sum(axis=1)
    on_order = np.zeros(n_cells, dtype=np.int64)
    arrivals: dict[int, list[tuple[np.ndarray, ...]]] = {}
    empty_i = np.zeros(0, dtype=np.int64)

    for d in range(cal.n_days):
        active = m.cell_active_from <= d

        # 1. overnight: perishables age one day; stock reaching its shelf life expires
        expired = np.zeros(n_cells, dtype=np.int64)
        if perish.size:
            sl = shelf[perish]
            expired[perish] = inv[perish, sl - 1]
            inv[perish, sl - 1] = 0
            inv[perish, 1:] = inv[perish, :-1]
            inv[perish, 0] = 0
        on_hand -= expired

        # 2. damage, taken from the oldest stock
        damaged = rng.binomial(on_hand, damage_rate)
        take_fifo(inv, damaged)
        on_hand -= damaged

        # 3. receipts arrive before opening
        arr = arrivals.pop(d, [])
        if arr:
            r_cell, r_qty, r_line, r_oday, r_ordered = (
                np.concatenate(x) for x in zip(*arr, strict=True)
            )
            np.add.at(inv[:, 0], r_cell, r_qty)
            np.add.at(on_hand, r_cell, r_qty)
            np.add.at(on_order, r_cell, -r_ordered)
        else:
            r_cell = r_qty = r_line = r_oday = empty_i

        # 4. demand: calendar x promo uplift x day-level shock, split into trading hours
        discount = np.zeros(n_cells)
        for i, mask in enumerate(promo_masks):
            if m.promo_start[i] <= d <= m.promo_end[i]:
                discount = np.where(mask, np.maximum(discount, m.promo_discount[i]), discount)
        expected = (
            base * factors[d, cat] * (1 + cfg["promotions"]["uplift_per_discount"] * discount)
        )
        expected = expected * active
        shock = rng.gamma(dc["day_noise_shape"], 1 / dc["day_noise_shape"], n_cells)
        demand = rng.poisson((expected * shock)[:, None] * profile[None, :])
        dem_online = rng.binomial(demand, online_share[:, None])
        dem_store = demand - dem_online

        # 5. trade hour by hour: in-store first, then online picks from the same shelf
        sold = np.zeros((n_cells, n_hours), dtype=np.int64)
        shipped = np.zeros_like(sold)
        snap = np.zeros_like(sold)
        for h in range(n_hours):
            s = np.minimum(dem_store[:, h], on_hand)
            take_fifo(inv, s)
            on_hand -= s
            o = np.minimum(dem_online[:, h], on_hand)
            take_fifo(inv, o)
            on_hand -= o
            sold[:, h], shipped[:, h], snap[:, h] = s, o, on_hand

        # 6. nightly batch: 28-day moving average of observed (censored) sales, fixed safety stock
        ring[:, d % ma_days] = sold.sum(axis=1) + shipped.sum(axis=1)
        forecast = ring.mean(axis=1)
        reorder_point = np.maximum(forecast * (lead + safety), min_stock)
        order_up_to = np.maximum(forecast * (lead + review + safety), min_stock)
        position = on_hand + on_order
        orderable = m.cell_active_from <= d + 1
        need = orderable & (position < reorder_point)
        qty = np.where(need, np.ceil((order_up_to - position) / case) * case, 0).astype(np.int64)
        full = rng.random(n_cells) < sup["full_fill_prob"]
        frac = rng.uniform(*sup["short_fill"], n_cells)
        received = np.where(full, qty, np.floor(qty / case * frac).astype(np.int64) * case)
        late = np.where(
            rng.random(n_cells) < sup["late_prob"],
            rng.integers(sup["late_days"][0], sup["late_days"][1] + 1, n_cells),
            0,
        )
        po_cell = np.flatnonzero(qty)
        po_due = d + lead[po_cell]
        arrival = po_due + late[po_cell]
        po_line = d * 100_000 + po_cell
        for a in np.unique(arrival):
            sel = arrival == a
            arrivals.setdefault(int(a), []).append(
                (
                    po_cell[sel],
                    received[po_cell[sel]],
                    po_line[sel],
                    np.full(sel.sum(), d, dtype=np.int64),
                    qty[po_cell[sel]],
                )
            )
        on_order += qty

        yield DayResult(
            day=d,
            active=active,
            expected=expected,
            discount=discount,
            dem_store=dem_store,
            dem_online=dem_online,
            sold=sold,
            shipped=shipped,
            on_hand=snap,
            expired=expired,
            damaged=damaged,
            rcv_cell=r_cell,
            rcv_qty=r_qty,
            rcv_po_line=r_line,
            rcv_order_day=r_oday,
            po_cell=po_cell,
            po_qty=qty[po_cell],
            po_due_day=po_due,
            po_arrival_day=arrival,
        )
