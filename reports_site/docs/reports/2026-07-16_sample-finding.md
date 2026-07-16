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

## Instance

| Field | Value |
|---|---|
| Instance UUID | `3f2a9c1e4b7d4e0a8c6f1b2d9e3a5c70` |
| App version | 2.4.1 |
| Total books | 142 |
| Window | 2026-07-15T11:00:00Z → 2026-07-16T11:00:00Z |
| Received | 2026-07-16T11:02:32Z |

## Enabled integrations

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

## Error context

| Field | Value |
|---|---|
| Category | code-bug |
| Severity | low |
| Occurrences | 109 |
| First seen | 2026-07-15 |
| Last seen | 2026-07-16 |
| Pattern | `pull_highlights() logs a WARNING for BookFusion 404 (book not found)` |

## Logs

```log
2026-07-15T12:00:02Z WARNING - BookFusion pull_highlights: 404 for book 'Example Title' (not present in BookFusion)
2026-07-15T13:00:02Z WARNING - BookFusion pull_highlights: 404 for book 'Example Title' (not present in BookFusion)
2026-07-15T14:00:02Z WARNING - BookFusion pull_highlights: 404 for book 'Example Title' (not present in BookFusion)
```

<!-- BEGIN DEVELOPER RESPONSE — the parser must never write below this line -->

## Developer Response

!!! success "Status: fixed"
    Downgraded to debug to match the silent-404 pattern in
    `get_reading_position()`; ships in the next `:dev` image.

<!-- END DEVELOPER RESPONSE -->
