---
paths:
  - "models/gold/**"
---

# `models/gold/`

Read `docs/architecture.md` and `docs/research.md` before changing anything
here — what each covers is in the root `CLAUDE.md`, "Docs".

**`models/gold/` holds two models, both read by Report 1:
`forecast_accuracy`, and `margin_compression` (W19, 15 Oct 2026).** Neither
carries tests, so neither can stop a weekly run. The four that used
to sit beside them — `lag_correlation`, `lag_resolved`, `factor_volatility`,
`volatility_config` — were deleted on 8 Sep 2026: nothing had read them since
Report 1 moved to the Python ADL+ECM, and they carried 22 of the project's 65
tests, any of which could stop a weekly run over data with no consumer. Their
design is still written up under "The T-SQL lag layer" in `architecture.md`,
kept as the reasoning any replacement has to answer.
