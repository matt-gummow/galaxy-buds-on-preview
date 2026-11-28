# Buds On and Buds4 Pro connection parity

## Current implementation

The preview's failed ordinary Mac reconnection is not a test of the Buds4 Pro multipoint procedure. The preview deliberately bypasses that procedure for Buds On.

| Path | Buds4 Pro | Buds On preview |
| --- | --- | --- |
| Feature profile | Includes SeamlessConnection and Rename | Empty generic feature rules |
| MDE patch eligibility | Rename feature enables the patcher | Ineligible |
| MDE patch execution | Writes version-only property and checks reply | Additional explicit BudsOn early return |
| Alternative Samsung channel | General SMEP sender | General sender blocked; separate opt-in handoff transport |
| Status and settings | Generic model-specific implementation | Dedicated guarded decoder and settings commands |
| Manager Multipoint | Uses the upstream multipoint patch | Starts from the verified management connection and holds a separate Samsung control channel |

These are application restrictions introduced during protocol validation. They do not prove a hardware restriction. Enabling the Pro flags wholesale would activate command encoders that have not been checked for SM-U600.

## Manager UI parity

Reuse the Manager’s Buds4 Pro controls for features shared with Buds On. Keep their labels, layout, and interactions aligned wherever the behavior matches. Use the selected model’s capabilities to determine which controls appear and which device commands they use.

For Buds On-specific features, place the controls alongside related settings using the Manager’s existing components and interaction patterns.

### Capabilities by model

| Feature | Shared behavior | Manager support for Buds On |
| --- | --- | --- |
| Device switching | Samsung lists Auto Switch for both models. | Multipoint uses the shared Settings panel. Automatic setup after a case cycle needs a hardware check. |
| Battery and EQ | Both expose battery and sound settings. | The shared battery display, menu bar readings, and EQ preset picker use validated Buds On data. Custom EQ curves can be read from supported replies. Editing needs a validated write and readback. |
| Media and calls | Both support play/pause, track navigation, volume, answer/end, and decline. Buds On uses taps and holds. Buds4 Pro uses pinches and swipes. | Touchpad shares call switches and per-ear hold selectors with model-specific labels and actions. Buds On has a tested grouped media switch. |
| Per-ear shortcuts | Samsung lists Google or Bixby and shortcuts such as Spotify and Voice Recorder for both models. | Buds On currently exposes the mapped Off and Volume choices. Extra shortcut and assistant mappings need verification. |
| Find My Earbuds | Samsung Find is listed for both models. | The local ring and stop commands need SM-U600 validation before enabling the shared Find page. |
| 360 Audio | Samsung lists 360 Audio for both and 360 head tracking for Buds4 Pro. | The basic 360 setting needs SM-U600 readback and write validation. |
| Wear detection and balance | The user guides document pause on removal, wear-based call routing, and left/right sound balance. | The shared Advanced switch for pause on removal is experimental on SM-U600. Call routing and balance need SM-U600 command and readback validation. |
| Head gestures and voice control | Nod/shake and voice controls are available on compatible Galaxy devices for both models. | Mac controls need model-specific validation. Head gestures and 360 head tracking are separate capabilities. |
| Audio formats | Both list Auracast and 24-bit / 96 kHz audio on compatible devices. | Format and broadcast availability follow the host and Bluetooth audio path. |

Buds On lists Audio Leakage Reduction and Auto Volume. Buds4 Pro lists Adaptive ANC, Ambient Sound, Adaptive EQ, and 360 Audio with head tracking. Keep those controls tied to the model and verified behavior.

[Official comparison](https://www.samsung.com/us/mobile-audio/galaxy-buds/compare/) · [Touch controls](https://www.samsung.com/us/support/answer/ANS10001318/) · [Buds On specifications](https://www.samsung.com/sec/support/model/SM-U600NZKAKOO/) · [Buds4 Pro specifications](https://www.samsung.com/sec/support/model/SM-R640NZKAKOO/) · [Buds On user guide](https://downloadcenter.samsung.com/content/UM/202610/20261002151858228/U600_UG_CA_ENG_D2.pdf)

## Samsung protocol distinctions

Saved Samsung application disassembly distinguishes three paths:

- Standard SPP `0xAF` carries a boolean for SET_SEAMLESS_CONNECTION.
- Standard SPP `0x20` carries two bytes for SET_MULTIPOINT_STATUS.
- The upstream multipoint patch writes SMEP `0x43` property `0x0B`, MDE_VERSION.

A capability flag suppressing the generic multipoint control cannot establish that the MDE path is unsupported. The original APK is needed to recheck the exact SM-U600 capability assignment and the complete model-specific parser call chain.

The saved status decoder locates a Seamless boolean ten bytes after EQ. Four preceding fields align with the validated Buds On full-status layout, suggesting payload byte19. The original constructor connecting that decoder to SM-U600 status is missing from the saved extracts, and hardware confirmation is outstanding. The preview does not expose a new setting write based on that inference.

## Evidence and remaining work

The Galaxy Book/Fold test demonstrated call switching and music returning. The ordinary Mac/Fold test showed both Fold audio profiles disconnecting after the Mac connection. The Book sent an extended MDE message and a later computer handoff request. The version-only Pro write and its readback have not been validated on SM-U600.

In Connection Check 1.1 the Mac opened the Samsung control channel with Fold music initially audible. No application payload was sent, and the listener reported that the music stopped. This test recorded neither the Fold's profile state nor the exact moment playback stopped.

The revision 3 saved-trace reader matched one outgoing Galaxy Book frame on the confirmed Samsung SMEP service to the extended v3 MDE host-setup format with three zero optional bytes. In that interval the Book also sent computer settings information before setup and a separate handoff request afterward. The notification following setup has no validated version readback. Connection Check 1.2 can send the matched v3 message alone in an opt-in Mac experiment, then the listener can reconnect the Fold and check audio on both devices. A successful local Bluetooth write establishes only submission. Whether this one message is sufficient for two-host audio or call switching on SM-U600 still requires hardware observation.

Battery, standard EQ, media/call touch controls and experimental gaming/pause paths already have dedicated implementations. Generic feature flags for other Pro capabilities need a model-specific audit. Firmware flashing stays disabled under the project requirements.

The 1.2 Mac host setup run on November 27 opened the outgoing channel, then stopped before it attempted the write. The same 1.2 error covered missing service-class evidence on the open device and a changed RFCOMM channel number. The report cannot distinguish those cases. Version 1.3 checks equivalent cached entries for the same service record, can request fresh service information on the open device, and reports the reason when verification stops setup.

The 1.3 hardware run opened the outgoing channel and timed out waiting for the full service lookup. It made no setup write. Version 1.4 uses the cached service lookup pattern used by the upstream Mac transport. It requires the exact Samsung UUID, one matching service and a unique channel assignment consistent with the outgoing connection. An explicit conflicting class, a changed channel or an ambiguous mapping stops setup. An entry without readable class information can still supply a usable UUID-to-channel mapping. The report identifies the basis for proceeding. [Upstream macOS service lookup](https://github.com/timschneeb/GalaxyBudsClient/blob/85dfc8bb39fc45d3c30ecf71ab2c663fb1d41729/GalaxyBudsClient.Platform.OSX/Native/src/Bluetooth.mm#L78-L116)

The 1.4 hardware run completed the write on verified RFCOMM channel 25 and closed its control channel. Mac audio disconnected when the Fold connected. Earbud acceptance and Mac baseband state were unconfirmed.

Version 1.5 keeps the same setup write and leaves the outgoing channel open through the Fold reconnection and Mac playback check. It timestamps any reported channel closure, samples RFCOMM and the Mac baseband separately, and records whether the listener heard Mac audio without manually reconnecting.

In the November 27 1.5 hardware run, macOS completed one write on verified RFCOMM channel 25. The same channel reported open immediately after the write (+1.9 s), when the listener marked the Fold reconnected (+27.7 s), and before app cleanup (+85.9 s). The app logged no channel closure. The listener heard Mac audio through the Buds after the Fold reconnection without manually reconnecting the Mac.

The Mac baseband probe returned disconnected at all three checkpoints, including immediately after the successful write on the open channel. Treat the Mac baseband state as inconclusive for this run. Earbud acceptance of the setup message and whether the Fold retained an active audio profile while the Mac played remain unverified.

In the follow-up 1.5 hardware test, the Fold call automatically took over audio in the Buds while the Mac was playing YouTube. After hang-up, YouTube required pressing Play. Mac audio then played through the Buds without a manual Bluetooth reconnect. This run confirms automatic call handoff and return to Mac audio on demand. Media playback did not resume automatically in this test.

References:
- [Upstream MDE implementation and hardware discussion](https://github.com/timschneeb/GalaxyBudsClient/pull/729)
- [Buds4 Pro feature profile at the pinned upstream revision](https://github.com/timschneeb/GalaxyBudsClient/blob/85dfc8bb39fc45d3c30ecf71ab2c663fb1d41729/GalaxyBudsClient/Model/Specifications/Buds4ProDeviceSpec.cs)
- [Buds4 Pro seamless-setting report](https://github.com/timschneeb/GalaxyBudsClient/pull/729#issuecomment-5829485757)
