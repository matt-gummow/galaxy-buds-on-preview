# Galaxy Buds On for GalaxyBudsClient (macOS)

This repository builds an Apple Silicon version of [GalaxyBudsClient](https://github.com/timschneeb/GalaxyBudsClient) for Galaxy Buds On (SM-U600). The app uses the Samsung management channel for device status and specific confirmed setting commands.

## Install

Open the latest successful [macOS build](https://github.com/matt-gummow/galaxy-buds-on-preview/actions). Download **GalaxyBudsOn-diagnostic-macos-arm64** under Artifacts, unzip it, and open the included `.pkg`. macOS may ask you to approve this unsigned installer. The build runs in GitHub Actions and requires no local Xcode or App Store sign-in.

The workflow checks out upstream commit `85dfc8bb39fc45d3c30ecf71ab2c663fb1d41729`, applies `add_buds_on.py`, and builds the native Bluetooth library and app with the pinned cloud toolchain.

## Using the app

| Page | Buds On support |
| --- | --- |
| **Home** | Left earbud, right earbud, and case battery from validated device status. The app groups matching earbud percentages and uses the macOS headset battery when available while waiting for device status. |
| **Touchpad** | Media controls, Answer call or end call, and Decline call. These commands were confirmed on SM-U600 in the preceding hardware previews. Left and right volume hold are available for experimental testing when both hold actions are known. |
| **Equalizer** | Six standard presets from Balanced through Treble boost. Preset writes passed a hardware test in the previous preview. A Custom curve can be read from the device when it returns a supported reply. Custom curve editing remains disabled. |
| **Settings** | Experimental Gaming mode and Pause when one earbud is removed, a reversible read-only mode for the running app, and the connection report. |

Pair the earbuds in macOS Bluetooth first and connect in GalaxyBudsClient. Changes are explicit actions on the selected device. The app checks the current status and can refresh the management channel to verify a change. It sends each setting command once and never retries a write automatically.

Volume hold changes only the selected earbud and preserves the other side. This build supports the Off and Volume values. Actions assigned to an assistant or another behavior require using the phone. A mixed media control state is displayed as unavailable for editing. Active Custom EQ is protected from replacement.

## Connection and multipoint

Open **Settings → Copy Buds On connection report** after connecting or attempting a connection. The same report is saved to `~/Library/Application Support/GalaxyBudsClient/buds-on-connection-report.txt`. It omits Bluetooth addresses and packet dumps.

The report summarizes complete 8-byte `0x76` multipoint notices. It includes the firmware’s support flag, connection state, audio focus, and known streaming profiles. The final three unverified payload bytes are omitted. Those status fields cannot establish simultaneous audio connections to a specific pair of hosts by themselves. Samsung currently documents Auto Switch for compatible Galaxy devices and Windows PCs running Galaxy Connect.

SM-U600 disables the generic multipoint capability in Samsung’s app profile. The [upstream MDE patch](https://github.com/timschneeb/GalaxyBudsClient/pull/729) is disabled for this model. Factory reset, firmware operations, and generic configuration writes are also disabled.

## Protocol evidence

Analysis used Samsung’s [Galaxy Buds 9.0.10.1724 APK](https://www.apkmirror.com/apk/samsung-electronics-co-ltd/galaxy-buds/galaxy-buds-9-0-10-1724-release/galaxy-buds-9-0-10-1724-android-apk-download/#safeDownload) and the pinned GalaxyBudsClient source. Offsets below refer to the payload and start at zero.

- Validated `0x61` frames are 63 bytes. The EQ preset is byte 9. Byte 10 includes Answer/end call in bit 4, Decline in bit 5, and Media controls in bits 3, 2, 1, and 6. The `0x90` command preserves unrelated flags.
- Standard EQ is set with `0x86` and a preset code from 0 to 5. The `0x69` read request accepts a validated six- or seven-row, nine-band reply and displays the last row as Custom.
- The high and low nibbles of byte 11 hold the left and right hold options. The `0x92` command uses both sides, with 0 for Off and 6 for Volume. Other options and assistant subtype writes are disabled.
- The two experimental audio options use `0x85` for Gaming mode (status byte 8) and `0x6C` for Pause when one earbud is removed (status byte 46). Both are binary.
- Native and managed fixtures verify command bytes, checksums, allowed values, preservation of sibling controls, fresh status, and selected-device guards. The new hold controls, audio options, curve reading, and reconnect behavior still need physical testing on this build.
