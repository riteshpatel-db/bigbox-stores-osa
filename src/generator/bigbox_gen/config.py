"""Load the generator config and derive the simulation calendar."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config(path: Path | str = DEFAULT_CONFIG, overrides: dict | None = None) -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f)
    if overrides:
        cfg = _merge(cfg, overrides)
    return cfg


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def config_sha256(cfg: dict) -> str:
    canonical = json.dumps(cfg, sort_keys=True, default=str).encode()
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class Calendar:
    sim_start: dt.date
    history_start: dt.date
    history_end: dt.date
    live_end: dt.date
    open_hour: int
    close_hour: int

    @classmethod
    def from_config(cls, cfg: dict) -> Calendar:
        c = cfg["calendar"]
        return cls(
            sim_start=c["history_start"] - dt.timedelta(days=c["burn_in_days"]),
            history_start=c["history_start"],
            history_end=c["history_end"],
            live_end=c["live_end"],
            open_hour=c["open_hour"],
            close_hour=c["close_hour"],
        )

    @property
    def n_days(self) -> int:
        return (self.live_end - self.sim_start).days + 1

    @property
    def hours(self) -> int:
        return self.close_hour - self.open_hour

    def index(self, day: dt.date) -> int:
        return (day - self.sim_start).days

    def date(self, idx: int) -> dt.date:
        return self.sim_start + dt.timedelta(days=idx)

    @property
    def emit_start(self) -> int:
        return self.index(self.history_start)

    @property
    def live_start(self) -> int:
        return self.index(self.history_end) + 1

    @property
    def last_day(self) -> int:
        return self.n_days - 1
