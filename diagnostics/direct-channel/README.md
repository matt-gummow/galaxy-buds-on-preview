# Buds On Connection Check

This Apple Silicon app offers two experiments for Galaxy Buds On (SM-U600). Quit Galaxy Buds Manager from its menu bar icon first. Connection Check uses the Buds already selected in Manager and paired with macOS. The app may request Bluetooth permission.

## Galaxy Book host setup

On the Mac, connect the Buds and confirm you can hear Mac audio. Select **Mac host setup**, click **Set up this Mac…**, then choose **Send once**. The app uses Samsung’s control channel to send the extended version 3 host-setup message from the Galaxy Book recording. A completed write reports what macOS submitted. The Buds' response format for confirming the stored version remains unverified.

Version 1.3 checks the Samsung service class on the open channel. When macOS exposes the class in another entry for the same paired Buds, the entries must identify the same service record and RFCOMM channel. If the cached class information is missing, the app can request the service records once while the channel is open. If verification stops the test, copy the report. The Fold playback steps below apply after macOS confirms the write.

After the write, leave the Mac connected and the Buds out of the case. Reconnect the Fold once using its saved Bluetooth pairing. Play music on the Fold and check whether the Mac still lists the Buds as connected. Check whether Mac music is audible again without selecting Connect on either device. If both hosts retain the Buds, try a Fold call while Mac music is playing and listen for Mac music to resume after hanging up. Copy the app report and record which audio you heard and whether either device needed a manual reconnection.

Revision 3 of the [saved capture reader](https://github.com/matt-gummow/galaxy-buds-on-preview/commit/cc0fa1c0554a8949bdb0cd5463e9921d291ef66e) identified one exact match to the [extended v3 message](https://github.com/Clascheurduturfu/galaxy-continuity-mac/blob/13f0a528aaa28481460578a22853c08363d244f6/Sources/ContinuityCore/BudsProtocol.swift). The optional fields contained zeros. The Book also sent other messages during this connection. This experiment isolates host setup from the later computer handoff request.

## Fold playback check

With Fold music playing through the Buds and the Mac initially disconnected, choose **Test while Fold music is playing**. The Mac opens the control channel without sending an application payload. Select the playback result and copy the report. Each launch allows one experiment. The listener timestamp marks when the result was selected.

## Build and checks

On macOS, run `bash tests/run-tests.sh`, `bash tests/run-ui-tests.sh`, and `bash build.sh /tmp/budson-connection-build`. GitHub Actions runs both fixture suites, builds the installer and verifies the architecture of the packaged executable. The app is ad-hoc signed. The installer is not notarized.
