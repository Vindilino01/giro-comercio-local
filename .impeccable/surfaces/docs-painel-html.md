---
version: 1
slug: "docs-painel-html"
primary_target: "docs/painel.html"
related_targets: []
---

## Scope and mode

Surface: the single static artifact `docs/painel.html`, generated from the PostgreSQL
cluster by `dashboard/gerar.py`. It is what the store owner opens weekly and what the
board sees in the ten-minute pitch. Mode: **Operate** — the visitor completes a task
(place this week's order, understand last week's loss, decide whether to trust it).

## Audience, job, action

Owner or manager of a neighbourhood grocery store. Weekly purchase ritual, no analyst,
no IT. Job: decide what to buy, from whom, how much, and whether the data deserves
trust. Action: read the order band, pick a supplier, copy the picking list.

Proof on hand: 4,134,874 sales lines, 37,477 rupture events over the last 12 months,
R$ 2,239,060.44 lost in that window, R$ 299,519.92 to order across 6 suppliers, 96.22%
defect-detection recall against 44,475 injected defects. Data is synthetic, labelled so
on the page.

## Direction contract

**THESIS** — The page is the wholesale distributor's order catalog the owner already
reads every week, rebuilt as a working screen. It refuses the category default: a KPI
card grid over a chart over a table, where the decision is nowhere.

**OWN-WORLD** — Two-ink print on cool paper: ground `#f1f0ea`, ink `#16211c`, one deep
green `#0b4f3c` owning the masthead and the selected supplier at full strength, printer's
red `#a8231b` for rupture, ochre `#8a5a00` for critical. Piazzolla (serif) for headings
and money, Archivo (sans) for labels and table cells. Hairline rules carry the
structure; no cards, no shadows, no rounded corners.

**STORY** — In one glance: R$ 299.519,92 must be ordered this week, 101 SKUs are already
empty, and the rupture has cost R$ 2.239.060,44 in the last twelve months — 7,5 orders
like this one. Then: 96% of the injected defects were caught before they reached the
numbers. Then: take one supplier's picking list.

**FIRST VIEWPORT** — Full-bleed green masthead (wordmark, store filter, data reference
date, synthetic-data notice). Beneath it: the order total at poster scale beside the
service-level control that recomputes it; below, the supplier band where each segment's
width is that supplier's share of the order; below that the picking list.

**FORM** — Grounded candidate 4 of 7 (the distributor catalog page), raised by the hand
it beat. seed: seed:c9591a770bb9c70e.

**FINISH** — unreviewed and undocumented is unfinished; this build ends with the finish
review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.

## Raises (each named for its donor)

- **Scale courage** (metro typographic tiles) — the two numbers that define the
  trade-off are set at poster scale, not as KPI chips.
- **Rerank in place with identity** (boarding-pass gate board) — choosing a supplier
  keeps the selection lit while the picking list below changes.
- **Peripheral quieting** (streaming wall) — while one supplier is read, the other
  segments recede in tone; nothing disappears.
- **Extent as weight** (acetate manual) — band segment width is the order value, so the
  band is a bar chart that is also the navigation.
- **Hard steps, no easing** (acetate manual) — 90 ms, `steps(2)`, so the instrument reads
  as machinery rather than as a web page animating.
- **The next decision only** (airport wayfinding) — the selected supplier's block answers
  what / from whom / by when, and nothing competes for the eye.
- **One control remaps the board** (variable-font specimen) — the service-level control
  re-derives every quantity live, so the safety-stock assumption is visible and arguable
  instead of buried in a docstring.

## Built and verified

- Offline: one 812 KB file, 3 fonts embedded in base64, zero external URLs, zero
  `fetch`/XHR, opens from `file://`.
- Every figure re-derivable: `dashboard/verificar.py` re-runs the SQL and compares
  totals per store, loss, rupture rate and per-supplier sums — 18/18 pass.
- Signature interaction verified through CDP: 95% → 99% moves the order from
  R$ 311.505,83 to R$ 348.408,92 (+R$ 36.903,09), and the delta names the trade-off.
- Band proportions are exact (`fr` units, not `%` or flex) at desktop widths; below
  900 px the band becomes 2 or 1 equal columns and the legend changes text with it.
- Contrast measured in the browser: minimum 5.01:1 across 2,241 text elements; the
  12px floor is 4.5:1. Zero elements below AA.
- Print: 8 A4 pages, the band becomes a list that keeps proportion as a bar, the
  store headers survive, the picking table drops the five columns nobody uses on paper.
- First viewport: at 1366x657 (a maximized 1366x768 window) two picking rows are
  fully visible; at 1366x768, six. The compact rhythm applies at `max-height: 860px`
  and keeps the dateline, which carries the evidence line.
- Audit 2026-11-16 (`/impeccable critique`, 25/40) closed P0 and three P1s: the
  picking list is grouped by store, the first viewport fits the named laptop, the
  band is a `toolbar` of `aria-pressed` buttons with focus restored after render, and
  the legend no longer claims proportional width where it is not. The seal now shows
  the dimension that decides it, and its note no longer promises hidden suggestions.

## Unresolved

- OTIF per supplier is absent from the surface on purpose: the generator writes
  `quantidade_entregue = 0`, so Q08 reports 0% for every supplier. Recorded as a known
  defect in `docs/07-limitacoes.md`; showing it would turn a bug into a business claim.
- The dataset ends 2025-10-31 while the wall clock reads later; every query is anchored
  to `max(data_venda)`, never `CURRENT_DATE`, and the page prints its own reference date.
