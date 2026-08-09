# Active / time-sensitive items

Check dates against today before relying on this file — it goes stale by
design and should be trimmed or updated, not left as-is indefinitely.

- `auto-resume-fabric-capacity` Logic App: only intended to run through
  10 Aug 2026 (has an internal date guard, but the paired
  `auto-pause-fabric-capacity` schedule was also shifted to 23:00 for the
  same window) — after that, revert the pause time to 00:00:01 and
  disable/delete the resume app.
- Power BI Report 1 was published live temporarily (9am–11pm NZT) through
  10 Aug 2026, then switched to a PDF-only version per the Part 5 post.
