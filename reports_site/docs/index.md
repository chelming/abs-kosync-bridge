# BookBridge Bug Reports

Internal analytics site for the opt-in diagnostics pipeline. The automated
parser turns incoming diagnostics into one markdown page per finding, and this
site renders them with maintainer responses and submitter comments on each one.
It is local-only: nothing here is published or reachable by users.

## How reports get here

The diagnostics scan writes two kinds of content:

- [Findings](findings.md) — a live copy of the fleet digest
  (`DIAGNOSTICS_FINDINGS.md`), overwritten on every scan.
- [Reports](reports/index.md) — one page per active finding, **fully
  regenerated** on every scan. Each page includes current summary, context,
  integrations, evidence, maintainer response, and visible submitter comments.

## Responding to a report

Post a maintainer response using the PowerShell helper:

```powershell
powershell -ExecutionPolicy Bypass -File reports_site/respond-finding.ps1 <id> "<message>"
```

The response is stored on the receiver API. The next diagnostics scan
regenerates the report page with your response included under
**Maintainer Response**.
