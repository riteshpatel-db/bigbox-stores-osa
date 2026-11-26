"""Business case arithmetic: measured loss levers x assumed capture, at assumed revenue scales.

Pure functions, no I/O beyond loading the YAML; tools/value_model_business_case.py measures the
inputs. Per lever: annual cost (measured in the synthetic data, $ per year for the modelled slice),
backtest reduction (measured, 1 - ML / incumbent; negative when the ML policy raises the cost) and
the kept share per case (assumed, business_case.yaml). Value is linear in revenue (an assumption).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_ASSUMPTIONS = Path(__file__).with_name("business_case.yaml")
CASES = ("low", "mid", "high")


@dataclass(frozen=True)
class Lever:
    key: str
    name: str
    annual_cost: float  # measured, $ per year, modelled slice
    backtest_reduction: float  # measured, share of the incumbent's cost the ML policy removes
    kept: dict[str, float]  # assumed, per case
    why: dict[str, str]

    def capture(self, case: str) -> float:
        """Share of the lever's annual cost removed in production."""
        return self.backtest_reduction * self.kept[case]

    def value(self, case: str, scale: float = 1.0) -> float:
        """$ per year; `scale` = company revenue / modelled-slice revenue."""
        return self.annual_cost * self.capture(case) * scale


def load(path: Path | str = DEFAULT_ASSUMPTIONS) -> dict:
    return yaml.safe_load(Path(path).read_text())


def levers(a: dict, annual_cost: dict[str, float], reduction: dict[str, float]) -> list[Lever]:
    return [
        Lever(k, v["name"], annual_cost[k], reduction[k], v["kept"], v["why"])
        for k, v in a["levers"].items()
    ]


def total(ls: list[Lever], case: str, scale: float = 1.0) -> float:
    return sum(lv.value(case, scale) for lv in ls)


def share_of_revenue(ls: list[Lever], case: str, slice_revenue: float) -> float:
    return total(ls, case) / slice_revenue


def sensitivity(
    ls: list[Lever], slice_revenue: float, revenues: list[float]
) -> list[dict[str, float]]:
    """Total per case at each assumed company revenue (linear in revenue)."""
    return [{"revenue": r, **{c: total(ls, c, r / slice_revenue) for c in CASES}} for r in revenues]


def sig(x: float, n: int = 2) -> float:
    """Round to n significant figures (removes false precision from modelled numbers)."""
    if x == 0 or not math.isfinite(x):
        return x
    return round(x, n - 1 - math.floor(math.log10(abs(x))))


def usd(x: float, n: int = 2) -> str:
    """$ with n significant figures: $7.1M, $510k, $176."""
    x = sig(x, n)
    a, s = abs(x), "-" if x < 0 else ""
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if a >= div:
            return f"{s}${a / div:,.{max(0, n - 1 - math.floor(math.log10(a / div)))}f}{suffix}"
    return f"{s}${a:,.{max(0, n - 1 - math.floor(math.log10(a))) if a else 0}f}"
