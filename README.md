# Galaxy Buds On — experimental macOS diagnostic build

This repository builds a **read-only, experimental Galaxy Buds On (SM-U600)** variant of [GalaxyBudsClient](https://github.com/timschneeb/GalaxyBudsClient) in GitHub Actions. It is a compatibility investigation, **not a working multipoint unlock**.

## Build and download

1. Open the [Actions tab](https://github.com/matt-gummow/galaxy-buds-on-preview/actions) and select **Build Galaxy Buds On diagnostic app (macOS)**.
2. Open the latest successful run. If no run appears, click **Run workflow**.
3. Under **Artifacts**, download **GalaxyBudsOn-diagnostic-macos-arm64**.
4. Unzip the downloaded artifact and install the included macOS Apple Silicon `.pkg`.
5. The installer is unsigned. Only allow it in macOS Privacy & Security if you trust this repo and its upstream source.

No local Xcode installation or Apple App Store sign-in is needed. The cloud workflow checks out upstream commit `85dfc8bb39fc45d3c30ecf71ab2c663fb1d41729`, applies `add_buds_on.py`, compiles the macOS native Bluetooth library, and publishes a `.pkg` with .NET 11.

## Run the read-only connection test

1. Connect Galaxy Buds On through macOS Bluetooth and open the preview. In GalaxyBudsClient, select **Galaxy Buds On** and click **Connect** if the app offers it.
2. Wait about 15 seconds. Open the app's **Settings** and select **Copy Buds On connection report**, even if the app reports a connection error.
3. Paste the report in your test conversation. It contains SDP service-class UUIDs, RFCOMM channels, connection results, incoming chunk sizes, and validated frame metadata. It excludes Bluetooth addresses, device names, and packet contents. The report covers the current app launch.

The preview also saves the report automatically as `~/Library/Application Support/GalaxyBudsClient/buds-on-connection-report.txt`. If Settings is unavailable, open that file after a connection attempt to read the same report.

## Compare settings in one session

Keep Buds Manager open so the report can retain observations across reconnects. Start with the settings as they are and capture one Mac reading before editing anything in Galaxy Wearable.

Change one setting at a time on the Galaxy phone. After each change, reconnect the buds to the Mac if the phone took the connection and wait for a fresh status message. Start with **Answer call or end call**, then try **Decline call**, one left or right hold action, **Media controls**, and one EQ preset. Restore values individually and capture each restored state.

Each report row contains the candidate EQ code, left and right hold-action codes, and expected touch and call flags. Unchanged rows are omitted within a connection. The first observation after a reconnect is always recorded. The call double-tap flag has passed an On → Off → On comparison. Other fields are candidates until individual changes in Galaxy Wearable match the observations. All changes in this test are made on the phone.

## Current support

- The app recognizes Buds On by Bluetooth name. The macOS connection attempts Bluetooth service discovery and tries the existing Galaxy Buds management UUID. The report distinguishes a refreshed service list from a potentially cached one.
- The Home page shows the earbuds' lower battery percentage and the case percentage from repeated Buds On status messages. Missing fields are omitted. Before those messages arrive, the app can show the overall percentage supplied by macOS. Separate left and right readings remain in the diagnostics while they are independently verified.
- The preview blocks outgoing Samsung protocol messages, including settings, factory reset, firmware, and multipoint writes. It checks incoming frames in memory for valid Samsung SPP framing and CRC. The report records message IDs, lengths, counts, and clearly marked battery candidates without saving raw packets.
- The Touch controls page shows the current **Answer call or end call** setting as On or Off after a fresh Buds On status message. The row is read-only. Switching this setting on the phone and reconnecting to the Mac updates the display.
- EQ and other touch settings still require more model-specific validation. The EQ controls can change the displayed preset while the preview blocks the device command.
- Samsung supports Auto Switch on compatible Galaxy devices and on Windows through Galaxy Connect. The existing [GalaxyBudsClient multipoint patch](https://github.com/timschneeb/GalaxyBudsClient/pull/729) has no verified Buds On compatibility.

## Important limits

A successful CI build does not prove that the package installs, recognizes Buds On, communicates over Bluetooth, or enables multipoint. The macOS package is unsigned and may need manual approval. Builds are hosted on GitHub-hosted macOS runners; access and quotas depend on GitHub's current policies.

If the run fails, open the failed step in the GitHub Actions log and inspect the error.
