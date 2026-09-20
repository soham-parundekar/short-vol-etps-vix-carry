# Limitations

Everything the project knows to be imperfect, in one place, with the results each
item bears on. The test for inclusion is whether a careful reader who found it
themselves would feel it had been concealed.

Items are stated at the strength the evidence supports. Where something is
unexplained it says so rather than offering a mechanism that has not been shown.

---

## L1. The reconstructed index carries measurement noise against the traded products

**Magnitude.** Roughly 120 bp a day before 26 October 2020, roughly 30 bp a day
after. Fitted slopes of product on index: 0.87 over 2011-2017, 0.96 over 2019 to
October 2020, 0.98 after.

**Cause, as far as it is established.** The dominant term is that the two series were
measured fifteen minutes apart. Cboe struck the VX daily settlement at 3:15 p.m. CT
until 26 October 2020 and at 3:00 p.m. CT after; 3:00 p.m. CT is 4:00 p.m. ET, which
is when the products' consolidated closing price is struck. `docs/validation.md` V6
dates the break in the data and V9 shows it at its most extreme, on 5 February 2018,
where 57.5% of the day's index move happened after 4:00 p.m.

**Not fully explained.** The lead-lag coefficient dies after 2015 and the
contemporaneous slope improves around 2019, both before the settlement-time change.
No mechanism for either has been demonstrated.

**What it bounds.** Every result computed on the pre-2020 sample. An effect whose
economic significance depends on differences smaller than ~120 bp a day in that
period is not supported by this data. This is a property of the reconstruction, not
of the strategy, and it does not bias a return series - it widens the interval around
any comparison against a traded product.

---

## L2. VXX is linked to the total-return index; the reconstruction is excess-return

The iPath Series B pricing supplement states that the ETNs are linked to the
"S&P 500 VIX Short-Term Futures Index **TR**". XIV was linked to the excess-return
version. This project reconstructs ER (the futures-only return), with a total-return
variant available when a T-bill accrual is supplied.

**Consequence.** VXX's mean tracking residual against the ER reconstruction carries a
known positive bias of approximately the T-bill rate less the 0.89% fee. At 2023-2025
rates that is on the order of 1-2 bp a day.

**What it bears on.** The *mean* residual in `reports/tables/index_tracking.csv` for
VXX only. It does not affect the slope, the tracking error, or any result that rests
on covariation rather than on level.

---

## L3. VXX has been closed to issuance since March 2022

Barclays suspended further sales and issuances effective 14 March 2022. With
creations switched off, the arbitrage that holds an ETN near its indicative value
does not operate, and the issuer's own amendment says the notes may trade at a
premium or discount.

**Consequence.** VXX's post-2022 price series is not a clean proxy for index
performance. Its daily tracking error over 2022-2026 is 101 bp against VIXY's 28 bp
over the identical window.

**What it bears on.** Any use of VXX as a validation benchmark after March 2022.
VIXY is the appropriate +1x comparator for that period and is used as such.

---

## L4. Two product terms rest on documents that may have been superseded

| Term | Value used | Source | Risk |
|---|---|---|---|
| VXX investor fee | 0.89%/yr | iPath Series B **preliminary** pricing supplement, 3 Jan 2018 | The document states on its face that the information "is not complete and may be changed". The final supplement has not been archived. |
| SVIX management fee | 1.35%/yr | VS Trust 424B3, 28 Jan 2022 (launch) | A later amendment reducing the fee has not been checked. The configuration previously carried 1.29%, which could not be located in any archived filing. |

**What they bear on.** The mean tracking residual for those two products. Both are
sub-basis-point-per-day effects against tracking errors of 51-101 bp. Neither enters
the strategy, the tail model, or the survival analysis.

---

## L5. The pre-2013 futures history comes from a different Cboe archive

Contracts expiring before roughly January 2013 are served only by a legacy archive
keyed by month code rather than by settlement date, and dated `MM/DD/YYYY` rather
than ISO. The two archives were cross-validated on 13,127 overlapping cells and
agree in 13,126 (`docs/validation.md` V4), so this is a documented splice rather than
an unexamined one - but it is a splice.

**What it bears on.** Anything computed on 2008-2012. The single disagreement found
was a bad legacy print, adjudicated by curve shape and resolved in favour of the
modern archive.

---

## L6. Reconstructed, not licensed

The index used throughout is a reconstruction from public futures settlement prices,
not the published S&P Dow Jones Indices series. The roll convention was selected on
evidence (`docs/validation.md` V5) rather than taken from the licensed methodology
document, of which only the roll-period definition has been obtained.

**What it bears on.** Everything. It is also what makes the project possible: the
reconstruction extends before the products existed, is free of product fees, and
exposes its own inputs. The tracking validation in V5, V6 and V9 is the evidence
offered in place of a licence.

---

## L7. Market prices, not NAV

The product series used are consolidated closing prices from a free provider,
split-adjusted. Net asset values are not used, because a long free history of them is
not available. L1 is the direct consequence. On stressed days the closing price can
also carry a premium or discount to fair value that is not measured here - 5 February
2018 being the clearest case, where three products agreed with each other to 2.25
percentage points, which argues against large *idiosyncratic* distortion but does not
rule out a common one.

---

## L8. Open questions carried forward

1. The 2016 and 2019 steps in the tracking-error series are unexplained (L1).
2. Post-October-2020 slopes are 0.985, 0.991 and 0.971 rather than 1.000. Whether the
   residual 1-3% is product tracking difficulty, fee drag mis-attributed to the
   slope, or remaining index noise is not resolved.
