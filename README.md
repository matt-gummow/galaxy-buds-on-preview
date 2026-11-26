# Galaxy Buds On — experimental macOS diagnostic build

This repository builds an **experimental Galaxy Buds On (SM-U600)** variant of [GalaxyBudsClient](https://github.com/timschneeb/GalaxyBudsClient) in GitHub Actions. It includes read-only diagnostics and explicitly confirmed one-shot touch and equalizer tests on macOS.

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

## Check touch controls and EQ in one session

1. Connect the Buds On in the Mac app. On **Touchpad**, choose **Test Decline call and Media controls…**, then confirm **Turn both off once**. The button requires fresh status showing both settings fully on. If the button stays disabled after reconnecting, use **Test Touch and hold during call…** to test Decline by itself.
2. On **Equalizer**, note the current preset and choose **Test an EQ preset…**. Pick a different standard preset and confirm **Set preset once**. If the app requests fresh status, reconnect in the Mac app and try the EQ test once more.
3. Check both changes in the Galaxy phone’s Bluetooth device settings for Buds On. Confirm **Decline call** and **Media controls** are off if you ran the combined test, **Answer call or end call** kept its original value, and the EQ matches your selection. Restore your previous values on the phone.
4. Reconnect to the Mac and choose **Settings → Copy Buds On connection report** to capture the restored state along with the test results.

Each confirmation sends a single command. The test dialogs distinguish a new status report from an acknowledgment. If both tests use the same status frame, a newer Bluetooth response must arrive between them. Samples expire after 60 seconds, and the app checks the selected device, session, and relevant status at send time. It never retries a command automatically.

## Current support

- The app recognizes Buds On by Bluetooth name. The macOS connection attempts Bluetooth service discovery and tries the existing Galaxy Buds management UUID. The report distinguishes a refreshed service list from a potentially cached one.
- The Home page shows the earbuds' lower battery percentage and the case percentage from repeated Buds On status messages. Missing fields are omitted. Before those messages arrive, the app can show the overall percentage supplied by macOS. Separate left and right readings remain in the diagnostics while they are independently verified.
- The preview checks incoming frames for valid Samsung SPP framing and CRC. The report records message IDs, lengths, counts, and battery observations without saving raw packets. Generic settings commands, factory reset, firmware, and multipoint writes are blocked for Buds On. Only the dedicated touch and preset EQ tests can send configuration commands for this model.
- The **Touchpad** page shows read-only **Double tap during call** and **Touch and hold during call** rows after a fresh Buds On status message. The phone calls them **Answer call or end call** and **Decline call**. The first row was confirmed on Apple Silicon with SM-U600. The second decoder was checked against Samsung’s app and synthetic status frames. A Mac test turned off **Answer call or end call** on an SM-U600, confirmed in the Galaxy's Buds settings. The original On value was restored on the phone and reported after reconnecting. The Decline call write still needs a hardware check.
- **Equalizer** displays the on-device preset from Buds On status and allows one explicitly confirmed test of a different standard preset. Custom EQ is read-only. The preset write matches the Samsung app protocol and requires a hardware check.
- The combined **Decline call and Media controls** test preserves Answer/end call and the other untouched gesture bits. It requires a hardware check. Per-side touch-and-hold assignments are read-only in the report.
- Samsung supports Auto Switch on compatible Galaxy devices and on Windows through Galaxy Connect. The existing [GalaxyBudsClient multipoint patch](https://github.com/timschneeb/GalaxyBudsClient/pull/729) has no verified Buds On compatibility.

## Protocol findings

Static analysis used the public Galaxy Buds APK version `9.0.10.1724`, the version reported by the test Galaxy. The APK checksum matched the published value. [Public APK metadata and checksum](https://www.apkmirror.com/apk/samsung-electronics-co-ltd/galaxy-buds/galaxy-buds-9-0-10-1724-release/galaxy-buds-9-0-10-1724-android-apk-download/#safeDownload)

- The SM-U600 handler reads Answer or end call from bit 4 and Decline call from bit 5 of byte 10 in the `0x61` status payload. These offsets are zero-based.
- Samsung changes either setting with a `0x90` request that replaces the touch control state. The first eight payload bytes are one byte per flag, sourced from status bits `7, 3, 2, 1, 0, 4, 5, 6`. The last two bytes are both `1`. The test sources all eight flags from a fresh status message. Samsung's Media controls switch changes bits 3, 2, 1, and 6 together. The combined test clears those four bits and Decline bit 5 in a single frame. The individual selectors still change one bit each. Offline tests verified the frame and guard behavior. Hardware verification covers the Mac Answer or end call Off action and phone restoration.
- Samsung sets one of six standard EQ presets with `0x86` and one byte of preset data. The current preset is byte 9 of `0x61`. An incoming `0x42` with `0x86` and the returned preset is reported separately from full status.
- Samsung uses the high and low nibbles of status byte 11 for left and right hold enablement. The app obtains hold action labels from its own preferences.
- In the SM-U600 capability profile, Samsung removes the Bluetooth multipoint support flag and retains the separate Galaxy Auto Switch capability. The preview keeps the multipoint patch disabled while hardware support remains unverified.

## Important limits

A successful CI build does not prove that the package installs, recognizes Buds On, communicates over Bluetooth, or enables multipoint. The macOS package is unsigned and may need manual approval. Builds are hosted on GitHub-hosted macOS runners; access and quotas depend on GitHub's current policies.

If the run fails, open the failed step in the GitHub Actions log and inspect the error.
