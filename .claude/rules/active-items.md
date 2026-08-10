# Active / time-sensitive items

Check dates against today before relying on this file — it goes stale by
design and should be trimmed or updated, not left as-is indefinitely.

- `auto-resume-fabric-capacity` Logic App: **disabled 10 Aug 2026**, at the
  end of the window it was built for. Two follow-ups still open:
  - [ ] 11 Aug 2026 — confirm in the Azure Portal run history that it did
    not fire overnight.
  - [ ] revert `auto-pause-fabric-capacity` from 23:00 (shifted for the same
    window) back to 00:00:01 NZT.
  Once both are done, delete this whole item.
- Power BI Report 1 was published live temporarily (9am–11pm NZT) through
  10 Aug 2026, then switched to a PDF-only version per the Part 5 post.
  Drop this item once the PDF switch is confirmed done.
