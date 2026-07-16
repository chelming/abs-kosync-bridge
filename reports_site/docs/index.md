# BookBridge Bug Reports

Internal analytics site for the opt-in diagnostics pipeline. The automated
parser turns incoming diagnostics into one markdown page per finding, and this
site renders them with room for a developer response on each one. It is
local-only: nothing here is published or reachable by users.

## How reports get here

The diagnostics scan writes two kinds of content:

- [Findings](findings.md) — a live copy of the fleet digest
  (`DIAGNOSTICS_FINDINGS.md`), overwritten on every scan.
- [Reports](reports/index.md) — one page per finding, **create-only**: once a
  report file exists, the parser never touches it again.

## Responding to a report

Open the report page's markdown file and edit the section between the
`BEGIN DEVELOPER RESPONSE` and `END DEVELOPER RESPONSE` sentinel comments.
Because report files are create-only, your response survives every future
scan.
