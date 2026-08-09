# Tooling split — this isn't the only place work happens

- **Claude Code (here):** dbt models, macros, seeds, SQL, git, tests —
  anything that's a file + terminal command.
- **claude.ai chat (separate):** Power BI Desktop (Windows VM GUI — DAX
  can be drafted here as text, but applying/screenshotting it happens
  there), Azure Portal / Fabric web UI clicks (IAM roles, Logic App
  designer, tenant settings), methodology discussions, LinkedIn post
  drafting. Don't assume you can drive those directly.

Critical working rules (verify before asserting, heredoc checks, one
change at a time, no point-forecast language) live in the root
`CLAUDE.md` — not repeated here.
