"""Master data: stores, products, assortment (the store x SKU cells), buyers and promotions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import Calendar

STATES = {
    "EAST": ["NY", "PA", "NJ", "MA", "CT"],
    "CENTRAL": ["IL", "OH", "MI", "IN", "WI"],
    "SOUTH": ["TX", "FL", "GA", "NC", "TN"],
    "WEST": ["CA", "WA", "OR", "AZ", "CO"],
}
TIMEZONES = {
    "EAST": "America/New_York",
    "CENTRAL": "America/Chicago",
    "SOUTH": "America/Chicago",
    "WEST": "America/Los_Angeles",
}
FIRST_NAMES = np.array(
    "Alex Jordan Taylor Morgan Casey Riley Jamie Avery Quinn Drew Sam Robin Jesse Kai Rowan "
    "Emery Parker Reese Skyler Logan".split()
)
LAST_NAMES = np.array(
    "Smith Johnson Lee Brown Garcia Miller Davis Wilson Moore Clark Lewis Walker Hall Young "
    "King Wright Scott Green Baker Adams".split()
)


@dataclass
class Masters:
    # stores
    store_id: np.ndarray
    store_region: np.ndarray
    store_format: np.ndarray
    store_state: np.ndarray
    store_tz: np.ndarray
    store_size: np.ndarray
    # products
    sku_id: np.ndarray
    sku_name: np.ndarray
    sku_category: np.ndarray  # index into category_names
    sku_perishable: np.ndarray
    sku_shelf_life: np.ndarray  # 0 for non-perishables
    sku_price: np.ndarray
    sku_cost: np.ndarray
    sku_case_pack: np.ndarray
    sku_lead_time: np.ndarray
    sku_supplier: np.ndarray
    sku_launch: np.ndarray  # date the SKU becomes available
    category_names: list[str]
    # assortment: every store x SKU pair, with the ranged subset as simulation cells
    assort_store: np.ndarray
    assort_sku: np.ndarray
    assort_ranged: np.ndarray
    cell_store: np.ndarray
    cell_sku: np.ndarray
    cell_active_from: np.ndarray  # day index (simulation calendar)
    cell_base_rate: np.ndarray  # units per day before calendar effects
    # buyers
    buyer_id: np.ndarray
    buyer_first: np.ndarray
    buyer_last: np.ndarray
    buyer_email: np.ndarray
    buyer_phone: np.ndarray
    buyer_home_store: np.ndarray
    buyer_since: np.ndarray
    buyers_by_store: list[np.ndarray]
    # promotions: one entry per event
    promo_id: list[str]
    promo_start: list[int]
    promo_end: list[int]
    promo_skus: list[np.ndarray]
    promo_regions: list[list[str]]
    promo_discount: list[float]

    @property
    def n_cells(self) -> int:
        return len(self.cell_store)


def build_masters(cfg: dict, cal: Calendar, rng: np.random.Generator) -> Masters:
    sc, pc, dc = cfg["stores"], cfg["products"], cfg["demand"]

    # stores: regions round-robin, formats by share
    n_st = sc["count"]
    regions = np.array(sc["regions"])[np.arange(n_st) % len(sc["regions"])]
    fmt_names = list(sc["formats"])
    fmt_share = np.array([sc["formats"][f]["share"] for f in fmt_names])
    fmt_idx = rng.choice(len(fmt_names), size=n_st, p=fmt_share / fmt_share.sum())
    formats = np.array(fmt_names)[fmt_idx]
    size = np.array([sc["formats"][f]["size"] for f in formats]) * rng.lognormal(
        0.0, sc["size_sigma"], n_st
    )
    state = np.array([STATES[r][rng.integers(len(STATES[r]))] for r in regions])
    store_id = np.array([f"S{i + 1:03d}" for i in range(n_st)])

    # products: SKU counts per category by largest remainder
    cats = pc["categories"]
    n_sku = pc["count"]
    shares = np.array([c["share"] for c in cats], dtype=float)
    raw = shares / shares.sum() * n_sku
    counts = np.floor(raw).astype(int)
    counts[np.argsort(-(raw - counts))[: n_sku - counts.sum()]] += 1
    sku_cat = np.repeat(np.arange(len(cats)), counts)
    perishable = np.array([cats[c]["perishable"] for c in sku_cat])
    shelf = np.array(
        [
            rng.integers(cats[c]["shelf_life"][0], cats[c]["shelf_life"][1] + 1)
            if cats[c]["perishable"]
            else 0
            for c in sku_cat
        ]
    )
    price = np.array([rng.uniform(*cats[c]["price"]) for c in sku_cat])
    price = np.maximum(np.round(price) - 0.01, 0.99)
    cost = np.round(price * rng.uniform(*pc["cost_ratio"], n_sku), 2)
    case_pack = np.array([rng.choice(cats[c]["case_pack"]) for c in sku_cat])
    lead = np.array(
        [rng.integers(cats[c]["lead_time"][0], cats[c]["lead_time"][1] + 1) for c in sku_cat]
    )
    supplier = np.array([f"SUP{rng.integers(1, pc['suppliers'] + 1):02d}" for _ in range(n_sku)])
    sku_id = np.array([f"SKU{i + 1:04d}" for i in range(n_sku)])
    per_cat = np.zeros(len(cats), dtype=int)
    names = []
    for c in sku_cat:
        per_cat[c] += 1
        names.append(f"{cats[c]['name']} item {per_cat[c]:03d}")
    launch = np.full(n_sku, cal.sim_start, dtype=object)
    n_new = pc["new_launches"]["count"]
    if n_new:
        new_idx = rng.choice(n_sku, size=n_new, replace=False)
        launch[new_idx] = pc["new_launches"]["launch_date"]

    # assortment: each store ranges a format-dependent share of SKUs
    ranged_share = np.array([sc["formats"][f]["ranged"] for f in formats])
    ranged = rng.random((n_st, n_sku)) < ranged_share[:, None]
    a_store, a_sku = np.meshgrid(np.arange(n_st), np.arange(n_sku), indexing="ij")
    a_store, a_sku, a_ranged = a_store.ravel(), a_sku.ravel(), ranged.ravel()
    cell_store, cell_sku = a_store[a_ranged], a_sku[a_ranged]
    launch_idx = np.array([max(cal.index(d), 0) for d in launch])
    popularity = rng.lognormal(np.log(dc["popularity_median"]), dc["popularity_sigma"], n_sku)
    price_factor = (dc["reference_price"] / price) ** dc["price_elasticity"]
    base = popularity[cell_sku] * price_factor[cell_sku] * size[cell_store]

    # buyers: home store weighted by store size
    n_b = cfg["buyers"]["count"]
    home = rng.choice(n_st, size=n_b, p=size / size.sum())
    first = FIRST_NAMES[rng.integers(len(FIRST_NAMES), size=n_b)]
    last = LAST_NAMES[rng.integers(len(LAST_NAMES), size=n_b)]
    bnum = np.arange(1, n_b + 1)
    buyer_id = np.char.add("B", np.char.zfill(bnum.astype(str), 7))
    email = np.char.add(
        np.char.add(np.char.lower(np.char.add(np.char.add(first, "."), last)), bnum.astype(str)),
        "@example.com",
    )
    phone = np.array(
        [
            f"+1-555-{a:03d}-{b:04d}"
            for a, b in zip(rng.integers(100, 1000, n_b), rng.integers(0, 10000, n_b), strict=True)
        ]
    )
    since = np.datetime64("2015-01-01") + rng.integers(0, 3900, n_b).astype("timedelta64[D]")
    by_store = [np.flatnonzero(home == s) for s in range(n_st)]

    # promotions inside the emitted window; the incumbent policy does not know about them
    prc = cfg["promotions"]
    dur = prc["duration_days"]
    p_start, p_end, p_skus, p_regions, p_disc = [], [], [], [], []
    for _ in range(prc["events"]):
        start = int(rng.integers(cal.emit_start, cal.last_day - dur + 2))
        p_start.append(start)
        p_end.append(start + dur - 1)
        p_skus.append(np.sort(rng.choice(n_sku, size=prc["skus_per_event"], replace=False)))
        k = int(rng.integers(1, len(sc["regions"]) + 1))
        p_regions.append(sorted(rng.choice(sc["regions"], size=k, replace=False).tolist()))
        p_disc.append(round(float(rng.uniform(*prc["discount"])) / 0.05) * 0.05)
    order = np.argsort(p_start, kind="stable")

    return Masters(
        store_id=store_id,
        store_region=regions,
        store_format=formats,
        store_state=state,
        store_tz=np.array([TIMEZONES[r] for r in regions]),
        store_size=size,
        sku_id=sku_id,
        sku_name=np.array(names),
        sku_category=sku_cat,
        sku_perishable=perishable,
        sku_shelf_life=shelf,
        sku_price=price,
        sku_cost=cost,
        sku_case_pack=case_pack,
        sku_lead_time=lead,
        sku_supplier=supplier,
        sku_launch=launch,
        category_names=[c["name"] for c in cats],
        assort_store=a_store,
        assort_sku=a_sku,
        assort_ranged=a_ranged,
        cell_store=cell_store,
        cell_sku=cell_sku,
        cell_active_from=launch_idx[cell_sku],
        cell_base_rate=base,
        buyer_id=buyer_id,
        buyer_first=first,
        buyer_last=last,
        buyer_email=email,
        buyer_phone=phone,
        buyer_home_store=home,
        buyer_since=since,
        buyers_by_store=by_store,
        promo_id=[f"PR{i + 1:03d}" for i in range(len(order))],
        promo_start=[p_start[i] for i in order],
        promo_end=[p_end[i] for i in order],
        promo_skus=[p_skus[i] for i in order],
        promo_regions=[p_regions[i] for i in order],
        promo_discount=[p_disc[i] for i in order],
    )
