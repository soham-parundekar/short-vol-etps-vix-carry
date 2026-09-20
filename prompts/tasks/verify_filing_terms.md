# Task — Verify every product term against its filing

## Parent phase

`prompts/phases/02_literature_review.md`, revisited in `04_data_source_discovery.md`.

## Objective

Establish that every product term the project asserts — daily leverage, fee,
benchmark index, wrapper, acceleration clause, leverage-change date — is read out of
the archived filing rather than recalled or taken from a secondary description.

## Why this is a separate task

Product terms are the factual backbone of the whole project: the leverage enters the
decay regression and the flow calculation, the fee enters the tracking validation, and
the acceleration clause is the entire subject of the survival analysis. A single wrong
fee makes the tracking test fail for a reason nobody will find. And these are exactly
the kind of number that is easy to remember approximately and hard to remember
exactly.

## Inputs

- `config/filings.yaml` — each entry lists the claims it is supposed to support
- `references/filings/**` — the archived documents

## Procedure

1. For each entry in `config/filings.yaml`, open the archived file.
2. Search it for each claim listed under `used_for`. Record the **verbatim** phrase
   that supports the claim, with enough surrounding text to be unambiguous.
3. Compare with the value in `config/config.yaml` under `products.*`.
4. Where they disagree, the filing wins. Update the configuration and log the change.
5. Where the archived document does not contain the claim — because the filing was
   amended, or the relevant passage is in a document not yet archived — find the
   document that does, add it to `config/filings.yaml`, and download it.
6. Set `verified: true` only for entries where every listed claim has been located in
   the text.
7. Write the extracted quotations to `reports/tables/filing_terms.csv` with columns
   `key, claim, value, quotation, document, verified`.

## Decision rule

A term is verified when it can be quoted. "It is well known that XIV charged 1.35%"
is not verification. If a term cannot be quoted from a primary document, it is stated
in the repository as unverified, with the best available source named, and any result
that depends on it is flagged.

## Validation

| Check | Pass | Failure |
|---|---|---|
| Coverage | every `used_for` claim has a quotation | any claim unquoted but marked verified |
| Agreement | configuration matches the filings | a silent disagreement |
| Dates | the leverage-change date matches the filing, and matches where the price data shows the break | dates disagree and it is not investigated |
| Provenance | every quotation names its document and is reproducible by search | a quotation that cannot be relocated |

## Output

`reports/tables/filing_terms.csv`; updates to `config/config.yaml` and
`config/filings.yaml`.

## Record

Disagreements found and resolved go in `docs/project_log.md`. Terms that remain
unverified go in `docs/limitations.md`, naming the results that depend on them.
