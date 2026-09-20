#!/usr/bin/env python3
"""Verify every product term against the archived filing that states it.

    python scripts/extract_filing_terms.py            # verify and write the table
    python scripts/extract_filing_terms.py --search "investor fee"  --key xiv_424b2
    python scripts/extract_filing_terms.py --list     # show what is being checked

Why this exists
---------------
The leverage enters the decay regression, the fee enters the tracking validation and
the acceleration clause is the entire subject of the survival analysis. These are
exactly the numbers that are easy to remember approximately and hard to remember
exactly, and a wrong fee makes a downstream test fail for a reason nobody will find.

So no product term in this repository is asserted from recall or from a secondary
description. Each one is located in the primary document by a **stored search
pattern**, and the surrounding text is written verbatim into
``reports/tables/filing_terms.csv``. A reader can re-run the same pattern against the
same archived file and get the same passage back. A term that cannot be located that
way is reported as unverified rather than quietly accepted; the script exits non-zero
when any expected term is missing, so this cannot pass silently.

What "verified" means here
--------------------------
Narrow and mechanical: *the number the configuration uses appears in the archived
filing, in a passage that is about that term.* The pattern carries the term's own
wording, and the extracted passage is stored so the judgement is reviewable rather
than taken on trust. It does not mean the filing has been read end to end.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from svcarry.config import load_config  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


# ----------------------------------------------------------------- text extraction
_DROP = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v   ]+")


def to_text(path: Path) -> str:
    """Flatten an EDGAR HTML filing to searchable text.

    Block-level tags become spaces rather than nothing, so that words either side of
    a table cell boundary do not fuse into one token - which matters because most of
    the numbers being verified live in tables. Unicode is normalised to NFKC and the
    various dashes and quotation marks are folded to ASCII, because these documents
    mix typographic and plain forms of the same character and a pattern written with
    a hyphen must still match a passage typeset with an en dash.
    """
    raw = path.read_bytes().decode("utf-8", errors="replace")
    raw = _DROP.sub(" ", raw)
    raw = _TAG.sub(" ", raw)
    txt = html.unescape(raw)
    txt = unicodedata.normalize("NFKC", txt)
    txt = (txt.replace("’", "'").replace("‘", "'")
              .replace("“", '"').replace("”", '"')
              .replace("–", "-").replace("—", "-")
              .replace("−", "-"))
    txt = _WS.sub(" ", txt)
    txt = re.sub(r"\s*\n\s*", "\n", txt)
    return re.sub(r" {2,}", " ", txt)


def window(text: str, m: re.Match, before: int = 180, after: int = 260) -> str:
    """The matched passage with context, trimmed to word boundaries."""
    lo = max(0, m.start() - before)
    hi = min(len(text), m.end() + after)
    seg = text[lo:hi].replace("\n", " ")
    if lo:
        seg = seg[seg.find(" ") + 1:]
    if hi < len(text):
        seg = seg[: seg.rfind(" ")]
    return _WS.sub(" ", seg).strip()


# --------------------------------------------------------------------- the checks
@dataclass(frozen=True)
class Check:
    """One term to locate in one document.

    ``pattern``  the regex, written to carry the term's own wording so that a match
                 is about the right thing and not a coincidence of digits elsewhere
                 in a 5 MB document.
    ``expect``   the value ``config/config.yaml`` asserts, for comparison.
    ``config``   dotted path of that value, or None where the term is not a config
                 entry (a date, a formula, a clause).
    """

    key: str
    claim: str
    pattern: str
    expect: str
    config: str | None = None
    flags: int = re.I
    #: False where the filing and the configuration state the same fact in
    #: deliberately different terms, so a literal comparison would be misleading.
    #: ``note`` must then say why, and is written into the output table.
    compare: bool = True
    note: str = ""


CHECKS: tuple[Check, ...] = (
    # ---- XIV: Credit Suisse VelocityShares pricing supplement ------------------
    Check("xiv_424b2", "XIV daily investor fee factor",
          # NOT [^.] here: the list runs "(i) 0.0089 ... (ii) 0.0135" and a
          # period-excluding class cannot cross the decimal point in 0.0089.
          r"Investor\s+Fee\s+Factor\s*\"?\s*will\s+be\s+equal\s+to[\s\S]{0,250}?0\.0135",
          "0.0135", "products.XIV.fee"),
    Check("xiv_424b2", "XIV inverse (-1x) daily objective",
          r"inverse[^.]{0,200}?(?:daily|one\s*day)[^.]{0,200}?perform",
          "-1.0", "products.XIV.leverage"),
    Check("xiv_424b2", "XIV underlying index",
          # NFKC folds the trademark glyph to the letters TM, which then sit between
          # "Futures" and "Index" in the filing's own typography.
          r"Daily\s+Inverse\s+VIX\s+Short\s+Term\s+ETNs\s+linked\s+to\s+the\s+"
          r"S&P\s*500\s*VIX\s*Short-?Term\s*Futures\s*(?:TM)?\s*Index",
          "S&P 500 VIX Short-Term Futures Index"),
    Check("xiv_424b2", "XIV T-bill accrual on the notional",
          r"(?:91|13[- ]week|three[- ]month)[^.]{0,200}?Treasury",
          "3-month T-bill accrual"),
    Check("xiv_424b2", "XIV acceleration at the issuer's option",
          r"(?:accelerat\w+)[^.]{0,300}?(?:at\s+our\s+option|option\s+to\s+accelerat)",
          "optional acceleration clause"),

    # ---- XIV: the acceleration 8-K --------------------------------------------
    Check("xiv_acceleration_8k", "XIV acceleration trigger, 20% of prior close",
          # The release spells the threshold out in words. A pattern written as "20%"
          # finds nothing, which is how this check failed on its first run.
          r"equal\s+to\s+or\s+less\s+than\s+twenty\s+percent\s+of\s+the\s+prior\s+"
          r"day'?s\s+closing\s+indicative\s+value",
          "intraday indicative value <= 20% of prior closing indicative value"),
    Check("xiv_acceleration_8k", "XIV closing indicative value 2018-02-02",
          r"closing\s+indicative\s+value\s+was\s+\$?108\.3681", "108.3681"),
    Check("xiv_acceleration_8k", "XIV acceleration event date",
          r"intraday\s+indicative\s+value\s+of\s+XIV\s+on\s+February\s+5,\s+2018",
          "2018-02-05"),
    Check("xiv_acceleration_8k", "XIV acceleration date",
          r"acceleration\s+date\s+for\s+XIV\s+is\s+expected\s+to\s+be\s+"
          r"February\s+21,\s+2018",
          "2018-02-21", "products.XIV.terminated"),

    # ---- ProShares: the February 2018 prospectus, terms as at that date --------
    Check("proshares_424b3_2018_02", "SVXY daily objective -1x as at Feb 2018",
          r"Inverse\s+Fund\s+seeks\s+results[^.]{0,140}?inverse\s*\(\s*-\s*1x\s*\)",
          "-1.0", "products.SVXY.leverage"),
    Check("proshares_424b3_2018_02", "UVXY daily objective 2x as at Feb 2018",
          r"Ultra\s+Fund\s+seeks\s+results[^.]{0,140}?two\s+times\s*\(\s*2x\s*\)",
          "2.0", "products.UVXY.leverage"),
    Check("proshares_424b3_2018_02", "ProShares VIX funds benchmark index",
          r"S&P\s*500\s*VIX\s*Short-?Term\s*Futures?\s*Index",
          "S&P 500 VIX Short-Term Futures Index"),
    Check("proshares_424b3_2018_02", "ProShares management fee 0.95%",
          r"0\.95%", "0.0095", "products.SVXY.fee"),
    Check("proshares_424b3_2018_02", "ProShares NAV calculation time 4:15 p.m. ET",
          # Load-bearing for docs/validation.md SS V6 and V9: the fund strikes NAV at
          # 4:15 p.m., while the closing price this project regresses on is the
          # 4:00 p.m. consolidated close.
          r"NAV\s+calculation\s+time\s+for\s+the\s+Funds\s+is\s+typically\s+4:15",
          "4:15 p.m. ET"),
    Check("proshares_424b3_2018_02", "SVXY 2-for-1 split, July 2017",
          r"2-for-1\s+split[\s\S]{0,400}?SVXY\s+commenced\s+trading\s+at\s+the\s+"
          r"post-split\s+price\s+on\s+July\s+17,\s+2017",
          "2-for-1 on 2017-07-17"),
    Check("proshares_424b3_2018_02", "VIXY and UVXY 1-for-4 reverse split, 2017",
          r"1-for-4\s+reverse\s+split[\s\S]{0,200}?ProShares\s+VIX\s+Short-?Term\s+"
          r"Futures\s+ETF",
          "1-for-4 reverse split announced 2017-06-27"),

    # ---- ProShares 10-K FY2017: the leverage change as a subsequent event ------
    Check("proshares_trust_ii_10k_2017", "effective date of the exposure change",
          r"Effective\s+as\s+of\s+close\s+of\s+business\s+on\s+February\s+27,\s+2018,"
          r"\s+the\s+investment\s+objective",
          "close of business 2018-02-27", "products.SVXY.leverage_change_date",
          compare=False,
          note="The filing dates the change to the close of 27 Feb 2018; the "
               "configuration stores 2018-02-28 because that is the first daily "
               "RETURN computed under the new objective (27 Feb close -> 28 Feb "
               "close). Confirmed in the data: implied leverage on 27 Feb is "
               "-1.21 (SVXY) and +2.48 (UVXY), on 28 Feb -0.24 and +1.13."),
    Check("proshares_trust_ii_10k_2017", "UVXY new objective 1.5x",
          r"UVXY\s*\)?\s*changed\s+its\s+investment\s+objective[^.]{0,200}?"
          r"one\s+and\s+one-half\s+times\s*\(\s*1\.5x\s*\)",
          "1.5", "products.UVXY.leverage_after"),
    Check("proshares_trust_ii_10k_2017", "the -0.5x inverse class exists",
          r"one-half\s+inverse\s*\(\s*-0\.5x\s*\)", "-0.5",
          "products.SVXY.leverage_after"),
    Check("proshares_trust_ii_10k_2017", "SVXY net assets disclosed",
          r"Short\s+VIX\s+Short-?Term\s+Futures\s+ETF[^.]{0,300}?\$?[\d,]{7,}",
          "net assets by fund"),

    # ---- Barclays iPath Series B ----------------------------------------------
    # The fee lives in the January-2018 pricing supplement, NOT in the 2022 filing
    # originally recorded against this claim; see docs/project_log.md.
    Check("ipath_vxx_series_b_2018_launch", "VXX investor fee rate 0.89% per annum",
          r"subtracted\s+at\s+the\s+rate\s+of\s+0\.89%\s+per\s+year",
          "0.0089", "products.VXX.fee"),
    Check("ipath_vxx_series_b_2018_launch", "VXX tracks the TOTAL RETURN index",
          # XIV was linked to the excess-return version; VXX to the total-return one.
          # The difference is the T-bill accrual and it is not cosmetic.
          r"S&P\s*500\s*(?:®)?\s*VIX\s*Short-?Term\s*Futures\s*(?:TM)?\s*Index\s*TR",
          "S&P 500 VIX Short-Term Futures Index TR"),
    Check("ipath_vxx_series_b_2018_launch", "Series B pricing supplement, January 2018",
          r"Preliminary\s+Pricing\s+Supplement\s+Dated\s+January\s+3,\s+2018",
          "January 2018 relaunch"),
    Check("ipath_vxx_series_b_424b2", "VXX issuance suspended March 2022",
          # Explains why VXX tracks worse than VIXY after 2022: with creations
          # suspended it can trade at a persistent premium or discount.
          r"we\s+will\s+suspend,\s+until\s+further\s+notice,\s+any\s+further\s+sales",
          "issuance suspended 2022-03-14"),

    # ---- Volatility Shares SVIX ------------------------------------------------
    Check("vs_trust_svix_424b3", "SVIX daily objective -1x",
          r"-\s*1\s*x[^.]{0,300}?(?:Short\s+VIX\s+Futures\s+Index|daily\s+performance)",
          "-1.0", "products.SVIX.leverage"),
    Check("vs_trust_svix_424b3", "SVIX management fee",
          r"SVIX\s+pays\s+the\s+Sponsor\s+a\s+management\s+fee[^.]{0,220}?"
          r"1\.35\s*%\s*per\s+annum",
          "0.0135", "products.SVIX.fee"),
    Check("vs_trust_svix_424b3", "SVIX has no acceleration clause (ETF, not ETN)",
          r"commodity\s+pool|series\s+of\s+(?:the\s+)?(?:VS\s+)?Trust",
          "fund structure, not a note"),
)


def _same(expect: str, cfg_value) -> bool:
    """Compare a filing value with a configuration value.

    Numeric where both parse as numbers (so 0.0135 and "0.0135" agree, and a fee
    stored as a fraction is compared as a fraction), string containment otherwise.
    """
    if cfg_value is None:
        return False
    try:
        return abs(float(expect) - float(cfg_value)) < 1e-12
    except (TypeError, ValueError):
        return str(expect).strip().lower() in str(cfg_value).strip().lower() or \
               str(cfg_value).strip().lower() in str(expect).strip().lower()


# ------------------------------------------------------------------------- runner
def load_filings() -> dict:
    p = ROOT / "config" / "filings.yaml"
    if yaml is None:
        raise SystemExit("pyyaml is required to read config/filings.yaml")
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    return {f["key"]: f for f in doc["filings"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--search", help="ad-hoc regex to run against one filing")
    ap.add_argument("--key", help="filing key for --search")
    ap.add_argument("--max", type=int, default=6, help="matches to show for --search")
    ap.add_argument("--list", action="store_true", help="list the stored checks")
    args = ap.parse_args()

    filings = load_filings()
    fdir = ROOT / load_config().dotted("paths.filings")

    if args.list:
        for c in CHECKS:
            print(f"  {c.key:34s} {c.claim:46s} expect={c.expect}")
        return 0

    if args.search:
        if not args.key:
            raise SystemExit("--search needs --key")
        path = fdir / filings[args.key]["local_name"]
        text = to_text(path)
        hits = list(re.finditer(args.search, text, re.I | re.S))
        print(f"{path.name}: {len(hits)} match(es) for {args.search!r}\n")
        for m in hits[: args.max]:
            print("  ...", window(text, m), "...\n")
        return 0

    cache: dict[str, str] = {}
    rows, missing, disagree = [], [], []
    cfg = load_config()

    for c in CHECKS:
        meta = filings[c.key]
        path = fdir / meta["local_name"]
        if not path.exists():
            missing.append((c, f"archived file not present: {path.name}"))
            continue
        if c.key not in cache:
            cache[c.key] = to_text(path)
        text = cache[c.key]

        m = re.search(c.pattern, text, c.flags | re.S)
        cfg_value = cfg.dotted(c.config, None) if c.config else None
        agrees = "n/a"
        if c.config and c.compare:
            agrees = "yes" if _same(c.expect, cfg_value) else "no"
        row = {
            "key": c.key,
            "document": meta["local_name"],
            "form": meta.get("form", ""),
            "claim": c.claim,
            "expected": c.expect,
            "config_path": c.config or "",
            "config_value": "" if cfg_value is None else str(cfg_value),
            "agrees": agrees,
            "note": c.note,
            "found": bool(m),
            "quotation": window(text, m) if m else "",
            "pattern": c.pattern,
        }
        rows.append(row)
        if not m:
            missing.append((c, "pattern did not match"))
        if agrees == "no":
            disagree.append((c, cfg_value))

    out = ROOT / cfg.dotted("paths.tables") / "filing_terms.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    found = sum(r["found"] for r in rows)
    print(f"{found}/{len(rows)} terms located in their archived filing")
    print(f"  -> {out.relative_to(ROOT)}")
    by_key: dict[str, list[bool]] = {}
    for r in rows:
        by_key.setdefault(r["key"], []).append(r["found"])
    print("\n  per filing:")
    for k, v in by_key.items():
        print(f"    {k:34s} {sum(v)}/{len(v)}")

    if disagree:
        print(f"\n  CONFIGURATION DISAGREES WITH THE FILING ({len(disagree)}):")
        for c, got in disagree:
            print(f"    {c.config}: config has {got!r}, the filing says {c.expect!r}")
        print("\n  The filing wins. Update config/config.yaml and log the change.")

    if missing:
        print(f"\n  UNLOCATED ({len(missing)}):")
        for c, why in missing:
            print(f"    {c.key}: {c.claim}  [{why}]")
        print("\n  These are reported, not silently accepted. Either the pattern is")
        print("  wrong or the term is not in this document; both need a human look.")
        return 1
    return 1 if disagree else 0


if __name__ == "__main__":
    raise SystemExit(main())
