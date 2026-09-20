# Operation — Data quality review

## When to run

After any change to the acquisition or cleaning pipeline, after any re-download, and
before any phase that consumes a dataset for the first time.

## Inputs

The dataset in question, its entry in `docs/data_sources.md`, and the raw manifest.

## Procedure

**Shape and coverage**

- [ ] Row count — and does it reconcile with what it should be (trading days ×
      contracts, or days in the sample)?
- [ ] First and last date; do they match the source's documented range?
- [ ] Gaps: which trading days are missing, and why?
- [ ] Extra days: any date that is not a trading day?

**Values**

- [ ] Missing values per column, as a count and a share
- [ ] Zeros where a zero is impossible (a price, a divisor)
- [ ] Duplicated keys — inspect before dropping
- [ ] Stale runs: the same value repeated for several days. Legitimate for a rate,
      suspicious for a settlement price
- [ ] Range checks: VIX futures outside 8–90, open interest negative, high below low

**Distribution**

- [ ] Summary statistics against expectation. Is the mean of the index return
      negative, as a rolling short-term VIX futures index should be?
- [ ] The ten largest moves in each direction, each with a verdict: genuine event,
      data error, or construction artefact
- [ ] Autocorrelation of returns near zero; autocorrelation of squared returns high

**Provenance**

- [ ] Every file in the manifest; `verify_manifest()` clean
- [ ] Spot-check three values against the source directly

**Alignment**

- [ ] Do the datasets that get joined share a calendar? Check the intersection size
- [ ] Is any series in percent joined to one in decimals?

## What counts as done

A row appended to `reports/tables/data_quality.csv` recording counts for every check,
and every anomaly either explained or escalated. "No anomalies found" is recorded
explicitly — it is a result, and an empty section is indistinguishable from an
unperformed check.

## Escalation

- Value anomaly: investigate before deciding anything. Never delete first
- Coverage gap that affects the sample: document in `docs/limitations.md` and check
  whether the sample window should change
- Discrepancy against the source: re-download with `--force` and compare hashes; a
  changed hash means the vendor revised the file, which is itself worth recording
