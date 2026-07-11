# Release Notes - 7.1.1

The headline change is **reader-owned integrations, BookFusion support, and a more reliable BridgeSync**. BookBridge now gives every reader a self-service place to manage their own service accounts, adds BookFusion progress and highlight sync, expands the list and collection bridges introduced around 7.1, and makes large-library synchronization faster and more resilient.

Highlight and note sync still requires the **BridgeSync KOReader plugin from 7.1.0 or newer**. Standard KOReader/KOSync progress sync continues to work without it, but annotation exchange, sweep, close-capture, and managed collection features use the updated plugin. Install the latest bundled plugin for the reliability improvements below. Devices that briefly installed BridgeSync 0.5.0 must reinstall manually because that disabled build cannot run its own updater.

## Added

- **BookFusion progress and highlight sync** - readers can link their own BookFusion account, sync reading progress by percentage, and relay BookFusion highlights through the annotation hub. BookFusion positions use a fresh UTF-16 offset/xpointer mapper, and uploading books to BookFusion is intentionally not part of this release.
- **Self-service reader integrations** - each signed-in reader now has Account -> My Integrations, where they can manage service usernames, passwords, tokens, API keys, and per-user sync toggles. Admins can still manage those same fields for any reader from Settings -> Users.
- **Readest and Hardcover annotation spokes** - Readest cloud highlights and Hardcover annotations can participate in the annotation hub using each reader's own account configuration.
- **BridgeSync collections from Grimmory or Hardcover** - KOReader collection manifests can use either Grimmory shelves or Hardcover lists as the source, configured per reader.
- **Grimmory shelves to Hardcover lists** - readers can optionally mirror Grimmory shelf membership into Hardcover lists, with modes for all shelves, magic shelves, or regular shelves.

## Changed

- **Integration settings follow the reader** - user-owned credentials live with the reader, either in Account -> My Integrations or in the admin-managed user integrations page. Global Settings keep shared engine behavior such as server URLs, poll intervals, and daemon-level options.
- **KOReader collection controls are per-reader** - the collection source selector now lives under each reader's KOReader Collections integration group, making Hardcover-list collections discoverable even when Grimmory is disabled.
- **Integration pages are easier to scan** - service groups now use Settings-style enable toggles in the header, and disabled groups collapse their account fields until that reader turns the integration on.
- **Settings and account pages explain the split** - admin integration pages point readers to Account -> My Integrations, and BookFusion forms link to BookFusion's Calibre integration page for manual API-key setup.
- **BridgeSync handles large libraries and competing sync requests more reliably** - annotation and statistics uploads are bounded and acknowledgment-gated, paged results are drained completely, and overlapping work is serialized and coalesced. On-device status, safer payload handling, xpointer repair, semantic update checks, and translated interface strings make failures easier to diagnose and recover.
- **EPUB position resolution is substantially faster** - BookBridge shares cached book paths between the parser and sync manager, bypasses unnecessary scans for managed cache files, and avoids parsing the same EPUB twice while resolving generated XPath positions. (#318)

## Fixed

- **Manually selected KoSync hashes now stay selected** - previous and served-file hashes remain linked as siblings, so devices and progress resolve through either EPUB build without a manifest refresh replacing the chosen primary hash. (#316)
- **Mark Complete only writes to compatible services** - BookBridge filters clients by book type and support, and records completion only after a successful remote update. (#318)
- **Background work shuts down and resumes safely** - deleting a mapping cancels its transcription worker without allowing a late save to recreate it, while restart recovery serializes pending full Forge uploads. (#313, #314)
- **Routine incomplete or temporarily locked data no longer aborts maintenance work** - suggestion scans skip unusable Audiobookshelf duration records, and KOReader statistics writes retry ordinary SQLite lock contention. (#312, #315)
- **Audiobookshelf instant sync applies live debounce changes safely** - listener replacements no longer leak debounce workers, and self-write suppression remains active across longer debounce intervals.

## Operational Notes

Database migrations apply automatically on startup. BookFusion support syncs progress and highlights only; uploading books to BookFusion is not included. Web-reader annotation sync depends on the matching source credentials being configured for each reader. Restart BookBridge after updating, and install the latest bundled BridgeSync plugin on KOReader devices to receive the plugin-side reliability improvements.
