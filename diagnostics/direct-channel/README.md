# Buds On direct control-channel check

This Apple Silicon diagnostic tests whether a direct open of the cached Samsung SMEP service can coexist with audible Fold playback. The GalaxyBudsClient preview currently requires an established management connection before its handoff test. That connection interrupted Fold playback in the user's test, so the handoff request was never reached.

Quit Galaxy Buds Manager, including its menu bar process. With the Buds connected to the Fold and Fold music audible, launch this app and choose **Test while Fold music is playing**. Select the playback result and copy its report. A Bluetooth permission prompt may appear on first use. Each launch makes at most one opening attempt. Opening the channel may itself cause macOS to connect the audio profiles.

The diagnostic reads GalaxyBudsClient's existing selected-device settings. It matches that Buds On to Apple's paired-device list and checks cached service records for the Samsung SMEP UUID. Missing or ambiguous records produce an explanation. An asynchronous open has a 12-second deadline. An opened channel is observed for at most 15 seconds. The app closes its own channel on a listener result, timeout, window close or quit.

No earbud application payload is sent. The transport contains no settings, firmware, handoff, factory reset, SDP-query or explicit baseband-connection calls. Apple may establish the baseband implicitly when opening RFCOMM. The report contains fixed stage messages, relative times and the listener's observation. It excludes Bluetooth addresses, names, account fields and received packets.

A successful open with continuing Fold audio would establish a usable control connection for the next protocol investigation. It would not establish two simultaneous audio profiles, call priority, or successful MDE configuration.

## Build and checks

Run `bash tests/run-tests.sh`, `bash tests/run-ui-tests.sh`, and `bash build.sh /tmp/budson-connection-build` on macOS. The repository workflow builds and verifies the installer in GitHub Actions. Transport fixtures substitute every paired-device and channel input, exercising ambiguous records, synchronous and late callbacks, cancellation, remote closure and timeout. UI fixtures cover listener results while an open is pending, the observation delay, late callbacks, and automatic closure.

The installer is ad-hoc signed and is not notarized.
