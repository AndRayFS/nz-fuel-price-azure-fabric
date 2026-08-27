# Tooling split — this isn't the only place work happens

- **Claude Code (here):** dbt models, macros, seeds, SQL, git, tests —
  anything that's a file + terminal command. Also, since 10 Aug 2026, the
  **logged-in browser** (see below) and **Azure read-only queries** via the
  `az` CLI (installed, authenticated against subscription
  `e30d2fa4-fb6e-48c5-b3cd-5f9c3f270159`).
- **claude.ai chat (separate):** Power BI Desktop (Windows VM GUI — DAX
  can be drafted here as text, but applying/screenshotting it happens
  there), methodology discussions, LinkedIn post drafting. Don't assume
  you can drive those directly.

## Browser access

Chrome automation works in this VSCode session once the user types
`@browser:new_tab` — that loads the `mcp__claude-in-chrome__*` tools. There
is no `/chrome` slash command in the VSCode panel (that one is
terminal-CLI-only). Permissions are granted **per domain, per client**:
linkedin.com worked; `portal.azure.com` was denied until approved in the
Chrome extension panel. The connection can drop mid-task; the user
re-enables it the same way.

For Azure facts, prefer the `az` CLI over portal clicking — the Cost
Management REST API (`az rest`, `Microsoft.CostManagement/query`) returns
usable data, whereas `az consumption usage list` deserialises costs as the
string `"None"` and `az costmanagement` needs an extension that isn't
installed. That API throttles with HTTP 429 — **wait at least 45 s between
attempts**. Not "a short backoff": the 429 body says only "Please retry",
but the response headers carry
`x-ms-ratelimit-microsoft.costmanagement-clienttype-retry-after: 32` and
`...-clienttype-requests: DefaultQuota:0`. Retrying at 20 s intervals
failed six times in a row on 14 Aug 2026; 45 s succeeded on the second
attempt. `az rest` hides those headers — use `curl -D` with a token from
`az account get-access-token` when you need to see why it is refusing.

## Numbers in `docs/` are illustrations, not current values

Every figure written into `docs/` is a cache of a computation made on some
past date, and it goes stale silently — the source revises, MBIE finalises a
block of weeks, someone runs part of the chain by hand in the portal. Nothing
guarantees a documented number still holds, and dated caveats stapled to
individual tables only work if a reader notices them.

So the rule is about *quoting*, not about the documents:

- **If the answer is about shape or logic** — why the lag halves, which
  direction a regime pushes, whether an axis does anything at all — the cached
  figure is the right answer. Use it, and say it is an illustration from its
  date. Recomputing would cost time and prove nothing the reader asked about.
- **If the answer turns on the digit** — a number about to be published,
  quoted to someone else, or used to decide — name the date it was measured
  and *offer* the recompute. Do not silently quote it as current, and do not
  silently run the recompute either.
- **Say what the recompute actually costs**, because it varies: some run
  offline against `research/data/panel_weekly.csv` in seconds, others need the
  Fabric capacity resumed and therefore money. `headline_results.py` is the
  first kind; anything reading the warehouse is the second.

Critical working rules (verify before asserting, heredoc checks, one
change at a time, no point-forecast language) live in the root
`CLAUDE.md` — not repeated here.
