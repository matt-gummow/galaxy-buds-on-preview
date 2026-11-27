# Buds On Connection Check

This Apple Silicon app offers two experiments for Galaxy Buds On (SM-U600). Quit Galaxy Buds Manager from its menu bar icon first. Connection Check uses the Buds already selected in Manager and paired with macOS. The app may request Bluetooth permission.

## Galaxy Book host setup

On the Mac, connect the Buds and confirm you can hear Mac audio. Select **Mac host setup**, click **Set up this Mac…**, then choose **Send once**. The app uses Samsung’s control channel to send the extended version 3 host-setup message from the Galaxy Book recording. A completed write reports what macOS submitted. The Buds' response format for confirming the stored version remains unverified.

The check looks up Samsung’s exact service UUID in the selected Buds’ cached records and verifies that it maps uniquely to the outgoing RFCOMM channel. The report records the channel verification before the write attempt. If the records disagree, copy the report.

Version 1.5 holds the original control channel after the same one-time write. Reconnect the Fold once using its saved Bluetooth pairing, then click **Fold reconnected**. Pause Fold audio if it’s playing. Start or resume Mac audio without using Bluetooth Connect or changing the audio output, then choose what you hear through the Buds.

The report timestamps a channel closure if macOS reports one. It includes separate readings for RFCOMM and the Mac Bluetooth baseband after the write, at the Fold reconnection marker, and before the app ends the observation. You can record the audio result even if the control channel closes. Use **Finish early** if the Fold cannot reconnect. Submitting a result, finishing early, or quitting closes any remaining control channel owned by the app. Select **Copy test report** to share the result.

Revision 3 of the [saved capture reader](https://github.com/matt-gummow/galaxy-buds-on-preview/commit/cc0fa1c0554a8949bdb0cd5463e9921d291ef66e) identified one exact match to the [extended v3 message](https://github.com/Clascheurduturfu/galaxy-continuity-mac/blob/13f0a528aaa28481460578a22853c08363d244f6/Sources/ContinuityCore/BudsProtocol.swift). The optional fields contained zeros. The Book also sent other messages during this connection. This experiment isolates host setup from the later computer handoff request.

## Fold playback check

With Fold music playing through the Buds and the Mac initially disconnected, choose **Test while Fold music is playing**. The Mac opens the control channel without sending an application payload. Select the playback result and copy the report. Each launch allows one experiment. The listener timestamp marks when the result was selected.

## Build and checks

On macOS, run `bash tests/run-tests.sh`, `bash tests/run-ui-tests.sh`, and `bash build.sh /tmp/budson-connection-build`. GitHub Actions runs both fixture suites, builds the installer and verifies the architecture of the packaged executable. The app is ad-hoc signed. The installer is not notarized.
