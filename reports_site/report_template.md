---
title: "{{summary_short}}"
---

# Report {{report_id}} — {{summary_short}}

## Summary

{{summary_long}}

## Instance

| Field | Value |
|---|---|
| Instance UUID | `{{instance_id}}` |
| App version | {{app_version}} |
| Total books | {{total_books}} |
| Window | {{window_start}} → {{window_end}} |
| Received | {{sent_at}} |

## Enabled integrations

| Service | Enabled |
|---|---|
| {{service_name}} | {{yes_or_no}} |

## Error context

| Field | Value |
|---|---|
| Category | {{category}} |
| Severity | {{severity}} |
| Occurrences | {{count}} |
| First seen | {{first_seen}} |
| Last seen | {{last_seen}} |
| Pattern | `{{pattern}}` |

## Logs

```log
{{verbatim_warning_log_lines}}
```

<!-- BEGIN DEVELOPER RESPONSE — the parser must never write below this line -->

## Developer Response

!!! note "Status: pending"
    _No response yet._

<!-- END DEVELOPER RESPONSE -->
