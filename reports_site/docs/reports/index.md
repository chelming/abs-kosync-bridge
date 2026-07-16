# Reports

One page per finding, added by the parser as `YYYY-MM-DD_<finding-id>.md`
(date = first seen). Each page is **fully regenerated** on every scan and
includes: summary, error context, enabled integrations, evidence, maintainer
response (from the receiver API's `response_md`/`response_at` fields), and
visible submitter comments. Stale pages for resolved findings are removed
automatically.

The committed sample (`2026-07-16_sample-finding.md`) is a fabricated example
and is never overwritten or deleted by the parser.
