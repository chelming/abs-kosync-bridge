---
title: "Sample: BookFusion 404 logged as WARNING every sync cycle"
---

# Report sample-finding — BookFusion 404 logged as WARNING every sync cycle

## Summary

`pull_highlights()` logs a WARNING for a BookFusion 404 (book not present in
BookFusion) on every sync cycle, flooding the diagnostics window with repeat
noise for a condition that is expected for part of the library.

*This page is a fabricated example demonstrating the report template — it is
safe to delete once real reports exist.*

## Error context

| Field | Value |
|---|---|
| Category | code-bug |
| Severity | low |
| Status | fixed |
| Occurrences | 109 |
| Instances affected | 1 |
| App versions | 2.4.1 |
| First seen | 2026-07-15 |
| Last seen | 2026-07-16 |

## Enabled integrations (most recent affected instance)

| Service | Enabled |
|---|---|
| ABS | yes |
| KoSync | yes |
| Storyteller | yes |
| BookFusion | yes |
| Grimmory | no |
| BookOrbit | no |
| CWA | no |
| Hardcover | yes |
| StoryGraph | no |

## Evidence (up to 5 most recent)

**Instance** `3f2a9c1e4b7d4e0a8c6f1b2d9e3a5c70` (v2.4.1, count 109, last seen 2026-07-16)

```log
2026-07-15T12:00:02Z WARNING - BookFusion pull_highlights: 404 for book 'Example Title' (not present in BookFusion)
2026-07-15T13:00:02Z WARNING - BookFusion pull_highlights: 404 for book 'Example Title' (not present in BookFusion)
2026-07-15T14:00:02Z WARNING - BookFusion pull_highlights: 404 for book 'Example Title' (not present in BookFusion)
```

## Maintainer Response

Downgraded to debug to match the silent-404 pattern in
`get_reading_position()`; ships in the next `:dev` image.

## Submitter Comments

_No visible comments._
