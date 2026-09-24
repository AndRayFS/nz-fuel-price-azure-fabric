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
  offline against `data/panel_weekly.csv` in seconds, others need the
  Fabric capacity resumed and therefore money. `headline_results.py` is the
  first kind; anything reading the warehouse is the second.

## Two sessions, one repository

**A branch belongs to the checkout, not to the session.** Two Claude Code
sessions opened on this directory are on the same branch at the same moment,
whatever each of them was asked to do, because `HEAD` is one file on disk and
both are reading it. A session that believes it is "on the research branch"
while another is "on the load branch" is mistaken: there is one branch, and
both are committing to it.

*Measured, 19 Sep 2026.* A session automating the weekly load and a session
doing research ran here at the same time. `git worktree list` showed one
worktree; three research commits landed on `w16-move-the-clock`, and one commit
swept the other session's unstaged files in with `git add -A`. Nothing was
lost, and nothing about the interleaving was visible until the reflog was read.

Separating them afterwards did not need a rewrite, and that is the point of the
last rule below: a second worktree, `git cherry-pick` of one session's commits
onto a fresh branch from `main`, and the mixed branch left standing for the
other session to do the same. *Checked* the same day — the rebuilt branch
differed from the mixed one by exactly the other session's files.

**One line of work, one worktree.** This is the only fix that actually
separates two sessions; everything below is damage control for when they share
one anyway.

```bash
git worktree add ../nz-fuel-research -b w17-margin-episodes
```

A fresh worktree is a real checkout and is missing everything git does not
carry, which in this repository is most of what a script needs:

| missing | why | what to do |
|---|---|---|
| `.venv/` | never committed, and it lives *above* the project on this machine | pass `VENV=/Users/Ray/nz-fuel-price-project/.venv` to `task`, or build one |
| `dbt_packages/` | gitignored | `task deps` once |
| `data/` | gitignored on purpose — derived data lives in the warehouse | symlink or copy from the main checkout; regenerating `panel_weekly.csv` costs a warehouse read |
| `.dbt/` | holds the profile, not committed | copy it |

Remove it with `git worktree remove ../nz-fuel-research` when the branch is
merged, or it will quietly keep a stale checkout alive.

**Stage by name, never `git add -A` or `git add .`.** Those two cannot tell
your work from someone else's, and in a shared checkout they will eventually
sweep in a file you have never read. Name the paths you changed, and read
`git status --short` before every commit rather than after.

**Changes you did not make are not yours to handle.** If unexpected edits or
untracked files appear mid-session: do not commit them, do not revert them, do
not stash them — stashing is worse than committing, because it removes them
from another session's working tree with no trace it can see. Say what turned
up and carry on with your own files.

**Do not rewrite history you did not write in this session.** `amend`, `reset`
and `rebase` all assume nobody else is standing on the commit. Read `git log`
first; if anything newer than your own last commit is there, the branch has
moved under you and rewriting it will take someone else's work with it. A
commit that turns out to be wrong is corrected by another commit.

## Commit messages are English

The repository is English throughout — models, macros, `docs/`, `CLAUDE.md`,
the rules in this directory, code comments. Commit subjects were English too
for the first 107 commits, through 23 Aug 2026, and then switched to Russian
on 27 Aug without a decision behind it; 56 commits are in Russian.

**Write commit subjects and bodies in English from now on.** The history is
not rewritten — the Russian commits stay as they are, and the split is a
visible date, not a mess to clean up.

This is about the artefact, not the conversation: discussion here stays in
Russian. The rule is that anything committed to the repository matches the
repository.

## Russian terminology — the words, not the calques

Conversation here is in Russian, and it uses the words the owner uses rather
than literal translations of the English identifiers.

- **The Fabric Warehouse is «база» or «БД», never «склад».** Asked for on
  27 Aug 2026 and again on 20 Sep 2026.

English is unaffected: identifiers, `docs/`, code comments and commit
subjects stay as they are. «Склад» is a calque that reads as translated
rather than written.

This lives here rather than only in memory because a rule in this file is
loaded as an instruction every session, while a memory index line is
background context that may never be recalled. When another term comes up,
add it to this list.

## Answer order

The problem the user reports is not density and not tone — it is order.
Answers arrive arranged so that the reader has to hold facts they cannot use
yet, and reach the point where a fact matters after it has gone past.

**Order by what the reader needs first, not by the order you found it in.**
The chronology of your own investigation — checked X, then Y turned out, so Z
— is almost never the right order for the answer. Conclusion first, then the
ground under it.

**Say each thing once, in one place, and then close it.** Do not return to a
topic already finished. `а ещё такой момент` and `стоит отметить` under a
stated conclusion are the visible symptom: a qualification arriving after the
conclusion means the conclusion was published too early, and the reader who
already acted on it has to go back. If you find mid-answer something that
changes the conclusion, rewrite the conclusion — never append under it.

**No forward references.** Do not use a number, name or fact before it has
been given. A sentence that only makes sense after the next paragraph means
the two are in the wrong order.

**One layer per line.** What happened, what it means, and what to do are
three different things; do not braid them into one sentence or one bullet.

The instrument for all four: the conclusion as the first line; the ground
under it as short bullets, one fact each; at most one closing line, and only
when a next action exists. If the answer has more than one part, say how many
before the first part and give each a heading.

Critical working rules (verify before asserting, heredoc checks, one
change at a time, no point-forecast language) live in the root
`CLAUDE.md` — not repeated here.
