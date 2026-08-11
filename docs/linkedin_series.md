# LinkedIn series — index and house style

Derived from reading all five published posts (10 Aug 2026). Links live in
`README.md`.

| Part | Topic | Ends by promising |
|---|---|---|
| 1 | Original R lag analysis, MBIE data, 4 shocks | — |
| 2 | Architecture: bronze/silver/gold, metadata pivot, why dbt | "register Azure, stand up Fabric" |
| 3 | Azure/Fabric registration, F2, budget alerts, first pipeline | "bring dbt into the picture" |
| 4 | dbt on Fabric, macros, lineage, the lag bug found vs R | "build the Power BI reports" |
| 5 | Report 1 live, confidence framing, 9am–11pm window | **"a look at what all this actually cost in Microsoft Fabric"** |
| 6 | Costs — material in `cost_notes.md` | |

Each post opens by referring back to the previous one and closes by naming
the next. Part 6 is already promised as the cost post.

## House style

- First person, opens from a concrete lived moment ("watching the news",
  "that was a pretty accurate description"), not from methodology.
- Body carries 3–5 bullets marked ✅ (findings) or 1️⃣2️⃣ (design decisions);
  ❓ introduces the question the post answers, 💡 the mental model.
- Every claim carries a number. Numbers are specific (0.92, NZ$0.40,
  NZ$306.60), never "significant" or "a lot".
- One honest limitation near the end, stated plainly — "a weekend data
  project rather than a controlled study", "still just a correlation" —
  followed by what would fix it.
- A surprise or reversal is the spine of the strongest posts: Part 3
  ("registration was supposed to be the boring part"), Part 4 (every test
  passed and the model was still wrong).
- Closing line is light, sometimes a joke (coffee ☕).
- Links to GitHub and sources go in the **first comment**, not the body.
  Part-to-part backlinks and 2–3 hashtags sit at the very bottom.
- Signed off as `NZ Fuel Price Project — Part N`.
- No point-forecast language on report measures — "if the pattern holds,
  we should begin seeing", never "will be". Matches the confidence-tier
  rule in `CLAUDE.md` / `architecture.md`.
