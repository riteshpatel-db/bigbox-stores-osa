"""The Genie scorer's result-set comparison (src/genie/score.py)."""

from score import compare

REF_COLS = ["region", "osa"]
REF = [["EAST", "0.9285"], ["WEST", "0.9290"]]


def test_order_and_extra_columns_and_names_do_not_matter():
    gen = [["WEST", "123", "0.929"], ["EAST", "456", "0.9285"]]
    assert compare(REF_COLS, REF, ["r", "n", "x"], gen)[0]


def test_numeric_tolerance_is_half_a_percent():
    assert compare(REF_COLS, REF, REF_COLS, [["EAST", "0.9320"], ["WEST", "0.9290"]])[0]
    assert not compare(REF_COLS, REF, REF_COLS, [["EAST", "0.9340"], ["WEST", "0.9290"]])[0]


def test_percentages_match_ratios_and_are_reported():
    ok, why = compare(REF_COLS, REF, REF_COLS, [["EAST", "92.85"], ["WEST", "92.90"]])
    assert ok and "percentage" in why


def test_row_count_and_row_pairing_must_match():
    assert not compare(REF_COLS, REF, REF_COLS, REF + [["SOUTH", "0.9"]])[0]
    # each column matches as a set, but the pairs are swapped (values > 0.5 % apart)
    ref = [["EAST", "0.90"], ["WEST", "0.95"]]
    assert not compare(REF_COLS, ref, REF_COLS, [["EAST", "0.95"], ["WEST", "0.90"]])[0]


def test_timestamp_at_midnight_equals_date_and_text_is_case_insensitive():
    ref = [["2026-09-01T00:00:00.000Z", "Dairy", "4"]]
    assert compare(["m", "c", "v"], ref, ["m", "c", "v"], [["2026-09-01", "dairy", "4.0"]])[0]
    assert not compare(["m", "c", "v"], ref, ["m", "c", "v"], [["2026-09-02", "Dairy", "4"]])[0]
