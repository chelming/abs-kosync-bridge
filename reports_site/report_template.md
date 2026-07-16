---
title: "Finding {{finding_id}}: {{summary_short}}"
---

# Finding {{finding_id}} — {{summary_short}}

## Summary

{{summary_long}}

## Error context

| Field | Value |
|---|---|
| Category | {{category}} |
| Severity | {{severity}} |
| Status | {{status}} |
| Occurrences | {{total_count}} |
| Instances affected | {{instance_count}} |
| App versions | {{app_versions}} |
| First seen | {{first_seen}} |
| Last seen | {{last_seen}} |

## Enabled integrations (most recent affected instance)

| Service | Enabled |
|---|---|
| {{service_name}} | {{yes_or_no}} |

## Evidence (up to 5 most recent)

{{#evidence}}
**Instance** `{{instance_id}}` (v{{app_version}}, count {{count}}, last seen {{last_seen}})

```log
{{message}}
```

{{/evidence}}

## Maintainer Response

{{#response_md}}
{{response_md}}

{{#response_at}}
_Updated: {{response_at}}_
{{/response_at}}
{{/response_md}}
{{^response_md}}
!!! note "Status: pending"
    _No response yet._
{{/response_md}}

## Submitter Comments

{{#visible_comments}}
**{{created_at}}**

```text
{{body}}
```

{{/visible_comments}}
{{^visible_comments}}
_No visible comments._
{{/visible_comments}}
