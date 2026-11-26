import pytest

import business_case as bc
import value_model


def _levers():
    a = bc.load()
    cost = {"lost_margin": 1000.0, "waste": 500.0, "carrying": 100.0}
    red = {"lost_margin": 0.3, "waste": 0.4, "carrying": -0.05}
    return a, bc.levers(a, cost, red)


def test_assumptions_have_every_case_and_reason():
    a = bc.load()
    for v in a["levers"].values():
        assert set(v["kept"]) == set(bc.CASES) == set(v["why"])
        assert all(0 <= v["kept"][c] <= 1 for c in bc.CASES)
        assert v["kept"]["low"] <= v["kept"]["mid"] <= v["kept"]["high"]
        assert all(v["why"][c].strip() for c in bc.CASES)


def test_mid_lost_margin_matches_the_value_model_realisation():
    assert bc.load()["levers"]["lost_margin"]["kept"]["mid"] == value_model.load()["realisation"]


def test_capture_is_backtest_reduction_times_kept():
    _, ls = _levers()
    lm = next(x for x in ls if x.key == "lost_margin")
    assert lm.capture("mid") == pytest.approx(0.3 * 0.5)
    assert lm.value("mid", scale=2) == pytest.approx(1000 * 0.15 * 2)


def test_negative_lever_is_a_cost():
    _, ls = _levers()
    assert next(x for x in ls if x.key == "carrying").value("mid") < 0


def test_cases_are_ordered_and_linear_in_revenue():
    _, ls = _levers()
    s = bc.sensitivity(ls, slice_revenue=10_000, revenues=[10_000, 20_000])
    assert s[0]["low"] < s[0]["mid"] < s[0]["high"]
    for c in bc.CASES:
        assert s[1][c] == pytest.approx(2 * s[0][c])
    assert bc.share_of_revenue(ls, "mid", 10_000) == pytest.approx(s[0]["mid"] / 10_000)


@pytest.mark.parametrize(
    "x,n,want",
    [(7_125_122, 2, 7_100_000), (0.0941, 2, 0.094), (-38_851, 2, -39_000), (0, 2, 0)],
)
def test_sig(x, n, want):
    assert bc.sig(x, n) == pytest.approx(want)


@pytest.mark.parametrize(
    "x,n,want",
    [
        (7_125_122, 2, "$7.1M"),
        (10_988_206, 2, "$11M"),
        (218_470, 2, "$220k"),
        (176.11, 3, "$176"),
        (0.72, 2, "$0.72"),
        (-38_851, 2, "-$39k"),
        (1.0e9, 2, "$1.0B"),
    ],
)
def test_usd(x, n, want):
    assert bc.usd(x, n) == want
