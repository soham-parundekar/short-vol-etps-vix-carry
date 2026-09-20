"""Tests for the two Cboe futures endpoints and their different file conventions.

Cboe serves the VX contract history from two places. The modern per-expiry endpoint
covers roughly 2013 onward and dates rows in ISO order; a legacy archive covers the
earlier contracts, is keyed by CME month code and two-digit year, and dates rows in US
order. Both land in the same local file naming so nothing downstream needs to know
which one served a contract.

The date-format test is the one that matters. A file whose first rows read
``03/04/2013`` is ambiguous, and letting pandas infer would silently swap day and
month for part of the sample - which would corrupt the roll calendar alignment in a
way that is very hard to see afterwards.
"""

from __future__ import annotations

import pandas as pd
import pytest

from svcarry.data.cboe import LEGACY_VX_URL, VX_URL, _parse_vx_file, legacy_vx_url


def test_legacy_url_uses_the_expiry_month_code():
    # A VX contract settles inside its own expiry month, so the code comes from the
    # settlement date directly.
    assert legacy_vx_url("2013-02-13").endswith("CFE_G13_VX.csv")
    assert legacy_vx_url("2008-03-19").endswith("CFE_H08_VX.csv")
    assert legacy_vx_url("2018-02-14").endswith("CFE_G18_VX.csv")
    assert legacy_vx_url("2009-12-16").endswith("CFE_Z09_VX.csv")
    assert legacy_vx_url("2011-01-19").endswith("CFE_F11_VX.csv")


def test_url_templates_are_distinct_hosts_paths():
    assert "historical_data/VX" in VX_URL
    assert "archive/volume-and-price" in LEGACY_VX_URL


_HEADER = ("Trade Date,Futures,Open,High,Low,Close,Settle,Change,"
           "Total Volume,EFP,Open Interest\n")


def _write(tmp, name, rows):
    p = tmp / name
    p.write_text(_HEADER + "".join(rows), encoding="utf-8")
    return p


def test_modern_iso_dates_parse(tmp_path=None):
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    p = _write(tmp, "VX_2018-02-14.csv", [
        "2018-02-02,G (Feb 2018),13.10,13.60,12.90,13.00,13.05,0.10,50000,0,300000\n",
        "2018-02-05,G (Feb 2018),13.05,29.00,13.00,28.00,28.50,15.45,90000,0,280000\n",
        "2018-02-06,G (Feb 2018),28.00,30.00,22.00,23.00,23.20,-5.30,80000,0,260000\n",
    ])
    df = _parse_vx_file(p, pd.Timestamp("2018-02-14"))
    assert list(df["date"]) == [pd.Timestamp("2018-02-02"), pd.Timestamp("2018-02-05"),
                               pd.Timestamp("2018-02-06")]
    assert df["settle"].iloc[1] == pytest.approx(28.50)
    assert (df["expiry"] == pd.Timestamp("2018-02-14")).all()


def test_legacy_us_dates_parse_without_day_month_swap():
    """03/04/2013 must be 4 March, not 3 April."""
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    p = _write(tmp, "VX_2013-03-20.csv", [
        "03/04/2013,H (Mar 13),14.10,14.60,13.90,14.00,14.05,0.10,5000,0,30000\n",
        "03/05/2013,H (Mar 13),14.05,14.20,13.80,13.90,13.95,-0.10,4800,0,30500\n",
        "03/11/2013,H (Mar 13),13.90,14.00,13.60,13.70,13.75,-0.20,4600,0,31000\n",
    ])
    df = _parse_vx_file(p, pd.Timestamp("2013-03-20"))
    assert list(df["date"]) == [pd.Timestamp("2013-03-04"), pd.Timestamp("2013-03-05"),
                               pd.Timestamp("2013-03-11")]
    # every row is in March; an inferred parse would have put the first in April
    assert (df["date"].dt.month == 3).all()


def test_zero_settlement_becomes_missing_not_a_price():
    """Cboe writes 0.0000 before a contract trades; a zero price would print -100%."""
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    p = _write(tmp, "VX_2008-03-19.csv", [
        "09/21/2007,H (Mar 08),0.00,0.00,0.00,0.00,0.00,0.00,0,0,0\n",
        "09/24/2007,H (Mar 08),19.37,19.37,19.37,19.37,19.50,19.50,186,0,186\n",
    ])
    df = _parse_vx_file(p, pd.Timestamp("2008-03-19"))
    # _parse_vx_file keeps raw values; the zero screen happens in load_vx_panel, so
    # here we assert the value survives parsing and is recognisably a placeholder.
    assert df["settle"].iloc[0] == 0.0
    assert df["settle"].iloc[1] == pytest.approx(19.50)


def test_rows_after_expiry_are_visible_to_the_cleaner():
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    p = _write(tmp, "VX_2013-03-20.csv", [
        "03/19/2013,H (Mar 13),13.90,14.00,13.60,13.70,13.75,-0.20,4600,0,31000\n",
        "03/20/2013,H (Mar 13),0.00,0.00,0.00,0.00,13.80,0.05,0,0,0\n",
        "03/21/2013,H (Mar 13),0.00,0.00,0.00,0.00,0.00,0.00,0,0,0\n",
    ])
    df = _parse_vx_file(p, pd.Timestamp("2013-03-20"))
    assert len(df) == 3                                  # parser keeps everything
    assert (df["date"] > df["expiry"]).sum() == 1        # cleaner drops this one
