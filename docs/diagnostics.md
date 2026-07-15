# BookBridge Opt-In Diagnostics

BookBridge can optionally collect anonymised warning/error telemetry and
POST it to a collector endpoint.  The feature is **opt-in** — nothing is
sent unless the user explicitly enables it.

## Phase Overview

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Warning collection, PII scrubbing, snapshot/clear API | Merged |
| 2 | Payload builder, daily sender, admin send-now endpoint | This document |
| 3 | Settings UI toggle | Planned |
| 4 | Receiver / collector service | Planned |

## Settings

| Key | Default | Description |
|-----|---------|-------------|
| `DIAGNOSTICS_OPT_IN` | `false` | Master toggle (`true`/`on`/`1` to enable) |
| `DIAGNOSTICS_PROMPTED` | `""` | Has the user been prompted to opt in |
| `DIAGNOSTICS_INSTANCE_ID` | `""` | Stable UUID4 hex identifier (auto-generated) |
| `DIAGNOSTICS_ENDPOINT_URL` | `""` | Collector POST URL (TBD for Phase 4) |
| `DIAGNOSTICS_LAST_SENT` | `""` | ISO-8601 timestamp of last successful send |

## POST Payload Schema

```json
{
  "schema": 1,
  "instance_id": "a1b2c3d4e5f6…",
  "sent_at": "2026-07-15T12:00:00+00:00",
  "app_version": "7.2.0",
  "services": {
    "abs": true,
    "kosync": false,
    "storyteller": true,
    "booklore": true,
    "bookfusion": false,
    "book_orbit": true,
    "cwa": false,
    "hardcover": false,
    "storygraph": false,
    "slash_books": true
  },
  "total_books": 42,
  "window": {
    "start": "2026-07-14T12:00:00+00:00",
    "end": "2026-07-15T12:00:00+00:00"
  },
  "dropped": 3,
  "warnings": [
    {
      "template": "Sync failed after # retries",
      "message": "Sync failed after 3 retries",
      "logger": "src.sync_manager",
      "level": "WARNING",
      "count": 5,
      "first_seen": "2026-07-14T12:00:00+00:00",
      "last_seen": "2026-07-15T11:58:00+00:00",
      "context": ["2026-07-15 11:58:00 WARNING …"]
    }
  ]
}
```

### Field Types

| Field | Type | Description |
|-------|------|-------------|
| `schema` | `int` | Payload version (currently `1`) |
| `instance_id` | `string` | Stable UUID4 hex per bridge instance |
| `sent_at` | `string` | UTC ISO-8601 timestamp of send |
| `app_version` | `string` | Bridge version from `APP_VERSION` |
| `services` | `object<string, bool>` | Per-service `is_configured` flags |
| `total_books` | `int \| null` | Active book count (`null` on DB error) |
| `window.start` | `string \| null` | Start of the observation window |
| `window.end` | `string \| null` | Snapshot taken-at timestamp |
| `dropped` | `int` | Warning entries dropped (capacity exceeded) |
| `warnings` | `array<object>` | Deduplicated warning entries |

Each warning object contains: `template`, `message`, `logger`, `level`,
`count`, `first_seen`, `last_seen`, `context` (array of scrubbed log
lines).  All PII (URLs, filesystem paths, long quoted spans) is
deterministically scrubbed before inclusion.

## Send Semantics

- **Frequency:** at most once per 24 hours; the sender checks
  `DIAGNOSTICS_LAST_SENT` before posting.
- **Deduplication:** the collector receives deduplicated, template-keyed
  warnings with occurrence counts — not raw log lines.
- **Scrubbing:** all text passes through `scrub_diagnostic_text()` which
  replaces URLs, filesystem paths, and long quoted spans with stable
  hash tokens.
- **Idempotency:** on a 2xx response the sender clears the snapshot
  buffer and records the send time.  On non-2xx or network error the
  buffer is preserved and the send is retried on the next cycle.
- **Heartbeat:** an empty `warnings` list is still sent — the metadata
  (instance, version, services, book count) constitutes an intentional
  heartbeat.
- **Admin override:** `POST /api/diagnostics/send-now` (admin-only)
  bypasses the 24h guard and forces an immediate send.

## Endpoint

`DIAGNOSTICS_ENDPOINT_URL` must be set to the collector's POST URL.
The default is TBD pending Phase 4 receiver implementation.

## Receiver (Phase 4)

The diagnostics receiver is a standalone Flask application that accepts
diagnostic payloads from opted-in BookBridge instances and stores them
in SQLite for automated and ad-hoc analysis.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Health check; returns `ok`, instance count, and batch count |
| `POST` | `/api/v1/diagnostics` | Accept a schema-1 diagnostics payload |
| `GET` | `/api/v1/export?since=<ISO>` | Export batches (and embedded warnings) since a timestamp |
| `GET` | `/api/v1/summary?days=<n>` | Aggregate top warning templates with distinct-instance counts |

### SQLite Schema

Three tables, managed idempotently via `CREATE TABLE IF NOT EXISTS`:

- **`instances`** — one row per `instance_id`; tracks `first_seen`,
  `last_seen`, `last_version`, `last_services_json`, and
  `last_total_books`.  Upserted on every incoming batch.
- **`batches`** — one row per received payload; stores `received_at`,
  `sent_at`, `app_version`, `services_json`, `total_books`, window
  bounds, and `dropped` count.
- **`warnings`** — one row per deduplicated warning entry within a
  batch; `context` arrays are joined by newline into `context_text`.

### Deployment

The receiver lives in `diagnostics_receiver/` and runs in its own Docker
container (`bookbridge_diagnostics`), built from `python:3.12-slim` with
`waitress` as the WSGI server.  Port **20129**, SQLite data persisted to
`./data/diagnostics.db` via a bind mount.

```bash
cd diagnostics_receiver
docker compose up -d --build
```

The public `DIAGNOSTICS_ENDPOINT_URL` that opted-in instances POST to
is still TBD; when deployed behind a reverse proxy, the URL will point
at the proxy's external address (port 20129 on the internal network).

### Automated Review Integration

`scripts/automated-review/run-diagnostics-scan.ps1` fetches the export
endpoint, captures the JSON snapshot, and feeds it to the read-only
bugscout agent using the prompt at
`docs/automated-review/prompts/diagnostics-scan.md`.  The agent looks
for fleet-wide warning patterns across opted-in instances and appends
findings to `BUG_REPORT.md`.  The scan mirrors the log-scan script in
structure, state handling, and failure semantics (state is NOT advanced
on failure so the window is re-scanned).
