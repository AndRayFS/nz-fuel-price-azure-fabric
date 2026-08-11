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
installed. That API throttles with HTTP 429 — retry with a short backoff.

Critical working rules (verify before asserting, heredoc checks, one
change at a time, no point-forecast language) live in the root
`CLAUDE.md` — not repeated here.
