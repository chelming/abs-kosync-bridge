# Bridge Sync KOReader Plugin

`bridgesync.koplugin` is an optional KOReader plugin for the bridge.

It mirrors bridge-managed books into a local KOReader folder so the device can keep a managed library in sync with the server.

## What It Does

- Connects to the bridge with your KOSync credentials
- Downloads books from the bridge-managed manifest
- Reuses existing local files when hashes already match
- Renames files when the bridge filename changes
- Optionally deletes local files that the bridge no longer tracks
- Can sync manually or on wake/network reconnect

## Install

1. Download the prebuilt `bridgesync` plugin zip from the project's GitHub Releases page.
2. Extract the resulting zip.
3. Copy `bridgesync.koplugin` into KOReader's `plugins/` directory.
4. Restart KOReader.

For local packaging or development, you can build the zip yourself:

   ```bash
   python scripts/package_koreader_plugins.py bridgesync.koplugin
   ```

Typical plugin locations:

- Kobo: `.adds/koreader/plugins/`
- Kindle: `koreader/plugins/`
- Linux: `~/.config/koreader/plugins/`
- Android: `/sdcard/koreader/plugins/`

## Configure

In KOReader:

1. Open `Tools -> Bridge Sync`.
2. Set the bridge server URL.
3. Enter the KOSync username and key used by the bridge.
4. Choose a managed folder.
5. Run `Test Connection`.
6. Run `Sync Now`.

## Notes

- This plugin is optional and is not required for normal bridge syncing.
- The plugin currently targets the bridge device-sync manifest endpoints already exposed by the server.
