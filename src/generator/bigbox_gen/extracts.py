"""Turn simulated days into source-system extracts, inject defects, write the ground truth.

History (history_start .. history_end) is written as one file per entity per day, as a nightly batch
would deliver it. The live window (after history_end) is written as hourly micro-batch files into
_staging/, which bigbox_live_drip releases into the landing folders in time order.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from .config import Calendar
from .masters import Masters
from .simulate import DayResult
from .sink import Sink

Key = tuple[
    int, int | None
]  # (day, clock hour) for live files; (day, None) for daily history files

ENTITY_PREFIX = {
    "pos_order_lines": ("pos", "csv"),
    "online_order_lines": ("online", "jsonl"),
    "inventory_snapshots": ("inv", "csv"),
    "replenishment_orders": ("po", "csv"),
    "replenishment_receipts": ("rcv", "csv"),
    "write_offs": ("wo", "csv"),
    "returns": ("ret", "csv"),
}
# clock hour of the live micro-batch that carries each daily entity
DAILY_SLOT = {
    "replenishment_receipts": 6,
    "write_offs": 7,
    "returns": 21,
    "replenishment_orders": 23,
}
POS_DEFECTS = ["null_sku", "null_store", "null_price", "orphan_sku", "negative_qty", "future_ts"]


def _ts(day_date: dt.date, seconds: np.ndarray) -> np.ndarray:
    return np.datetime64(day_date, "s") + seconds.astype("timedelta64[s]")


class Extracts:
    def __init__(self, cfg: dict, cal: Calendar, m: Masters, sink: Sink, rng: np.random.Generator):
        self.cfg, self.cal, self.m, self.sink, self.rng = cfg, cal, m, sink, rng
        self.df = cfg["defects"]
        self.H = cal.hours
        self.store_ids = pa.array(m.store_id)
        self.sku_ids = pa.array(m.sku_id)
        self.cell_store = m.cell_store
        self.cell_sku = m.cell_sku
        self.price = m.sku_price
        self.case_pack = m.sku_case_pack
        cats = cfg["products"]["categories"]
        self.return_rate = np.array([c["return_rate"] for c in cats])[m.sku_category]
        flat = np.concatenate(m.buyers_by_store)
        self.buyer_flat = flat
        self.buyer_start = np.concatenate(
            [[0], np.cumsum([len(b) for b in m.buyers_by_store])[:-1]]
        )
        self.buyer_count = np.array([len(b) for b in m.buyers_by_store])
        self.pending: dict[str, dict[Key, list]] = {
            "pos": defaultdict(list),
            "online": defaultdict(list),
        }
        self.pending_returns: dict[int, list[dict]] = defaultdict(list)
        self.opening_pos: list[dict] = []
        self.truth: list[pa.Table] = []
        self.truth_month: str | None = None
        self.defects: dict[str, int] = defaultdict(int)
        # per output file, so a reconciliation can count only the files already delivered
        self.file_defects: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.history_end = cal.index(cal.history_end)

    # ---------- keys, paths, timestamps ----------
    def is_live(self, day: int) -> bool:
        return day > self.history_end

    def path(self, entity: str, key: Key) -> str:
        prefix, ext = ENTITY_PREFIX[entity]
        day, hour = key
        stamp = self.cal.date(day).strftime("%Y%m%d")
        if hour is None:
            return f"{entity}/{prefix}_{stamp}.{ext}"
        return f"_staging/{entity}/{prefix}_{stamp}{hour:02d}.{ext}"

    def extract_ts(self, key: Key) -> np.datetime64:
        day, hour = key
        if hour is None:  # nightly batch, 02:00 the next morning
            return np.datetime64(self.cal.date(day + 1), "s") + np.timedelta64(2 * 3600, "s")
        return np.datetime64(self.cal.date(day), "s") + np.timedelta64((hour + 1) * 3600, "s")

    def key_for(self, day: int, clock_hour: int) -> Key:
        day = min(day, self.cal.last_day)
        return (day, None) if not self.is_live(day) else (day, clock_hour)

    def next_key(self, key: Key, clock_hour: int) -> Key:
        day, hour = key
        if hour is None:
            return self.key_for(
                day + 1, self.cal.open_hour if self.is_live(day + 1) else clock_hour
            )
        if hour + 1 < self.cal.close_hour:
            return (day, hour + 1)
        return self.key_for(day + 1, self.cal.open_hour) if day < self.cal.last_day else key

    def day_keys(self, day: int, entity: str | None = None) -> list[Key]:
        if not self.is_live(day):
            return [(day, None)]
        if entity in DAILY_SLOT:
            return [(day, DAILY_SLOT[entity])]
        return [(day, self.cal.open_hour + h) for h in range(self.H)]

    # ---------- masters ----------
    def write_masters(self) -> None:
        m, cal = self.m, self.cal
        sc = self.cfg["stores"]
        self.sink.csv(
            "stores/stores.csv",
            pa.table(
                {
                    "store_id": m.store_id,
                    "store_name": [f"Bigbox Stores #{s[1:]}" for s in m.store_id],
                    "region": m.store_region,
                    "state": m.store_state,
                    "format": m.store_format,
                    "timezone": m.store_tz,
                    "open_time": [f"{cal.open_hour:02d}:00"] * len(m.store_id),
                    "close_time": [f"{cal.close_hour:02d}:00"] * len(m.store_id),
                    "sales_area_sqft": np.round(
                        m.store_size / sc["formats"]["STANDARD"]["size"] * 120_000, -3
                    ).astype(np.int64),
                }
            ),
        )
        launch = [d if d > cal.history_start else cal.history_start for d in m.sku_launch]
        self.sink.csv(
            "products/products.csv",
            pa.table(
                {
                    "sku_id": m.sku_id,
                    "sku_name": m.sku_name,
                    "category": [m.category_names[c] for c in m.sku_category],
                    "perishable": m.sku_perishable,
                    "shelf_life_days": pa.array(
                        [int(s) if s else None for s in m.sku_shelf_life], pa.int64()
                    ),
                    "unit_cost": m.sku_cost,
                    "unit_price": m.sku_price,
                    "case_pack": m.sku_case_pack.astype(np.int64),
                    "lead_time_days": m.sku_lead_time.astype(np.int64),
                    "supplier_id": m.sku_supplier,
                    "launch_date": pa.array(launch, pa.date32()),
                }
            ),
        )
        eff = [launch[s] for s in m.assort_sku]
        self.sink.csv(
            "assortment/assortment.csv",
            pa.table(
                {
                    "store_id": pc.take(self.store_ids, pa.array(m.assort_store)),
                    "sku_id": pc.take(self.sku_ids, pa.array(m.assort_sku)),
                    "ranged": m.assort_ranged,
                    "effective_from": pa.array(eff, pa.date32()),
                }
            ),
        )
        self.sink.csv(
            "buyers/buyers.csv",
            pa.table(
                {
                    "buyer_id": m.buyer_id,
                    "first_name": m.buyer_first,
                    "last_name": m.buyer_last,
                    "email": m.buyer_email,
                    "phone": m.buyer_phone,
                    "home_store_id": pc.take(self.store_ids, pa.array(m.buyer_home_store)),
                    "loyalty_since": pa.array(m.buyer_since.astype("datetime64[D]"), pa.date32()),
                }
            ),
        )
        rows = defaultdict(list)
        for i, pid in enumerate(m.promo_id):
            for s in m.promo_skus[i]:
                for r in m.promo_regions[i]:
                    rows["promo_id"].append(pid)
                    rows["sku_id"].append(m.sku_id[s])
                    rows["region"].append(r)
                    rows["start_date"].append(cal.date(m.promo_start[i]))
                    rows["end_date"].append(cal.date(m.promo_end[i]))
                    rows["discount_pct"].append(round(m.promo_discount[i] * 100))
        self.sink.csv(
            "promotions/promotions.csv",
            pa.table(
                {k: pa.array(v, pa.date32()) if k.endswith("date") else v for k, v in rows.items()}
            ),
        )

    # ---------- one simulated day ----------
    def add_day(self, r: DayResult) -> None:
        if r.day < self.cal.emit_start:
            # burn-in: keep only open orders that will be received inside the emitted window
            keep = r.po_arrival_day >= self.cal.emit_start
            if keep.any():
                self.opening_pos.append(self._po_rows(r, keep))
            return
        self._pos(r)
        self._online(r)
        self._snapshots(r)
        self._replenishment(r)
        self._write_offs(r)
        self._returns(r.day)
        self._truth(r)

    def _split_lines(self, units: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Split per (cell, hour) units into lines of 1-3 units."""
        qp = self.cfg["pos"]["qty_per_line"]
        sizes = np.array([int(k) for k in qp])
        probs = np.array(list(qp.values()), dtype=float)
        cell, hour = np.nonzero(units)
        rem = units[cell, hour].astype(np.int64)
        out_c, out_h, out_q = [], [], []
        idx = np.arange(cell.size)
        while idx.size:
            q = np.minimum(self.rng.choice(sizes, size=idx.size, p=probs / probs.sum()), rem[idx])
            out_c.append(cell[idx])
            out_h.append(hour[idx])
            out_q.append(q)
            rem[idx] -= q
            idx = idx[rem[idx] > 0]
        if not out_c:
            e = np.zeros(0, dtype=np.int64)
            return e, e, e
        c, h, q = np.concatenate(out_c), np.concatenate(out_h), np.concatenate(out_q)
        order = np.lexsort((c, self.cell_store[c] * self.H + h))
        return c[order], h[order], q[order]

    def _group_ids(self, store: np.ndarray, hour: np.ndarray, per_group: float):
        """Assign rows (sorted by store, hour) to random baskets/orders within each store-hour."""
        g = store * self.H + hour
        _, inv, counts = np.unique(g, return_inverse=True, return_counts=True)
        n_groups = np.ceil(counts / per_group).astype(np.int64)
        local = np.floor(self.rng.random(g.size) * n_groups[inv]).astype(np.int64)
        gid = g * 10_000 + local
        uniq, ginv = np.unique(gid, return_inverse=True)
        return uniq, ginv, local

    def _buyers(self, store: np.ndarray) -> np.ndarray:
        pick = self.buyer_start[store] + np.floor(
            self.rng.random(store.size) * self.buyer_count[store]
        )
        return self.m.buyer_id[self.buyer_flat[pick.astype(np.int64)]]

    def _pos(self, r: DayResult) -> None:
        d, cal, rng, df = r.day, self.cal, self.rng, self.df
        date = cal.date(d)
        cell, hour, qty = self._split_lines(r.sold)
        n = cell.size
        store, sku = self.cell_store[cell], self.cell_sku[cell]
        uniq, binv, local = self._group_ids(store, hour, self.cfg["pos"]["lines_per_basket"])
        b_store = uniq // 10_000 // self.H
        b_hour = (uniq // 10_000) % self.H
        b_local = uniq % 10_000
        stamp = date.strftime("%Y%m%d")
        b_order = np.char.add(
            np.char.add(
                np.char.add(f"P{stamp}", self.m.store_id[b_store]),
                np.char.zfill((b_hour + cal.open_hour).astype(str), 2),
            ),
            np.char.zfill(b_local.astype(str), 4),
        )
        loyal = rng.random(uniq.size) < self.cfg["buyers"]["loyalty_share_of_pos_baskets"]
        b_buyer = np.where(loyal, self._buyers(b_store), None)
        b_secs = (cal.open_hour + b_hour) * 3600 + rng.integers(0, 3600, uniq.size)
        line_id = d * 10_000_000 + np.arange(n, dtype=np.int64)
        price = self.price[sku]
        disc = np.round(qty * price * r.discount[cell], 2)
        order_id = b_order[binv]
        self._queue_returns(d, "POS", order_id, line_id, store, sku, qty, price, disc)

        # defects
        store_s = self.m.store_id[store].astype(object)
        sku_s = self.m.sku_id[sku].astype(object)
        price_v = price.astype(object)
        disc_v = disc.astype(float)
        ts = _ts(date, b_secs[binv])
        q = qty.copy()
        cents = df["cents_price"]
        in_cents = (store_s == cents["store_id"]) & (cents["start"] <= date <= cents["end"])
        price_v[in_cents] = np.round(price[in_cents] * 100)
        disc_v[in_cents] = np.round(disc[in_cents] * 100)
        self.defects["pos_cents_price"] += int(in_cents.sum())
        label = np.full(n, None, dtype=object)  # defect per row, counted per file, never written
        label[in_cents] = "pos_cents_price"
        rates = np.array([df[f"pos_{k}_rate"] for k in POS_DEFECTS])
        u = rng.random(n)
        edges = np.cumsum(rates)
        kind = np.searchsorted(edges, u, side="right")  # == len(rates) means clean
        kind[in_cents] = len(rates)
        for i, name in enumerate(POS_DEFECTS):
            sel = kind == i
            self.defects[f"pos_{name}"] += int(sel.sum())
            label[sel] = f"pos_{name}"
            if name == "null_sku":
                sku_s[sel] = None
            elif name == "null_store":
                store_s[sel] = None
            elif name == "null_price":
                price_v[sel] = None
            elif name == "orphan_sku":
                sku_s[sel] = np.char.add(
                    "SKU9", np.char.zfill(rng.integers(0, 1000, sel.sum()).astype(str), 3)
                )
            elif name == "negative_qty":
                q[sel] = -q[sel]
            elif name == "future_ts":
                ts[sel] = ts[sel] + np.timedelta64(df["future_ts_shift_days"], "D")
        clean = np.flatnonzero((kind == len(rates)) & ~in_cents)

        cols = {
            "line_id": line_id,
            "order_id": order_id,
            "store_id": store_s,
            "sku_id": sku_s,
            "event_ts": ts,
            "quantity": q,
            "unit_price": price_v,
            "discount_amount": disc_v,
            "buyer_id": b_buyer[binv],
            "_defect": label,
        }
        clock = hour + cal.open_hour
        base_key = [self.key_for(d, h) for h in range(cal.open_hour, cal.close_hour)]

        def take(idx: np.ndarray, **over) -> pa.Table:
            t = {k: v[idx] for k, v in cols.items()}
            t.update(over)
            return _pos_table(t)

        # test store: copies of clean lines under a store that is not in the store master
        test = clean[rng.random(clean.size) < df["pos_test_store_rate"]]
        self.defects["pos_test_store"] += int(test.size)
        # late: lines delivered 1-3 days after the event; duplicates: re-sent in the next file
        lag = rng.integers(df["pos_late_days"][0], df["pos_late_days"][1] + 1, clean.size)
        # only rows whose late delivery still falls inside the generated window
        late_mask = (rng.random(clean.size) < df["pos_late_rate"]) & (d + lag <= cal.last_day)
        late, late_days = clean[late_mask], lag[late_mask]
        rest = clean[~late_mask]
        dup = rest[rng.random(rest.size) < df["pos_duplicate_rate"]]
        self.defects["pos_late"] += int(late.size)
        self.defects["pos_duplicate"] += int(dup.size)

        stay = np.ones(n, dtype=bool)
        stay[late] = False
        for i in np.unique(late_days) if late.size else []:
            sel = late[late_days == i]
            for h in np.unique(clock[sel]):
                rows = sel[clock[sel] == h]
                self.pending["pos"][self.key_for(d + int(i), int(h))].append(
                    take(rows, _defect=np.full(rows.size, "pos_late", dtype=object))
                )
        for h in np.unique(clock[dup]) if dup.size else []:
            rows = dup[clock[dup] == h]
            k = self.next_key(base_key[h - cal.open_hour], int(h))
            self.pending["pos"][k].append(
                take(rows, _defect=np.full(rows.size, "pos_duplicate", dtype=object))
            )
        if test.size:
            for h in np.unique(clock[test]):
                rows = test[clock[test] == h]
                self.pending["pos"][base_key[h - cal.open_hour]].append(
                    take(
                        rows,
                        store_id=np.full(rows.size, df["test_store_id"], dtype=object),
                        line_id=line_id[rows] + 5_000_000,
                        _defect=np.full(rows.size, "pos_test_store", dtype=object),
                    )
                )
        for key in self.day_keys(d):
            sel = (
                np.flatnonzero(stay) if key[1] is None else np.flatnonzero(stay & (clock == key[1]))
            )
            parts = [take(sel)] + self.pending["pos"].pop(key, [])
            t = pa.concat_tables(parts)
            if t.num_rows:
                path = self.path("pos_order_lines", key)
                for v in pc.value_counts(t["_defect"]).to_pylist():
                    if v["values"] is not None:
                        self.file_defects[path + ".gz"][v["values"]] += v["counts"]
                t = t.drop_columns(["_defect"]).append_column(
                    "extract_ts", pa.array(np.full(t.num_rows, self.extract_ts(key)))
                )
                self.sink.csv(path, t)

    def _online(self, r: DayResult) -> None:
        d, cal, rng, df, oc = r.day, self.cal, self.rng, self.df, self.cfg["online"]
        date = cal.date(d)
        cell, hour = np.nonzero(r.dem_online)
        order = np.lexsort((cell, self.cell_store[cell] * self.H + hour))
        cell, hour = cell[order], hour[order]
        n = cell.size
        store, sku = self.cell_store[cell], self.cell_sku[cell]
        req = r.dem_online[cell, hour].astype(np.int64)
        ship = r.shipped[cell, hour].astype(np.int64)
        price = self.price[sku]
        disc = np.round(ship * price * r.discount[cell], 2)
        uniq, oinv, _ = self._group_ids(store, hour, float(np.mean(oc["lines_per_order"])))
        # lines of one order must be contiguous for line_number
        order = np.lexsort((cell, oinv))
        cell, hour, store, sku, oinv = (
            cell[order],
            hour[order],
            store[order],
            sku[order],
            oinv[order],
        )
        req, ship, price, disc = req[order], ship[order], price[order], disc[order]
        o_store = uniq // 10_000 // self.H
        o_hour = (uniq // 10_000) % self.H
        stamp = date.strftime("%Y%m%d")
        o_id = np.char.add(
            np.char.add(
                np.char.add(f"W{stamp}", self.m.store_id[o_store]),
                np.char.zfill((o_hour + cal.open_hour).astype(str), 2),
            ),
            np.char.zfill((uniq % 10_000).astype(str), 4),
        )
        o_buyer = self._buyers(o_store)
        o_secs = (cal.open_hour + o_hour) * 3600 + rng.integers(0, 3600, uniq.size)
        o_total = np.bincount(oinv, weights=ship * price - disc, minlength=uniq.size)
        o_fee = np.where(
            (o_total > 0) & (o_total < oc["free_delivery_over"]), oc["delivery_fee"], 0.0
        )
        o_pickup = rng.random(uniq.size) < oc["pickup_share"]
        first = np.r_[True, oinv[1:] != oinv[:-1]] if n else np.zeros(0, dtype=bool)
        line_no = np.arange(n) - np.maximum.accumulate(np.where(first, np.arange(n), 0)) + 1
        line_id = d * 10_000_000 + np.arange(n, dtype=np.int64)
        shipped_any = ship > 0
        self._queue_returns(
            d,
            "ONLINE",
            o_id[oinv][shipped_any],
            line_id[shipped_any],
            store[shipped_any],
            sku[shipped_any],
            ship[shipped_any],
            price[shipped_any],
            disc[shipped_any],
        )

        # only fully shipped lines are corrupted, so the true shipped quantity stays known
        over = (rng.random(n) < df["online_overship_rate"]) & (ship == req)
        ship_out = np.where(over, req + rng.integers(1, 3, n), ship)
        self.defects["online_overship"] += int(over.sum())
        drift = df["schema_drift"]
        has_drift = date >= drift["start"]
        late = rng.random(n) < df["online_late_rate"]
        late_h = rng.integers(2, 7, n)
        clock_all = hour + cal.open_hour
        if self.is_live(d):  # late only if the target batch is still inside the window
            fits = (clock_all + late_h < cal.close_hour) | (d < cal.last_day)
        else:
            fits = np.full(n, d + 1 <= cal.last_day)
        late &= fits
        self.defects["online_late"] += int(late.sum())
        ts = _ts(date, o_secs[oinv])
        rows = []
        targets = []
        for i in range(n):
            o = oinv[i]
            row = {
                "order_id": str(o_id[o]),
                "line_id": int(line_id[i]),
                "line_number": int(line_no[i]),
                "buyer_id": str(o_buyer[o]),
                "fulfilling_store_id": str(self.m.store_id[store[i]]),
                "sku_id": str(self.m.sku_id[sku[i]]),
                "order_ts": str(ts[i]).replace("T", " "),
                "requested_qty": int(req[i]),
                "shipped_qty": int(ship_out[i]),
                "unit_price": float(price[i]),
                "discount_amount": float(disc[i]),
                "delivery_fee": float(o_fee[o]) if line_no[i] == 1 else 0.0,
            }
            if has_drift:
                row[drift["column"]] = "PICKUP" if o_pickup[o] else "SHIP"
            row["_flags"] = (
                bool(late[i]),
                bool(over[i]),
                has_drift,
            )  # counted per file, not written
            clock = int(hour[i]) + cal.open_hour
            if not late[i]:
                key = self.key_for(d, clock)
            elif not self.is_live(d):
                key = self.key_for(d + 1, cal.open_hour)
            else:
                h = clock + int(late_h[i])
                key = (
                    self.key_for(d, h)
                    if h < cal.close_hour
                    else self.key_for(d + 1, cal.open_hour + h - cal.close_hour)
                )
            rows.append(row)
            targets.append(key)
        self.defects["online_schema_drift_rows"] += n if has_drift else 0
        for row, key in zip(rows, targets, strict=True):
            self.pending["online"][key].append(row)
        for key in self.day_keys(d):
            out = self.pending["online"].pop(key, [])
            if out:
                path = self.path("online_order_lines", key)
                counts = self.file_defects[path + ".gz"]
                xts = str(self.extract_ts(key)).replace("T", " ")
                for row in out:
                    is_late, is_over, is_drift = row.pop("_flags")
                    counts["online_late"] += is_late
                    counts["online_overship"] += is_over
                    counts["online_schema_drift_rows"] += is_drift
                    row["extract_ts"] = xts
                self.sink.jsonl(path, out)

    def _snapshots(self, r: DayResult) -> None:
        date = self.cal.date(r.day)
        cells = np.flatnonzero(r.active)
        store = pa.array(self.cell_store[cells])
        sku = pa.array(self.cell_sku[cells])
        keys = self.day_keys(r.day)
        hours = [range(self.H)] if keys[0][1] is None else [[h] for h in range(self.H)]
        for key, hs in zip(keys, hours, strict=True):
            parts = []
            for h in hs:
                ts = np.full(
                    cells.size,
                    np.datetime64(date, "s")
                    + np.timedelta64((self.cal.open_hour + h + 1) * 3600, "s"),
                )
                parts.append(
                    pa.table(
                        {
                            "store_id": pc.take(self.store_ids, store),
                            "sku_id": pc.take(self.sku_ids, sku),
                            "snapshot_ts": pa.array(ts),
                            "on_hand": pa.array(r.on_hand[cells, h]),
                        }
                    )
                )
            self.sink.csv(self.path("inventory_snapshots", key), pa.concat_tables(parts))

    def _po_rows(self, r: DayResult, keep: np.ndarray) -> dict:
        date = self.cal.date(r.day)
        cell = r.po_cell[keep]
        store, sku = self.cell_store[cell], self.cell_sku[cell]
        return {
            "po_id": np.char.add(f"PO{date:%Y%m%d}-", self.m.store_id[store]),
            "po_line_id": r.day * 100_000 + cell,
            "store_id": self.m.store_id[store],
            "sku_id": self.m.sku_id[sku],
            "supplier_id": self.m.sku_supplier[sku],
            "order_ts": np.full(
                cell.size, np.datetime64(date, "s") + np.timedelta64(23 * 3600, "s")
            ),
            "ordered_qty": r.po_qty[keep],
            "uom": np.full(cell.size, "EA"),
            "due_date": np.array(
                [self.cal.date(int(x)) for x in r.po_due_day[keep]], dtype="datetime64[D]"
            ),
        }

    def _replenishment(self, r: DayResult) -> None:
        d, date, df = r.day, self.cal.date(r.day), self.df
        rows = [self._po_rows(r, np.ones(r.po_cell.size, dtype=bool))]
        if d == self.cal.emit_start:
            rows = self.opening_pos + rows
        po = {k: np.concatenate([x[k] for x in rows]) for k in rows[0]}
        if po["po_line_id"].size:
            key = self.day_keys(d, "replenishment_orders")[0]
            po_t = pa.table({**po, "due_date": pa.array(po["due_date"], pa.date32())})
            self.sink.csv(self.path("replenishment_orders", key), po_t)

        cell = r.rcv_cell
        if cell.size:
            store, sku = self.cell_store[cell], self.cell_sku[cell]
            supplier = self.m.sku_supplier[sku]
            qty = r.rcv_qty.astype(np.int64)
            uom = np.full(cell.size, "EA", dtype=object)
            u = df["uom_cases"]
            cs = (supplier == u["supplier_id"]) & (u["start"] <= date <= u["end"])
            qty = np.where(cs, qty // self.case_pack[sku], qty)
            uom[cs] = "CS"
            self.defects["receipts_uom_cases"] += int(cs.sum())
            path = self.path(
                "replenishment_receipts", self.day_keys(d, "replenishment_receipts")[0]
            )
            if cs.any():
                self.file_defects[path + ".gz"]["receipts_uom_cases"] += int(cs.sum())
            secs = 6 * 3600 + self.rng.integers(0, 3600, cell.size)
            t = pa.table(
                {
                    "receipt_id": d * 1_000_000 + np.arange(cell.size, dtype=np.int64),
                    "po_line_id": r.rcv_po_line,
                    "store_id": self.m.store_id[store],
                    "sku_id": self.m.sku_id[sku],
                    "supplier_id": supplier,
                    "received_ts": _ts(date, secs),
                    "received_qty": qty,
                    "uom": uom.astype(str),
                }
            )
            self.sink.csv(
                path,
                t,
            )

    def _write_offs(self, r: DayResult) -> None:
        date = self.cal.date(r.day)
        parts = []
        for reason, qty in (("EXPIRED", r.expired), ("DAMAGED", r.damaged)):
            cell = np.flatnonzero(qty)
            if not cell.size:
                continue
            parts.append(
                pa.table(
                    {
                        "writeoff_date": pa.array(
                            np.full(cell.size, np.datetime64(date, "D")), pa.date32()
                        ),
                        "store_id": pc.take(self.store_ids, pa.array(self.cell_store[cell])),
                        "sku_id": pc.take(self.sku_ids, pa.array(self.cell_sku[cell])),
                        "reason": pa.array([reason] * cell.size),
                        "quantity": pa.array(qty[cell].astype(np.int64)),
                    }
                )
            )
        if parts:
            self.sink.csv(
                self.path("write_offs", self.day_keys(r.day, "write_offs")[0]),
                pa.concat_tables(parts),
            )

    def _queue_returns(self, d, channel, order_id, line_id, store, sku, qty, price, disc) -> None:
        rc = self.cfg["returns"]
        ret = self.rng.random(line_id.size) < self.return_rate[sku]
        if not ret.any():
            return
        lag = np.minimum(self.rng.geometric(1 / rc["lag_mean_days"], ret.sum()), rc["max_lag_days"])
        reasons = list(rc["reasons"])
        probs = np.array(list(rc["reasons"].values()), dtype=float)
        reason = np.array(reasons)[
            self.rng.choice(len(reasons), size=ret.sum(), p=probs / probs.sum())
        ]
        secs = (
            self.cal.open_hour + self.rng.integers(0, self.H, ret.sum())
        ) * 3600 + self.rng.integers(0, 3600, ret.sum())
        q = qty[ret]
        refund = np.round(q * price[ret] - disc[ret], 2)
        for day in np.unique(lag):
            sel = lag == day
            if d + int(day) > self.cal.last_day:
                continue
            self.pending_returns[d + int(day)].append(
                {
                    "original_order_id": order_id[ret][sel],
                    "original_line_id": line_id[ret][sel],
                    "channel": np.full(sel.sum(), channel),
                    "store_id": self.m.store_id[store[ret][sel]],
                    "sku_id": self.m.sku_id[sku[ret][sel]],
                    "secs": secs[sel],
                    "quantity": q[sel],
                    "refund_amount": refund[sel],
                    "reason": reason[sel],
                }
            )

    def _returns(self, d: int) -> None:
        parts = self.pending_returns.pop(d, [])
        if not parts:
            return
        cols = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
        secs = cols.pop("secs")
        n = secs.size
        t = pa.table(
            {
                "return_id": d * 10_000_000 + np.arange(n, dtype=np.int64),
                **{
                    k: cols[k]
                    for k in (
                        "original_order_id",
                        "original_line_id",
                        "channel",
                        "store_id",
                        "sku_id",
                    )
                },
                "return_ts": _ts(self.cal.date(d), secs),
                **{k: cols[k] for k in ("quantity", "refund_amount", "reason")},
            }
        )
        self.sink.csv(self.path("returns", self.day_keys(d, "returns")[0]), t)

    def _truth(self, r: DayResult) -> None:
        date = self.cal.date(r.day)
        cells = np.flatnonzero(r.active)
        received = np.bincount(r.rcv_cell, weights=r.rcv_qty, minlength=r.active.size)
        month = f"{date:%Y%m}"
        if self.truth_month and month != self.truth_month:
            self._flush_truth()
        self.truth_month = month
        self.truth.append(
            pa.table(
                {
                    "date": pa.array(np.full(cells.size, np.datetime64(date, "D")), pa.date32()),
                    "store_id": pc.take(self.store_ids, pa.array(self.cell_store[cells])),
                    "sku_id": pc.take(self.sku_ids, pa.array(self.cell_sku[cells])),
                    "expected_demand": np.round(r.expected[cells], 4),
                    "demand_instore": r.dem_store[cells].sum(axis=1),
                    "demand_online": r.dem_online[cells].sum(axis=1),
                    "sold_instore": r.sold[cells].sum(axis=1),
                    "shipped_online": r.shipped[cells].sum(axis=1),
                    "stockout_hours": (r.on_hand[cells] == 0).sum(axis=1),
                    "closing_on_hand": r.on_hand[cells, -1],
                    "expired_units": r.expired[cells],
                    "damaged_units": r.damaged[cells],
                    "received_units": received[cells].astype(np.int64),
                    "promo_discount": r.discount[cells],
                }
            )
        )

    def _flush_truth(self) -> None:
        if self.truth:
            self.sink.csv(
                f"_ground_truth/truth_{self.truth_month}.csv", pa.concat_tables(self.truth)
            )
            self.truth = []

    def defects_by_file(self) -> dict[str, dict[str, int]]:
        """Non-zero defect counts per file; they sum exactly to the run totals."""
        out = {
            f: {k: v for k, v in sorted(c.items()) if v}
            for f, c in sorted(self.file_defects.items())
        }
        out = {f: c for f, c in out.items() if c}
        for name, total in self.defects.items():
            per_file = sum(c.get(name, 0) for c in out.values())
            if per_file != total:
                raise RuntimeError(f"{name}: {per_file} counted per file vs {total} injected")
        return out

    def finish(self) -> None:
        self._flush_truth()
        for name in ("pos", "online"):
            if self.pending[name]:
                raise RuntimeError(
                    f"unwritten {name} rows for keys {sorted(self.pending[name])[:3]}"
                )


def _pos_table(t: dict) -> pa.Table:
    return pa.table(
        {
            "line_id": pa.array(t["line_id"], pa.int64()),
            "order_id": pa.array(t["order_id"], pa.string()),
            "store_id": pa.array(t["store_id"], pa.string()),
            "sku_id": pa.array(t["sku_id"], pa.string()),
            "event_ts": pa.array(t["event_ts"], pa.timestamp("s")),
            "quantity": pa.array(t["quantity"], pa.int64()),
            "unit_price": pa.array(t["unit_price"], pa.float64(), from_pandas=True),
            "discount_amount": pa.array(t["discount_amount"], pa.float64()),
            "buyer_id": pa.array(t["buyer_id"], pa.string()),
            "_defect": pa.array(t["_defect"], pa.string()),
        }
    )
