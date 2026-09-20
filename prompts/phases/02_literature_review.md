# Phase 02 — Literature and market-structure review

## 1. Objective

Understand the mechanism well enough to design a test of it, and establish exactly
what is already known so that the project's contribution can be stated honestly
rather than assumed. End state: a literature review that a reader can use to place
this project, and a set of archived primary documents from which every product term
asserted anywhere in the repository can be checked.

## 2. Context

The subject is short-volatility exchange-traded products written on the S&P 500 VIX
Short-Term Futures Index, the February 2018 failure of XIV, and the volatility risk
premium those products harvested. There is a substantial academic literature on the
variance risk premium, a smaller one on leveraged-ETF rebalancing mechanics, and at
least one careful study of the 2018 episode itself. The project must not re-derive
what is established, and must not claim as novel what is not.

## 3. Inputs

- The environment constraints from Phase 01 (which hosts are reachable)
- `config/filings.yaml` — created or extended in this phase

## 4. Tasks

1. Map the four literatures the project touches:
   - the variance/volatility risk premium and its compensation for jump risk
   - VIX futures term structure, roll yield, and the construction of the S&P indices
   - leveraged and inverse ETP mechanics: daily rebalancing, volatility decay,
     end-of-day flow and price impact
   - conditional extreme value theory, GARCH filtering, and growth-optimal sizing
     under fat tails
2. For the February 2018 episode specifically, find and read the careful prior work.
   Establish what it demonstrates, so the project builds on it rather than repeating
   it.
3. Locate the primary documents on EDGAR: the XIV pricing supplement and the
   acceleration announcement, the ProShares Trust II annual report and the prospectus
   in force in February 2018, the iPath VXX pricing supplement, the SVIX prospectus.
   Record each in `config/filings.yaml` with the **specific claim** it supports.
4. Obtain the index methodology document and extract the roll rules verbatim.
5. Write `docs/literature_review.md`. For each source: citation, URL or DOI, main
   contribution, data and method used, limitations, and how this project relates to
   it. Do not include a source that is never used.
6. Write `references/references.bib`.

## 5. Tools and methods

Web search and fetch; EDGAR full-text search; the archived-filing downloader in
`svcarry.data.edgar`. Where a document cannot be retrieved directly, record what is
known and mark the claim as unverified rather than asserting it.

## 6. Execution instructions

Read the primary documents rather than descriptions of them. A summary of a filing is
not the filing; a blog post's account of a fee is not the fee. Where a term has been
taken from a secondary source because the primary one could not be retrieved, mark it
`verified: false` in `config/filings.yaml` and re-check it in Phase 04.

Distinguish, in the writing, between: established fact, finding from a specific
paper's data, that paper's interpretation, and this project's own methodological
choice. Never blur the four.

**Never invent a citation.** If a half-remembered paper cannot be located, it does not
go in the bibliography.

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| Every citation resolvable | every entry has a working URL/DOI | one entry pending verification, flagged | any entry that cannot be located |
| Filings archived | each file downloaded, hashed, indexed | a filing retrievable only in part | a term asserted with no source |
| Terms traceable | every leverage, fee and clause maps to a filing key | — | a number with no provenance |
| Contribution statement | states what is established elsewhere and what is new here | — | claims novelty for something already published |
| Bibliography hygiene | every entry cited in the text | — | padding |

## 8. Self-review

- Is any source in the bibliography that the text never uses?
- Is any claim in the review stated more strongly than its source supports?
- Has the prior work on the 2018 episode been represented accurately, including the
  parts that anticipate this project's findings?
- Are the four categories (fact / finding / interpretation / own choice) actually
  distinguishable in the prose?

## 9. Deliverables

- `docs/literature_review.md`
- `references/references.bib`
- `references/filings/**` with `_index.json`
- `config/filings.yaml` populated

## 10. Git requirements

Commit the review, the bibliography and the filings index. Filings themselves are
public documents and small; commit them if licensing permits, and record that decision
in `docs/data_sources.md`. Commit message names the literatures covered and the number
of primary sources archived.

## 11. Completion gate

- [ ] Four literatures mapped, with at least the canonical reference in each
- [ ] Prior work on the 2018 episode read and accurately represented
- [ ] Every primary filing located, archived and indexed
- [ ] Index methodology roll rules extracted verbatim
- [ ] Every bibliography entry actually used
- [ ] Contribution stated relative to prior work, not in a vacuum
- [ ] No unverifiable citation anywhere

## 12. Handoff

Phase 03 needs: what is already established (so the hypotheses target what is not),
the exact index construction rules, the exact product terms, and the methodological
conventions used in the literature (so the project's departures from them are
deliberate and defensible).
