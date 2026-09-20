"""Tests for how the two Cboe futures archives are merged into one panel.

Written after three defects found by inspecting the assembled panel rather than by
watching the code run. All three shared the property that makes data bugs expensive:
the pipeline completed, produced a plausibly-shaped frame, and lost real prices in
silence.

Defect 1 - a disclaimer preamble. From the July-2013 expiry onward the legacy Cboe
archive puts a one-line legal notice above the CSV header. ``_parse_vx_file`` read
that line as the header, failed its required-column check, and ``load_vx_panel``
swallowed the exception. Fourteen files were dropped without a word.

Defect 2 - swallowing the failure at all. A file that cannot be parsed is now an
error, not a shrug. This is the test that would have caught defect 1 on the day it
was introduced.

Defect 3 - placeholder settlement prices winning the merge. Cboe's modern per-expiry
archive publishes ``Settle = 0`` for every session from 2013-01-02 to 2013-07-19
while populating ``Close`` normally. Zeroes are correctly converted to NaN, but the
conversion ran *after* de-duplication and the rule was "modern wins", so the empty
modern row beat the legacy row that carried the real price. The result was 95
consecutive sessions in 2013 with no contract priced at all, which the index
reconstruction reports as NaN and the index level then forward-fills across.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from svcarry.data import cboe
from svcarry.data.cboe import _parse_vx_file, load_vx_panel

HEADER = "Trade Date,Futures,Open,High,Low,Close,Settle,Change,Total Volume,EFP,Open Interest"
DISCLAIMER = (
    "CFE data is compiled for the convenience of site visitors and is furnished "
    "without responsibility for accuracy."
)


def _modern_rows(settle="15.60"):
    return [
        f"2013-01-02,F (Jan 2013),16.8000,16.8000,15.5000,15.6000,{settle},0,97535,3632,120663",
        f"2013-01-03,F (Jan 2013),15.7500,16.0000,15.3000,15.9000,{settle},0,59683,3630,118689",
    ]


def _legacy_rows(settle_a="15.60", settle_b="15.90"):
    return [
        f"01/02/2013,F (Jan 13),16.80,16.80,15.50,15.60,{settle_a},-2.10,97535,3632,120663",
        f"01/03/2013,F (Jan 13),15.75,16.00,15.30,15.90,{settle_b},0.30,59683,3630,118689",
    ]


def _write(tmp_path, name, lines):
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ------------------------------------------------------------------ parsing
def test_parses_a_file_with_a_disclaimer_preamble(tmp_path):
    """The exact shape that silently dropped fourteen legacy files."""
    p = _write(tmp_path, "VXL_2013-07-17.csv", [DISCLAIMER, HEADER] + _legacy_rows())
    df = _parse_vx_file(p, pd.Timestamp("2013-07-17"))
    assert len(df) == 2
    assert df["settle"].tolist() == [15.60, 15.90]
    assert df["date"].tolist() == [pd.Timestamp("2013-01-02"), pd.Timestamp("2013-01-03")]


def test_parses_a_file_with_no_preamble(tmp_path):
    p = _write(tmp_path, "VX_2013-01-16.csv", [HEADER] + _modern_rows())
    df = _parse_vx_file(p, pd.Timestamp("2013-01-16"))
    assert len(df) == 2
    assert df["date"].iloc[0] == pd.Timestamp("2013-01-02")


def test_us_and_iso_dates_are_parsed_without_swapping_day_and_month(tmp_path):
    """03/04/2013 is 4 March in the legacy files and must not become 3 April."""
    legacy = _write(tmp_path, "VXL_2013-05-22.csv",
                    [HEADER, "03/04/2013,K (May 13),14.0,14.2,13.9,14.1,14.05,0,10,0,100"])
    iso = _write(tmp_path, "VX_2013-05-22.csv",
                 [HEADER, "2013-03-04,K (May 2013),14.0,14.2,13.9,14.1,14.05,0,10,0,100"])
    a = _parse_vx_file(legacy, pd.Timestamp("2013-05-22"))
    b = _parse_vx_file(iso, pd.Timestamp("2013-05-22"))
    assert a["date"].iloc[0] == pd.Timestamp("2013-03-04")
    assert b["date"].iloc[0] == pd.Timestamp("2013-03-04")


def test_a_file_with_no_header_at_all_still_raises(tmp_path):
    p = _write(tmp_path, "VX_2013-01-16.csv", ["not,a,futures,file", "1,2,3,4"])
    with pytest.raises(ValueError, match="missing expected columns"):
        _parse_vx_file(p, pd.Timestamp("2013-01-16"))


# ------------------------------------------------------------------- merge
@pytest.fixture
def panel_dir(tmp_path, monkeypatch):
    """Point load_vx_panel at a throwaway directory."""
    d = tmp_path / "cboe" / "vx"
    d.mkdir(parents=True)
    monkeypatch.setattr(cboe, "_raw_dir", lambda: tmp_path)
    return d


def test_a_placeholder_settle_loses_to_a_real_legacy_settle(panel_dir):
    """The defect that left 95 sessions of 2013 with no priced contract.

    The modern file has Close but ``Settle = 0``; the legacy companion has both.
    The merged panel must carry the legacy settlement price.
    """
    _write(panel_dir, "VX_2013-01-16.csv", [HEADER] + _modern_rows(settle="0"))
    _write(panel_dir, "VXL_2013-01-16.csv", [DISCLAIMER, HEADER] + _legacy_rows())

    panel = load_vx_panel(start="2013-01-01", end="2013-01-31")
    assert len(panel) == 2
    assert panel["settle"].tolist() == [15.60, 15.90]
    assert panel["settle"].notna().all(), "a placeholder row won the merge"


def test_a_real_modern_settle_beats_a_legacy_settle(panel_dir):
    """Where both archives carry a price the modern file is authoritative.

    This is not cosmetic. On 2013-05-28 the legacy archive prints 10.25 for the
    February-2014 contract where the modern file prints 20.10; the rest of the curve
    that day runs 15.20 to 19.60 in monotone contango, so 10.25 is a bad print. One
    disagreement in 13,127 overlapping cells, and the rule resolves it correctly.
    """
    _write(panel_dir, "VX_2013-01-16.csv", [HEADER] + _modern_rows(settle="20.10"))
    _write(panel_dir, "VXL_2013-01-16.csv", [DISCLAIMER, HEADER] + _legacy_rows("10.25", "10.25"))

    panel = load_vx_panel(start="2013-01-01", end="2013-01-31")
    assert panel["settle"].tolist() == [20.10, 20.10]


def test_zero_settle_becomes_nan_not_a_minus_one_hundred_percent_return(panel_dir):
    """With no legacy companion the cell is missing, never zero."""
    _write(panel_dir, "VX_2013-01-16.csv", [HEADER] + _modern_rows(settle="0"))
    panel = load_vx_panel(start="2013-01-01", end="2013-01-31")
    assert panel["settle"].isna().all()
    assert not (panel["settle"] == 0).any()


def test_an_unparseable_file_raises_rather_than_being_dropped(panel_dir):
    _write(panel_dir, "VX_2013-01-16.csv", [HEADER] + _modern_rows())
    _write(panel_dir, "VX_2013-02-13.csv", ["garbage,header", "1,2"])
    with pytest.raises(ValueError, match="could not be parsed"):
        load_vx_panel(start="2013-01-01", end="2013-12-31")


def test_strict_false_warns_and_keeps_going(panel_dir):
    _write(panel_dir, "VX_2013-01-16.csv", [HEADER] + _modern_rows())
    _write(panel_dir, "VX_2013-02-13.csv", ["garbage,header", "1,2"])
    with pytest.warns(RuntimeWarning, match="could not be parsed"):
        panel = load_vx_panel(start="2013-01-01", end="2013-12-31", strict=False)
    assert len(panel) == 2
    assert len(panel.attrs["parse_failures"]) == 1


def test_rows_dated_after_their_own_expiry_are_dropped(panel_dir):
    _write(panel_dir, "VX_2013-01-16.csv", [HEADER] + _modern_rows() + [
        "2013-01-18,F (Jan 2013),1.0,1.0,1.0,1.0,1.0,0,0,0,0",
    ])
    panel = load_vx_panel(start="2013-01-01", end="2013-12-31")
    assert (panel["date"] <= panel["expiry"]).all()
    assert len(panel) == 2
