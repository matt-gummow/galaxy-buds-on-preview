# Galaxy Buds On for GalaxyBudsClient (macOS)

This repository builds an Apple Silicon version of [GalaxyBudsClient](https://github.com/timschneeb/GalaxyBudsClient) for Galaxy Buds On (SM-U600). The app uses the Samsung management channel for device status and specific confirmed setting commands.

## Install

The [hardware-checked Apple Silicon build](https://github.com/matt-gummow/galaxy-buds-on-preview/actions/runs/45736098878/artifacts/15079720347) is the current baseline. It confirmed an EQ change on SM-U600 and read the new preset again after reconnecting. Download the artifact, unzip it, and open the included `.pkg`. If the artifact expires, use the workflow for [the baseline build](https://github.com/matt-gummow/galaxy-buds-on-preview/actions/runs/45736098878) as the build reference. macOS may ask you to approve this unsigned installer. The build runs in GitHub Actions and requires no local Xcode or App Store sign-in.

The workflow checks out upstream commit `85dfc8bb39fc45d3c30ecf71ab2c663fb1d41729`, applies `add_buds_on.py`, and builds the native Bluetooth library and app with the pinned cloud toolchain.

## Using the app

| Page | Buds On support |
| --- | --- |
| **Home** | Left earbud, right earbud, and case battery from validated device status. The app groups matching earbud percentages and uses the macOS headset battery when available while waiting for device status. |
| **Touchpad** | Media controls, Answer call or end call, and Decline call. These commands were confirmed on SM-U600 in the preceding hardware previews. Left and right volume hold are available for experimental testing when both hold actions are known. |
| **Equalizer** | Six standard presets from Balanced through Treble boost. Preset writes passed a hardware test in the previous preview. A Custom curve can be read from the device when it returns a supported reply. Custom curve editing remains disabled. |
| **Settings** | Experimental Gaming mode and Pause when one earbud is removed, a reversible read-only mode for the running app, and the connection report. |

Pair the earbuds in macOS Bluetooth first and connect in GalaxyBudsClient. Changes are explicit actions on the selected device. The app checks recent status before sending a change. A matching EQ reply updates the preset without reconnecting. If the earbuds only acknowledge a touch command, select **Refresh status** to check the result. Last reported values stay visible during a management reconnect, and they do not authorize writes. The app sends each setting command once.

Volume hold changes only the selected earbud and preserves the other side. This build supports the Off and Volume values. Actions assigned to an assistant or another behavior require using the phone. A mixed media control state is displayed as unavailable for editing. Active Custom EQ is protected from replacement.

## Connection and multipoint

Open **Settings → Copy Buds On connection report** after connecting or attempting a connection. The same report is saved to `~/Library/Application Support/GalaxyBudsClient/buds-on-connection-report.txt`. It omits Bluetooth addresses and packet dumps.

The report summarizes complete 8-byte `0x76` multipoint notices. It includes the firmware’s support flag, connection state, audio focus, and known streaming profiles. The final three unverified payload bytes are omitted. An earlier SM-U600 report showed the firmware support flag and a multiple-device state. The subsequent simultaneous Galaxy phone and Mac connection attempt failed. That report showed a one-device state with the support flag still set. The current preview supports using one of those audio hosts at a time. Samsung documents Auto Switch for compatible Galaxy devices and Windows PCs running Galaxy Connect. [Samsung Galaxy Buds On](https://www.samsung.com/us/audio-sound/galaxy-buds-on/)

In a Galaxy Book and Galaxy phone test, the listener heard audio switch to the phone and back. During the same recording, the Book requested a disconnect of its classic Bluetooth link to the Buds and reconnected 4.82 seconds after the controller reported the disconnect. The recording covers only the Book and contains no call markers. Whether the phone and Book held simultaneous audio connections during the call is still unknown.

Service discovery identified Samsung’s SMEP service. The Book sent an extended `MDE_VERSION` message 0.685 seconds after reconnecting. The Buds sent a version notification 0.831 seconds later. The reader could not establish whether the two version fields matched. The extended message contains additional fields whose purpose on SM-U600 is unknown. Neither connection interval contained a recognized multipoint command or status report, an observed classic media channel opening (AVDTP), or an observed classic call-audio connection (SCO/eSCO). The recording had incomplete records and the reader did not cover LE Audio. The Fold’s link was outside the capture. This result leaves concurrent audio connections and compatibility with the upstream version-only write unverified.

SM-U600 disables the generic multipoint capability in Samsung’s app profile. The [upstream MDE patch](https://github.com/timschneeb/GalaxyBudsClient/pull/729) is disabled for this model. Factory reset, firmware operations, and generic configuration writes are also disabled.

## Protocol evidence

Analysis used Samsung’s [Galaxy Buds 9.0.10.1724 APK](https://www.apkmirror.com/apk/samsung-electronics-co-ltd/galaxy-buds/galaxy-buds-9-0-10-1724-release/galaxy-buds-9-0-10-1724-android-apk-download/#safeDownload) and the pinned GalaxyBudsClient source. Offsets below refer to the payload and start at zero.

- Validated `0x61` frames have 63-byte payloads. The EQ preset is byte 9. Byte 10 includes Answer/end call in bit 4, Decline in bit 5, and Media controls in bits 3, 2, 1, and 6. The `0x90` command preserves unrelated flags.
- Standard EQ is set with `0x86` and a preset code from 0 to 5. The `0x69` read request accepts a validated six- or seven-row, nine-band reply and displays the last row as Custom.
- The high and low nibbles of byte 11 hold the left and right hold options. The `0x92` command uses both sides, with 0 for Off and 6 for Volume. Other options and assistant subtype writes are disabled.
- The two experimental audio options use `0x85` for Gaming mode (status byte 8) and `0x6C` for Pause when one earbud is removed (status byte 46). Both are binary.
- Native and managed fixtures verify command bytes, checksums, allowed values, preservation of sibling controls, fresh status, and selected-device guards. Per-earbud volume hold, the two experimental audio options, and Custom EQ curve reading still need dedicated hardware validation.
