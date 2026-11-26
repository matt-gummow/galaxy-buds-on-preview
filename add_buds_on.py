#!/usr/bin/env python3
"""Galaxy Buds On support for GalaxyBudsClient on macOS.

Usage: python3 add_buds_on.py /path/to/GalaxyBudsClient
Targets upstream commit 85dfc8bb39fc45d3c30ecf71ab2c663fb1d41729.
Uses guarded settings commands and passive model-specific diagnostics.
"""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('Usage: python3 add_buds_on.py /path/to/GalaxyBudsClient')
root = Path(sys.argv[1]).expanduser().resolve()
if not (root / 'GalaxyBudsClient' / 'Model' / 'Constants.cs').exists():
    raise SystemExit(f'Not a GalaxyBudsClient source checkout: {root}')


def replace_once(filename: str, old: str, new: str) -> None:
    p = root / filename
    content = p.read_text(encoding='utf-8-sig')
    if new in content:
        print(f'Already patched: {filename}')
        return
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f'Expected one matching anchor in {filename}; got {count}. Check upstream revision.')
    p.write_text(content.replace(old, new, 1), encoding='utf-8')
    print(f'Patched: {filename}')


def write_once(filename: str, content: str) -> None:
    path = root / filename
    if path.exists() and path.read_text(encoding='utf-8') != content:
        raise RuntimeError(f'Unexpected existing file: {filename}')
    path.write_text(content, encoding='utf-8')
    print(f'Wrote: {filename}')


constants = 'GalaxyBudsClient/Model/Constants.cs'
replace_once(constants,
    '            Buds4Pro = 13\n',
    '            Buds4Pro = 13,\n'
    '            [ModelMetadata(Name = "Galaxy Buds On", FwPattern = "SM-U600", BuildPrefix = "U600")]\n'
    '            BudsOn = 14\n')

helper = 'GalaxyBudsClient/Model/Specifications/DeviceSpecHelper.cs'
replace_once(helper,
    '        Specs.Add(new Buds4DeviceSpec());\n',
    '        Specs.Add(new Buds4DeviceSpec());\n'
    '        Specs.Add(new BudsOnDeviceSpec());\n')
replace_once(helper,
    '    public static IDeviceSpec? FindByDevice(BluetoothDevice device)\n    {\n',
    '    public static IDeviceSpec? FindByDevice(BluetoothDevice device)\n    {\n'
    '        // Identify the new model by its advertised name until its device-ID UUID is known.\n'
    '        // This must precede the generic SPP-service fallback (which assumes Buds2).\n'
    '        if (device.Name.Contains("Buds On", StringComparison.OrdinalIgnoreCase))\n'
    '            return FindByModel(Models.BudsOn);\n\n')

spec = root / 'GalaxyBudsClient/Model/Specifications/BudsOnDeviceSpec.cs'
if not spec.exists():
    spec.write_text('''using System;
using System.Collections.Generic;
using GalaxyBudsClient.Message;
using GalaxyBudsClient.Model.Constants;
using GalaxyBudsClient.Model.Specifications.Touch;

namespace GalaxyBudsClient.Model.Specifications;

/// <summary>
/// EXPERIMENTAL SM-U600 (Galaxy Buds On) profile.
/// Model-specific settings use the dedicated macOS management transport.
/// Standard SPP decoding and the generic send paths are blocked for this model.
/// </summary>
public class BudsOnDeviceSpec : IDeviceSpec
{
    public Dictionary<Features, FeatureRule?> Rules => new();
    public Models Device => Models.BudsOn;
    public string DeviceBaseName => "Buds On";
    public ITouchMap TouchMap => new StubTouchMap();
    public Guid ServiceUuid => Uuids.SppNew;
    public IEnumerable<TrayItemTypes> TrayShortcuts => Array.Empty<TrayItemTypes>();
    public string IconResourceKey => "Pro";
    public int MaximumAmbientVolume => 0;
    public byte StartOfMessage => (byte)MsgConstants.Som;
    public byte EndOfMessage => (byte)MsgConstants.Eom;
}
''',encoding='utf-8')
    print(f'Created: {spec.relative_to(root)}')
else:
    print(f'Already exists: {spec.relative_to(root)}')

bluetooth = 'GalaxyBudsClient/Platform/BluetoothImpl.cs'
replace_once(bluetooth,
    '    public async Task SendAsync(SppMessage msg)\n    {\n',
    '    public async Task SendAsync(SppMessage msg)\n    {\n'
    '        // SM-U600 configuration uses the guarded device-specific writers below.\n'
    '        if (CurrentModel == Models.BudsOn)\n'
    '        {\n'
    '            Log.Warning("Buds On preview: outgoing SPP command blocked");\n'
    '            return;\n'
    '        }\n')
replace_once(bluetooth,
    '    public async Task SendAltAsync(SppAlternativeMessage msg)\n    {\n',
    '    public async Task SendAltAsync(SppAlternativeMessage msg)\n    {\n'
    '        // Block SMEP/MDE property writes (including the multipoint unlock).\n'
    '        if (CurrentModel == Models.BudsOn)\n'
    '        {\n'
    '            Log.Warning("Buds On preview: outgoing SMEP command blocked");\n'
    '            return;\n'
    '        }\n')
replace_once(bluetooth,
    '    public void ProcessDataBlock(List<byte> data, Models targetModel)\n    {\n',
    '    public void ProcessDataBlock(List<byte> data, Models targetModel)\n    {\n'
    '        // Do not parse unknown SM-U600 frames as if they were another Buds model.\n'
    '        if (targetModel == Models.BudsOn)\n'
    '        {\n'
    '            data.Clear();\n'
    '            return;\n'
    '        }\n')

patcher = 'GalaxyBudsClient/Platform/MultipointPatcher.cs'
replace_once(patcher,
    '    public static async Task<bool> ApplyAsync()\n    {\n',
    '    public static async Task<bool> ApplyAsync()\n    {\n'
    '        // The current MDE_VERSION write is untested on SM-U600; do not disconnect\n'
    '        // or send it even when manually invoked from the UI.\n'
    '        if (BluetoothImpl.Instance.CurrentModel == GalaxyBudsClient.Model.Constants.Models.BudsOn)\n'
    '        {\n'
    '            Log.Warning("Buds On preview: experimental multipoint patch blocked");\n'
    '            return false;\n'
    '        }\n')

replace_once('GalaxyBudsClient.Platform.OSX/Unmanaged.cs',
    '    internal static extern unsafe BT_CONN_RESULT bt_connect(BluetoothImpl* self, string mac, byte* uuid);\n',
    '''    internal static extern unsafe BT_CONN_RESULT bt_connect(BluetoothImpl* self, string mac, byte* uuid);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    internal delegate void Bt_OnDiagnostic(IntPtr message);

    [DllImport(DSO.Name, CallingConvention = CallingConvention.Cdecl)]
    internal static extern unsafe BT_CONN_RESULT bt_connect_diagnostic(
        BluetoothImpl* self, string mac, byte* uuid, Bt_OnDiagnostic callback);

''')

mac_bluetooth = 'GalaxyBudsClient.Platform.OSX/BluetoothService.cs'
replace_once(mac_bluetooth,
    '        private string _currentUuid = string.Empty;\n',
    '''        private string _currentUuid = string.Empty;
        private Action<string>? _currentDiagnostics;
        private Action<byte[], ulong>? _currentDiagnosticRx;
        private Action? _currentDiagnosticStarted;
''')
replace_once(mac_bluetooth,
    'await ConnectAsync(_currentMac, _currentUuid, CancellationToken.None);',
    'await ConnectAsync(_currentMac, _currentUuid, CancellationToken.None,\n                            _currentDiagnostics, _currentDiagnosticRx, _currentDiagnosticStarted);')
replace_once(mac_bluetooth,
    '                NewDataAvailable?.Invoke(this, byteArray);\n',
    '''                if (_currentDiagnosticRx is { } diagnosticRx)
                    diagnosticRx(byteArray, stamp);
                else
                    NewDataAvailable?.Invoke(this, byteArray);
''')
replace_once(mac_bluetooth,
    '        public async Task ConnectAsync(string macAddress, string uuid, CancellationToken cancelToken)\n',
    '''        public Task ConnectAsync(string macAddress, string uuid, CancellationToken cancelToken) =>
            ConnectAsync(macAddress, uuid, cancelToken, null, null, null);

        public async Task ConnectAsync(string macAddress, string uuid, CancellationToken cancelToken,
            Action<string>? diagnostics, Action<byte[], ulong>? diagnosticRx, Action? diagnosticStarted)
''')
replace_once(mac_bluetooth,
    '                    Log.Debug("OSX.BluetoothService: Already connected, skipped");\n',
    '''                    Log.Debug("OSX.BluetoothService: Already connected, skipped");
                    diagnostics?.Invoke(_currentDiagnostics != null && _currentMac == macAddress
                        ? "RFCOMM diagnostic channel already open"
                        : "Another RFCOMM channel is already open; no Buds On service probe ran");
''')
replace_once(mac_bluetooth,
    '                _currentUuid = uuid;\n',
    '''                _currentUuid = uuid;
                _currentDiagnostics = diagnostics;
                _currentDiagnosticRx = diagnosticRx;
                _currentDiagnosticStarted = diagnosticStarted;
                diagnosticStarted?.Invoke();
                diagnostics?.Invoke($"Requested RFCOMM service UUID: {uuid}");
''')
replace_once(mac_bluetooth,
    '                        result = Bluetooth.bt_connect(_nativePtr, macAddress, rawUuid);\n',
    '''                        result = diagnostics == null
                            ? Bluetooth.bt_connect(_nativePtr, macAddress, rawUuid)
                            : Bluetooth.bt_connect_diagnostic(_nativePtr, macAddress, rawUuid,
                                message => diagnostics(NativeUtf8ToString(message)));
''')
replace_once(mac_bluetooth,
    '                if (result != BT_CONN_RESULT.BT_CONN_SUCCESS)\n',
    '''                diagnostics?.Invoke($"RFCOMM connection result: {result}");

                if (result != BT_CONN_RESULT.BT_CONN_SUCCESS)
''')
replace_once(mac_bluetooth,
    '                    fixed (byte* raw = data)\n',
    '''                    // This generic path never writes to a diagnostic connection, even
                    // if the UI has selected another device while the channel is still active.
                    if (_currentDiagnostics != null)
                        return;

                    fixed (byte* raw = data)
''')


replace_once(bluetooth,
    '    private void OnDisconnected(object? sender, string reason)\n    {\n',
    '''    private void OnDisconnected(object? sender, string reason)
    {
        if (CurrentModel == Models.BudsOn)
            BudsOnDiagnostics.ResetReceiveStream();
''')


replace_once(bluetooth,
    '    public async Task DisconnectAsync(bool alternative = false)\n    {\n',
    '''    public async Task DisconnectAsync(bool alternative = false)
    {
        if (CurrentModel == Models.BudsOn)
            BudsOnDiagnostics.ResetReceiveStream();
''')
replace_once(bluetooth,
    '    private void OnBluetoothError(BluetoothException exception)\n    {\n',
    '''    private void OnBluetoothError(BluetoothException exception)
    {
        if (CurrentModel == Models.BudsOn)
            BudsOnDiagnostics.ResetReceiveStream();
''')

write_once('GalaxyBudsClient/Platform/BudsOnFrameProbe.cs', '''using System;
using System.Collections.Generic;
using GalaxyBudsClient.Message;
using GalaxyBudsClient.Utils;
using static GalaxyBudsClient.Message.Decoder.MultipointInfoDecoder;

namespace GalaxyBudsClient.Platform;

// Caller serializes all access. The stream buffer retains at most one maximum-size
// modern SPP frame. The report contains metadata and specific diagnostic candidates.
internal sealed class BudsOnFrameProbe
{
    private const byte Start = (byte)MsgConstants.Som;
    private const byte End = (byte)MsgConstants.Eom;
    private const int MaximumBodyLength = 0x03ff;
    private const int MaximumSignatures = 32;
    private const int MaximumSettingsObservations = 32;
    private const int MaximumMultipointObservations = 24;
    private const int BudsOnMultipointPayloadLength = 8;
    private const StreamingMaskFlags KnownStreamingProfiles = StreamingMaskFlags.A2dpMusicNotCall |
        StreamingMaskFlags.HfpCall | StreamingMaskFlags.CisMusicNotCall |
        StreamingMaskFlags.Bis | StreamingMaskFlags.CisCall;

    private static readonly (StreamingMaskFlags Flag, string Label)[] StreamingProfiles =
    [
        (StreamingMaskFlags.A2dpMusicNotCall, "A2DP media"),
        (StreamingMaskFlags.HfpCall, "HFP call"),
        (StreamingMaskFlags.CisMusicNotCall, "CIS media"),
        (StreamingMaskFlags.Bis, "BIS"),
        (StreamingMaskFlags.CisCall, "CIS call")
    ];
    private const int EqualizerOffset = 9;
    private const int GestureFlagsOffset = 10;
    private const int CallDoubleTapBit = 4;
    private const int CallHoldBit = 5;
    private const int HoldStatusOffset = 11;
    private const int GamingModeOffset = 8;
    private const int PauseOnRemovalOffset = 46;
    private const byte MediaControlsMask = 0x4E;

    internal readonly record struct SettingsSnapshot(byte EqualizerCode, byte GestureFlags,
        byte LeftHoldStatus, byte RightHoldStatus, byte GamingMode, byte PauseOnRemoval);

    internal readonly record struct ControlStatus(long Frame, SettingsSnapshot Settings)
    {
        public byte Flags => Settings.GestureFlags;
        public byte Preset => Settings.EqualizerCode;
    }

    private readonly record struct MultipointSnapshot(byte Revision, bool? Supported,
        bool? OneDevice, bool? BackgroundFocus, StreamingMaskFlags Profiles, bool UnknownProfileBits);

    private readonly record struct MultipointObservation(long Connection, long FirstFrame,
        long LastFrame, long Count, MultipointSnapshot Snapshot);

    private readonly byte[] _pending = new byte[MaximumBodyLength + 4];
    private readonly Dictionary<(byte Id, int PayloadLength), long> _signatures = new();
    private readonly Queue<(long Connection, long Frame, SettingsSnapshot Settings)> _settingsObservations = new();
    private readonly LinkedList<MultipointObservation> _multipointObservations = new();
    private long _multipointFrames;
    private long _multipointSessionFrames;
    private bool _observeSettings;
    private long _settingsConnection;
    private SettingsSnapshot? _lastSettings;
    private byte? _lastEqualizerPreset;
    private (int? Left, int? Right, int? Case) _lastBattery;
    public ControlStatus? LatestControlStatus { get; private set; }
    public SettingsSnapshot? LastSettings => _lastSettings;
    public (long Frame, byte Value)? GamingModeAck { get; private set; }
    public (long Frame, byte Value)? PauseOnRemovalAck { get; private set; }
    public (long Frame, byte Left, byte Right)? HoldAck { get; private set; }
    public (long Frame, sbyte[] Custom)? EqualizerCurves { get; private set; }
    public (long Frame, byte Preset)? EqualizerCommandAck { get; private set; }
    public byte? EqualizerPreset => _lastEqualizerPreset is <= 6 ? _lastEqualizerPreset : null;
    public void RecordConfirmedEqualizer(byte preset) => _lastEqualizerPreset = preset;
    public long CallCommandAckFrame { get; private set; }
    public bool HasPartialFrame => _pendingLength != 0;
    public long LastFrame => _validFrames;
    private int _pendingLength;
    private long _validFrames;
    private long _otherSignatures;
    private (long Count, byte Left, byte Right, byte Case) _basicStatus;
    private (long Count, byte Left, byte Right, byte Case) _extendedStatus;

    public void ResetStream(bool observeSettings, bool newSettingsDevice)
    {
        _pendingLength = 0;
        _basicStatus = default;
        _extendedStatus = default;
        _observeSettings = observeSettings;
        _multipointSessionFrames = 0;
        LatestControlStatus = null;
        CallCommandAckFrame = 0;
        EqualizerCommandAck = null;
        GamingModeAck = null;
        PauseOnRemovalAck = null;
        HoldAck = null;
        EqualizerCurves = null;

        if (newSettingsDevice)
        {
            _lastSettings = null;
            _lastEqualizerPreset = null;
            _lastBattery = default;
            _settingsObservations.Clear();
            _multipointObservations.Clear();
            _multipointFrames = 0;
            _settingsConnection = 0;
        }

        if (observeSettings)
            _settingsConnection++;
    }

    public void Append(byte[] chunk)
    {
        foreach (var value in chunk)
        {
            if (_pendingLength == 0 && value != Start)
            {
                LatestControlStatus = null;
                continue;
            }

            _pending[_pendingLength++] = value;
            DrainFrames();
        }
    }

    private void DrainFrames()
    {
        while (_pendingLength >= 3)
        {
            int header = _pending[1] | (_pending[2] << 8);
            int size = header & MaximumBodyLength;
            if (size < 3)
            {
                LatestControlStatus = null;
                MoveToNextStart(1);
                continue;
            }

            int frameLength = size + 4;
            if (_pendingLength < frameLength)
                return;

            if (_pending[frameLength - 1] != End || !HasValidChecksum(size))
            {
                LatestControlStatus = null;
                MoveToNextStart(1);
                continue;
            }

            RecordFrame(_pending[3], size - 3, isFragment: (header & 0x2000) != 0);
            MoveToNextStart(frameLength);
        }
    }

    private bool HasValidChecksum(int size)
    {
        var crc = unchecked((ushort)Crc16.crc16_ccitt(new ArraySegment<byte>(_pending, 3, size - 2)));
        int received = _pending[size + 1] | (_pending[size + 2] << 8);
        return received == crc;
    }

    private void MoveToNextStart(int offset)
    {
        var next = Array.IndexOf(_pending, Start, offset, _pendingLength - offset);
        if (next < 0)
        {
            _pendingLength = 0;
            return;
        }

        _pendingLength -= next;
        Array.Copy(_pending, next, _pending, 0, _pendingLength);
    }

    private void RecordFrame(byte id, int payloadLength, bool isFragment)
    {
        _validFrames++;
        var signature = (id, payloadLength);
        if (_signatures.TryGetValue(signature, out long count))
            _signatures[signature] = count + 1;
        else if (_signatures.Count < MaximumSignatures)
            _signatures.Add(signature, 1);
        else
            _otherSignatures++;

        if (isFragment)
        {
            if (id == (byte)MsgIds.EXTENDED_STATUS_UPDATED)
                LatestControlStatus = null;
            return;
        }

        var payload = _pending.AsSpan(4, payloadLength);
        if (_observeSettings && id == (byte)MsgIds.MULTIPOINT_INFO &&
            payloadLength == BudsOnMultipointPayloadLength)
            RecordMultipointStatus(payload);
        if (_observeSettings && id == 0x42 && payload.Length > 0)
        {
            if (payload[0] == 0x90)
                CallCommandAckFrame = _validFrames;
            if (payload.Length >= 2)
            {
                if (payload.Length == 2 && payload[0] == 0x86 && payload[1] <= 5)
                    EqualizerCommandAck = (_validFrames, payload[1]);
                if (payload[0] == 0x85 && payload[1] <= 1)
                    GamingModeAck = (_validFrames, payload[1]);
                if (payload[0] == 0x6C && payload[1] <= 1)
                    PauseOnRemovalAck = (_validFrames, payload[1]);
            }
            if (payload.Length >= 5 && payload[0] == 0x92 && payload[1] is (0 or 6) &&
                payload[2] is (0 or 6) && payload[3] == 0 && payload[4] == 0)
                HoldAck = (_validFrames, payload[1], payload[2]);
        }
        if (_observeSettings && id == 0x69)
            RecordEqualizerCurves(payload);
        if (id == (byte)MsgIds.STATUS_UPDATED && payloadLength >= 7)
            RecordBatteryCandidate(payload, batteryOffset: 1, ref _basicStatus);
        if (id == (byte)MsgIds.EXTENDED_STATUS_UPDATED)
        {
            if (payloadLength == 63 && RecordBatteryCandidate(payload, batteryOffset: 2, ref _extendedStatus))
                RecordSettingsCandidate(payload);
            else
                LatestControlStatus = null;
        }
    }

    private void RecordMultipointStatus(ReadOnlySpan<byte> payload)
    {
        // Samsung's Able handler reads five fields. The final three bytes are unverified.
        var flags = (StreamingMaskFlags)payload[4];
        var snapshot = new MultipointSnapshot(payload[0], ReadBinaryField(payload[1]),
            ReadBinaryField(payload[2]), ReadBinaryField(payload[3]),
            flags & KnownStreamingProfiles, (flags & ~KnownStreamingProfiles) != 0);
        _multipointFrames++;
        _multipointSessionFrames++;

        if (_multipointObservations.Last is { } last && last.Value.Connection == _settingsConnection &&
            last.Value.Snapshot == snapshot)
        {
            last.Value = last.Value with { LastFrame = _validFrames, Count = last.Value.Count + 1 };
            return;
        }

        if (_multipointObservations.Count == MaximumMultipointObservations)
            _multipointObservations.RemoveFirst();
        _multipointObservations.AddLast(new MultipointObservation(
            _settingsConnection, _validFrames, _validFrames, 1, snapshot));
    }

    private static bool? ReadBinaryField(byte value) => value switch
    {
        0 => false,
        1 => true,
        _ => null
    };

    private void RecordEqualizerCurves(ReadOnlySpan<byte> payload)
    {
        const int bandCount = 9;
        if (payload.Length < 2 || payload[0] is not (6 or 7) || payload[1] != bandCount ||
            payload.Length != 2 + payload[0] * bandCount)
            return;

        foreach (var value in payload[2..])
            if (unchecked((sbyte)value) is < -10 or > 10)
                return;

        var custom = new sbyte[bandCount];
        var customRow = payload[^bandCount..];
        for (var i = 0; i < custom.Length; i++)
            custom[i] = unchecked((sbyte)customRow[i]);
        EqualizerCurves = (_validFrames, custom);
    }

    private void RecordSettingsCandidate(ReadOnlySpan<byte> payload)
    {
        if (!_observeSettings)
            return;

        var assignments = payload[HoldStatusOffset];
        var settings = new SettingsSnapshot(payload[EqualizerOffset], payload[GestureFlagsOffset],
            (byte)(assignments >> 4), (byte)(assignments & 0x0F),
            payload[GamingModeOffset], payload[PauseOnRemovalOffset]);
        LatestControlStatus = new ControlStatus(_validFrames, settings);
        _lastEqualizerPreset = settings.EqualizerCode;
        var (_, left, right, caseBattery) = _extendedStatus;
        _lastBattery = (left <= 100 ? left : null, right <= 100 ? right : null,
            caseBattery <= 100 ? caseBattery : null);
        var unchanged = _extendedStatus.Count > 1 && _lastSettings == settings;
        _lastSettings = settings;
        if (unchanged)
            return;
        if (_settingsObservations.Count == MaximumSettingsObservations)
            _settingsObservations.Dequeue();
        _settingsObservations.Enqueue((_settingsConnection, _validFrames, settings));
    }

    private static bool RecordBatteryCandidate(ReadOnlySpan<byte> payload, int batteryOffset,
        ref (long Count, byte Left, byte Right, byte Case) status)
    {
        var left = payload[batteryOffset];
        var right = payload[batteryOffset + 1];
        var placement = payload[batteryOffset + 4];
        var caseBattery = payload[batteryOffset + 5];
        if (left > 101 || right > 101 || caseBattery > 101 ||
            payload[batteryOffset + 2] > 1 || payload[batteryOffset + 3] > 1 ||
            (placement >> 4) > 4 || (placement & 0x0f) > 4)
            return false;

        status = (status.Count + 1, left, right, caseBattery);
        return true;
    }

    public (int? Left, int? Right, int? Case) GetBattery() => _lastBattery;

    public IEnumerable<string> SnapshotLines()
    {
        yield return $"CRC-valid modern Samsung SPP frames: {_validFrames}";
        foreach (var entry in _signatures)
            yield return $"SPP ID 0x{entry.Key.Id:X2}, payload length {entry.Key.PayloadLength}: {entry.Value} frame(s)";
        if (_otherSignatures > 0)
            yield return $"Frames with other ID/length signatures: {_otherSignatures}";
        if (_basicStatus.Count >= 2)
            yield return FormatBatteryCandidate((byte)MsgIds.STATUS_UPDATED, _basicStatus);
        if (_extendedStatus.Count >= 1)
            yield return FormatBatteryCandidate((byte)MsgIds.EXTENDED_STATUS_UPDATED, _extendedStatus);
        if (_settingsObservations.Count > 0)
            yield return "Buds On settings observations (extended status 0x61)";
        foreach (var (connection, frame, settings) in _settingsObservations)
            yield return $"  Connection {connection}, valid frame {frame} | {FormatSettings(settings)}";
        if (_multipointFrames > 0 || _observeSettings)
        {
            yield return $"Buds On multipoint status (0x76, complete 8-byte payloads): {_multipointFrames} frame(s)";
            yield return _observeSettings
                ? $"  Current connection {_settingsConnection}: {_multipointSessionFrames} frame(s)"
                : "  No current Buds On receive session";
            foreach (var (connection, firstFrame, lastFrame, count, snapshot) in _multipointObservations)
            {
                var frameRange = firstFrame == lastFrame ? $"{firstFrame}" : $"{firstFrame}–{lastFrame}";
                yield return $"  Connection {connection}, valid frame(s) {frameRange} | " +
                    $"{count} matching sample(s) | {FormatMultipointStatus(snapshot)}";
            }
        }
    }

    private static string FormatMultipointStatus(MultipointSnapshot snapshot)
    {
        var support = snapshot.Supported switch { true => "yes", false => "no", null => "unknown" };
        var connection = snapshot.OneDevice switch
        {
            true => "one-device state",
            false => "multiple-device state",
            null => "unknown"
        };
        var focus = snapshot.BackgroundFocus switch
        {
            true => "background",
            false => "foreground",
            null => "unknown"
        };
        var profiles = new List<string>();
        foreach (var (flag, label) in StreamingProfiles)
        {
            if ((snapshot.Profiles & flag) != 0)
                profiles.Add(label);
        }
        if (snapshot.UnknownProfileBits)
            profiles.Add("unrecognized profile bits");

        var streams = profiles.Count == 0 ? "none" : string.Join(", ", profiles);
        return $"Revision {snapshot.Revision} | Device-reported support {support} | " +
            $"Connection state {connection} | Audio focus {focus} | Streams {streams}";
    }

    private static string FormatSettings(SettingsSnapshot settings)
    {
        var flags = settings.GestureFlags;
        return $"EQ code {settings.EqualizerCode} | Hold status nibbles L={settings.LeftHoldStatus} R={settings.RightHoldStatus} | " +
            $"Media controls {DescribeMediaControls(flags)} | Tap {FormatFlag(flags, 3)}, double {FormatFlag(flags, 2)}, " +
            $"triple {FormatFlag(flags, 1)}, media hold {FormatFlag(flags, 6)} | " +
            $"Call double {FormatFlag(flags, CallDoubleTapBit)}, call hold {FormatFlag(flags, CallHoldBit)} | " +
            $"Gaming mode {DescribeBinary(settings.GamingMode)}, pause on removal {DescribeBinary(settings.PauseOnRemoval)}";
    }

    private static string DescribeBinary(byte value) => value switch
    {
        0 => "off",
        1 => "on",
        _ => "unknown"
    };

    private static string DescribeMediaControls(byte flags) => (flags & MediaControlsMask) switch
    {
        MediaControlsMask => "on",
        0 => "off",
        _ => "mixed"
    };

    private static bool IsFlagSet(byte flags, int bit) => (flags & (1 << bit)) != 0;

    private static string FormatFlag(byte flags, int bit) => IsFlagSet(flags, bit) ? "on" : "off";

    private static string FormatBatteryCandidate(byte id, (long Count, byte Left, byte Right, byte Case) status) =>
        $"Candidate battery fields from {status.Count} matching 0x{id:X2} status frames: " +
        $"left {FormatPercent(status.Left)}, right {FormatPercent(status.Right)}, case {FormatPercent(status.Case)}";

    private static string FormatPercent(byte value) => value == 101 ? "unavailable" : $"{value}%";
}
''')

write_once('GalaxyBudsClient/Platform/BudsOnMacBattery.cs', '''using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace GalaxyBudsClient.Platform;

internal static class BudsOnMacBattery
{
    public static async Task<int?> ReadAsync(string deviceName, CancellationToken cancellationToken)
    {
        if (!OperatingSystem.IsMacOS() || string.IsNullOrWhiteSpace(deviceName))
            return null;

        cancellationToken.ThrowIfCancellationRequested();
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(2));
        using var process = new Process
        {
            StartInfo = new ProcessStartInfo("/usr/bin/pmset")
            {
                ArgumentList = { "-g", "accps" },
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            }
        };

        try
        {
            if (!process.Start())
                return null;

            var output = process.StandardOutput.ReadToEndAsync(deadline.Token);
            var errors = process.StandardError.ReadToEndAsync(deadline.Token);
            await Task.WhenAll(output, errors, process.WaitForExitAsync(deadline.Token)).ConfigureAwait(false);
            return process.ExitCode == 0 ? Parse(await output.ConfigureAwait(false), deviceName) : null;
        }
        catch (OperationCanceledException)
        {
            try
            {
                process.Kill();
            }
            catch (InvalidOperationException)
            {
                // pmset exited while the cancellation was observed.
            }
            catch (Win32Exception)
            {
                // The accessory reading is unavailable if pmset cannot be stopped.
            }
            cancellationToken.ThrowIfCancellationRequested();
            return null;
        }
        catch (Exception ex) when (ex is Win32Exception or IOException or InvalidOperationException)
        {
            return null;
        }
    }

    internal static int? Parse(string output, string deviceName)
    {
        var selectedName = NormalizeName(deviceName);
        if (selectedName.Length == 0)
            return null;

        using var lines = new StringReader(output);
        var matched = false;
        int? percentage = null;
        while (lines.ReadLine() is { } line)
        {
            line = line.Trim();
            var idStart = line.LastIndexOf(" (id=", StringComparison.Ordinal);
            if (!line.StartsWith('-') || idStart <= 1 ||
                !string.Equals(NormalizeName(line[1..idStart]), selectedName, StringComparison.OrdinalIgnoreCase))
                continue;

            var idEnd = line.IndexOf(')', idStart);
            if (idEnd < 0)
                continue;

            var reading = line[(idEnd + 1)..].TrimStart();
            if (reading.Contains("present: false", StringComparison.OrdinalIgnoreCase))
                continue;

            if (matched)
                return null;
            matched = true;

            var percentEnd = reading.IndexOf("%;", StringComparison.Ordinal);
            if (percentEnd > 0 && int.TryParse(reading.AsSpan(0, percentEnd), NumberStyles.None,
                    CultureInfo.InvariantCulture, out var value) && value is >= 0 and <= 100)
                percentage = value;
        }

        return percentage;
    }

    private static string NormalizeName(string name) =>
        name.Normalize(NormalizationForm.FormC).Replace('\\u2019', '\\'').Replace('\\u2018', '\\'').Trim();
}
''')

write_once('GalaxyBudsClient/Platform/BudsOnDiagnostics.cs', '''using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading;
using GalaxyBudsClient.Model.Config;
using GalaxyBudsClient.Model.Constants;

namespace GalaxyBudsClient.Platform;

internal static class BudsOnDiagnostics
{
    private static readonly object Sync = new();
    private static readonly Queue<string> Events = new();
    private static readonly List<int> FirstChunkLengths = new();
    private static readonly BudsOnFrameProbe FrameProbe = new();
    private static readonly Timer ReportTimer = new(_ => SaveReport());
    private static bool _savePending;
    private static long _chunks;
    private static long _bytes;
    private static int? _macBattery;
    private static Device? _receiveDevice;
    private static Device? _settingsDevice;
    private static long _receiveSession;
    private static ulong _receiveStamp;
    private static long _statusObservedAt;
    private static long _attemptedEqualizerStatusFrame;
    private static (long Barrier, byte Target)? _pendingEqualizerReply;
    private static (long Frame, byte Preset, long ObservedAt)? _confirmedEqualizerReply;
    private static ulong _attemptedSettingsStamp;
    private static readonly Dictionary<byte, long> AttemptedOptionFrames = new();

    internal enum Option
    {
        AnswerOrEnd,
        Decline,
        Media,
        LeftHoldVolume,
        RightHoldVolume,
        GamingMode,
        PauseOnRemoval
    }

    internal readonly record struct OptionSample(long Session, bool CurrentValue, byte Flags, byte UnchangedHold);
    internal readonly record struct OptionWrite(ulong Stamp, long Session, long ReplyBarrier, byte Flags,
        byte Value, byte Sibling, byte UnchangedHold, byte Opcode, byte Mask);

    internal readonly record struct EqualizerSample(long Session, long Frame, byte Preset);

    public static string? GetEqualizerPresetName(byte preset) => preset switch
    {
        0 => "Balanced",
        1 => "Bass boost",
        2 => "Smooth",
        3 => "Dynamic",
        4 => "Clear",
        5 => "Treble boost",
        6 => "Custom",
        _ => null
    };

    public static byte? GetEqualizerPreset(Device device)
    {
        lock (Sync)
            return ReferenceEquals(_receiveDevice, device) ? FrameProbe.EqualizerPreset : null;
    }

    // Call and EQ writes change different fields. Each may consume a fresh status once.
    // The native transport also requires a new receive stamp between any two writes.
    private static BudsOnFrameProbe.ControlStatus? GetFreshTestStatus(Device device)
    {
        if (!ReferenceEquals(_receiveDevice, device) || _receiveStamp == 0 || _receiveStamp == _attemptedSettingsStamp ||
            FrameProbe.HasPartialFrame || Stopwatch.GetElapsedTime(_statusObservedAt) > TimeSpan.FromSeconds(60))
            return null;

        return FrameProbe.LatestControlStatus;
    }

    // The EQ echo refreshes only the scalar EQ field. Full-vector controls
    // still use only a fresh extended-status sample through GetFreshTestStatus.
    private static EqualizerSample? GetLiveEqualizerSample(Device device)
    {
        if (!ReferenceEquals(_receiveDevice, device) || _receiveStamp == 0 || FrameProbe.HasPartialFrame ||
            FrameProbe.LatestControlStatus is not { } status)
            return null;

        if (_confirmedEqualizerReply is { } reply && reply.Frame > status.Frame)
            return Stopwatch.GetElapsedTime(reply.ObservedAt) <= TimeSpan.FromSeconds(60)
                ? new EqualizerSample(_receiveSession, reply.Frame, reply.Preset) : null;

        return status.Preset <= 6 && Stopwatch.GetElapsedTime(_statusObservedAt) <= TimeSpan.FromSeconds(60)
            ? new EqualizerSample(_receiveSession, status.Frame, status.Preset) : null;
    }

    public static bool HasLiveBudsOnEqualizer(Device device)
    {
        lock (Sync)
            return GetLiveEqualizerSample(device) != null;
    }

    public static EqualizerSample? GetEqualizerTestSample(Device device)
    {
        lock (Sync)
        {
            if (_receiveStamp == _attemptedSettingsStamp ||
                GetLiveEqualizerSample(device) is not { Preset: <= 5 } sample ||
                sample.Frame == _attemptedEqualizerStatusFrame)
                return null;

            return sample;
        }
    }

    public static (ulong Stamp, EqualizerSample Sample, long ReplyBarrier)? TakeEqualizerTestSample(
        Device device, EqualizerSample expected, byte targetPreset)
    {
        lock (Sync)
        {
            if (targetPreset > 5 || GetEqualizerTestSample(device) is not { } current ||
                current.Session != expected.Session || current.Preset != expected.Preset ||
                current.Preset == targetPreset)
                return null;

            _attemptedEqualizerStatusFrame = current.Frame;
            _attemptedSettingsStamp = _receiveStamp;
            var barrier = FrameProbe.LastFrame;
            _pendingEqualizerReply = (barrier, targetPreset);
            return (_receiveStamp, current, barrier);
        }
    }

    public static (byte? Preset, byte? AcknowledgedPreset)? GetEqualizerTestReadback(
        Device device, long session, long replyBarrier)
    {
        lock (Sync)
        {
            if (!ReferenceEquals(_receiveDevice, device) || _receiveSession != session)
                return null;

            byte? preset = FrameProbe.LatestControlStatus is { } status && status.Frame > replyBarrier
                ? status.Preset
                : null;
            byte? acknowledged = FrameProbe.EqualizerCommandAck is { } ack && ack.Frame > replyBarrier
                ? ack.Preset
                : null;
            return (preset, acknowledged);
        }
    }

    public static bool ConfirmEqualizerReply(Device device, long session, long replyBarrier, byte targetPreset)
    {
        lock (Sync)
        {
            if (!ReferenceEquals(_receiveDevice, device) || _receiveSession != session ||
                _pendingEqualizerReply != (replyBarrier, targetPreset) ||
                FrameProbe.EqualizerCommandAck is not { } reply || reply.Frame <= replyBarrier ||
                reply.Preset != targetPreset ||
                FrameProbe.LatestControlStatus is not { } status || status.Frame > reply.Frame)
                return false;

            _pendingEqualizerReply = null;
            _confirmedEqualizerReply = (reply.Frame, reply.Preset, Stopwatch.GetTimestamp());
            FrameProbe.RecordConfirmedEqualizer(reply.Preset);
            ScheduleSave();
            return true;
        }
    }

    private static byte OptionCommand(Option option) => option switch
    {
        Option.AnswerOrEnd or Option.Decline or Option.Media => 0x90,
        Option.LeftHoldVolume or Option.RightHoldVolume => 0x92,
        Option.GamingMode => 0x85,
        Option.PauseOnRemoval => 0x6C,
        _ => 0
    };

    private static byte GestureMask(Option option) => option switch
    {
        Option.AnswerOrEnd => 0x10,
        Option.Decline => 0x20,
        Option.Media => 0x4E,
        _ => 0
    };

    private static bool? ReadBinary(byte value) => value switch { 0 => false, 1 => true, _ => null };

    private static bool? ReadHold(byte value) => value switch { 0 => false, 6 => true, _ => null };

    private static byte HoldSibling(BudsOnFrameProbe.SettingsSnapshot status, Option option) => option switch
    {
        Option.LeftHoldVolume => status.RightHoldStatus,
        Option.RightHoldVolume => status.LeftHoldStatus,
        _ => 0
    };

    private static bool? ReadOption(BudsOnFrameProbe.SettingsSnapshot status, Option option) => option switch
    {
        Option.AnswerOrEnd => (status.GestureFlags & 0x10) != 0,
        Option.Decline => (status.GestureFlags & 0x20) != 0,
        Option.Media => (status.GestureFlags & 0x4E) switch { 0 => false, 0x4E => true, _ => null },
        Option.LeftHoldVolume when ReadHold(status.RightHoldStatus) != null => ReadHold(status.LeftHoldStatus),
        Option.RightHoldVolume when ReadHold(status.LeftHoldStatus) != null => ReadHold(status.RightHoldStatus),
        Option.GamingMode => ReadBinary(status.GamingMode),
        Option.PauseOnRemoval => ReadBinary(status.PauseOnRemoval),
        _ => null
    };

    public static bool? GetControlValue(Device device, Option option)
    {
        lock (Sync)
            return ReferenceEquals(_receiveDevice, device) && FrameProbe.LastSettings is { } status
                ? ReadOption(status, option)
                : null;
    }

    public static OptionSample? GetOptionSample(Device device, Option option)
    {
        lock (Sync)
        {
            var opcode = OptionCommand(option);
            if (opcode == 0 || GetFreshTestStatus(device) is not { } status ||
                AttemptedOptionFrames.GetValueOrDefault(opcode) == status.Frame ||
                ReadOption(status.Settings, option) is not bool value)
                return null;

            return new OptionSample(_receiveSession, value, status.Flags, HoldSibling(status.Settings, option));
        }
    }

    public static OptionWrite? PrepareOption(Option option, OptionSample sample, bool desired)
    {
        var opcode = OptionCommand(option);
        if (opcode == 0 || desired == sample.CurrentValue)
            return null;
        var value = desired ? (byte)1 : (byte)0;
        var right = (byte)0;
        if (opcode == 0x92)
        {
            var target = desired ? (byte)6 : (byte)0;
            value = option == Option.LeftHoldVolume ? target : sample.UnchangedHold;
            right = option == Option.RightHoldVolume ? target : sample.UnchangedHold;
        }

        return new OptionWrite(0, sample.Session, 0, sample.Flags, value, right, sample.UnchangedHold,
            opcode, GestureMask(option));
    }

    public static OptionWrite? TakeOptionSample(Device device, Option option, bool desired, OptionSample expected)
    {
        lock (Sync)
        {
            if (GetOptionSample(device, option) is not { } sample || sample.Session != expected.Session ||
                sample.CurrentValue != expected.CurrentValue || sample.UnchangedHold != expected.UnchangedHold ||
                (OptionCommand(option) == 0x90 && sample.Flags != expected.Flags) ||
                PrepareOption(option, sample, desired) is not { } write ||
                FrameProbe.LatestControlStatus is not { } status)
                return null;

            AttemptedOptionFrames[write.Opcode] = status.Frame;
            _attemptedSettingsStamp = _receiveStamp;
            return write with { Stamp = _receiveStamp, ReplyBarrier = FrameProbe.LastFrame };
        }
    }

    public static (bool? Value, bool Acknowledged, bool OtherChanged)? GetOptionReadback(
        Device device, Option option, OptionWrite write)
    {
        lock (Sync)
        {
            if (!ReferenceEquals(_receiveDevice, device) || _receiveSession != write.Session)
                return null;

            bool? value = null;
            var otherChanged = false;
            if (FrameProbe.LatestControlStatus is { } status && status.Frame > write.ReplyBarrier)
            {
                value = ReadOption(status.Settings, option);
                if (write.Mask != 0)
                    otherChanged = ((status.Flags ^ write.Flags) & ~write.Mask) != 0;
                else if (write.Opcode == 0x92)
                    otherChanged = HoldSibling(status.Settings, option) != write.UnchangedHold;
            }

            var acknowledged = write.Opcode switch
            {
                0x90 => FrameProbe.CallCommandAckFrame > write.ReplyBarrier,
                0x85 => FrameProbe.GamingModeAck is { } gaming && gaming.Frame > write.ReplyBarrier &&
                    gaming.Value == write.Value,
                0x6C => FrameProbe.PauseOnRemovalAck is { } pause && pause.Frame > write.ReplyBarrier &&
                    pause.Value == write.Value,
                0x92 => FrameProbe.HoldAck is { } hold && hold.Frame > write.ReplyBarrier &&
                    hold.Left == write.Value && hold.Right == write.Sibling,
                _ => false
            };
            return (value, acknowledged, otherChanged);
        }
    }

    public static bool HasLiveBudsOnStatus(Device device) => HasFreshStatus(device);

    public static bool HasFreshStatus(Device device)
    {
        lock (Sync)
            return ReferenceEquals(_receiveDevice, device) && FrameProbe.LatestControlStatus != null &&
                !FrameProbe.HasPartialFrame && Stopwatch.GetElapsedTime(_statusObservedAt) <= TimeSpan.FromSeconds(60);
    }

    public static (ulong Stamp, long Session, long ReplyBarrier)? TakeEqualizerCurvesRequest(Device device)
    {
        lock (Sync)
        {
            if (!ReferenceEquals(_receiveDevice, device) || _receiveStamp == 0 ||
                _receiveStamp == _attemptedSettingsStamp || FrameProbe.HasPartialFrame ||
                FrameProbe.LatestControlStatus == null)
                return null;

            _attemptedSettingsStamp = _receiveStamp;
            return (_receiveStamp, _receiveSession, FrameProbe.LastFrame);
        }
    }

    public static sbyte[]? GetEqualizerCurvesReadback(Device device, long session, long replyBarrier)
    {
        lock (Sync)
            return ReferenceEquals(_receiveDevice, device) && _receiveSession == session &&
                FrameProbe.EqualizerCurves is { } curves && curves.Frame > replyBarrier ? curves.Custom : null;
    }

    public static (int? Left, int? Right, int? Case) GetBattery(Device device)
    {
        lock (Sync)
            return ReferenceEquals(_receiveDevice, device) ? FrameProbe.GetBattery() : (null, null, null);
    }

    public static void SetMacBattery(int? battery)
    {
        lock (Sync)
        {
            if (_macBattery == battery)
                return;
            _macBattery = battery;
            ScheduleSave();
        }
    }

    public static void Record(string text)
    {
        lock (Sync)
        {
            if (Events.Count == 100)
                Events.Dequeue();
            Events.Enqueue(text);
            ScheduleSave();
        }
    }

    public static void ResetReceiveStream(Device? device = null)
    {
        lock (Sync)
        {
            if (device?.Model != Models.BudsOn)
                device = null;
            _receiveDevice = device;
            _receiveSession++;
            _receiveStamp = 0;
            _statusObservedAt = 0;
            _attemptedEqualizerStatusFrame = 0;
            _pendingEqualizerReply = null;
            _confirmedEqualizerReply = null;
            _attemptedSettingsStamp = 0;
            AttemptedOptionFrames.Clear();
            var newSettingsDevice = device != null && !ReferenceEquals(_settingsDevice, device);
            if (newSettingsDevice)
                _settingsDevice = device;
            FrameProbe.ResetStream(observeSettings: device != null, newSettingsDevice);
            ScheduleSave();
        }
    }

    public static void RecordRx(Device? device, byte[] frame, ulong stamp = 0)
    {
        lock (Sync)
        {
            if (stamp == 0 || device?.Model != Models.BudsOn || !ReferenceEquals(_receiveDevice, device))
                return;
            if (_receiveStamp != 0 && stamp != _receiveStamp + 1)
            {
                // A missing or out-of-order callback invalidates the status and any partial frame.
                _receiveSession++;
                FrameProbe.ResetStream(observeSettings: device != null, newSettingsDevice: false);
                _statusObservedAt = 0;
                _pendingEqualizerReply = null;
                _confirmedEqualizerReply = null;
                if (stamp != 0 && stamp <= _receiveStamp)
                {
                    ScheduleSave();
                    return;
                }
            }
            _receiveStamp = stamp;
            _chunks++;
            _bytes += frame.Length;
            if (FirstChunkLengths.Count < 16)
                FirstChunkLengths.Add(frame.Length);
            var previous = FrameProbe.LatestControlStatus?.Frame;
            FrameProbe.Append(frame);
            if (FrameProbe.LatestControlStatus?.Frame != previous)
                _statusObservedAt = Stopwatch.GetTimestamp();
            ScheduleSave();
        }
    }

    // Coalesce nearby native callbacks and keep an atomic copy outside the UI.
    private static void ScheduleSave()
    {
        if (_savePending || !PlatformUtils.IsOSX)
            return;

        _savePending = true;
        ReportTimer.Change(250, Timeout.Infinite);
    }

    private static void SaveReport()
    {
        lock (Sync)
        {
            _savePending = false;
            var reportPath = PlatformUtils.CombineDataPath("buds-on-connection-report.txt");
            var stagedPath = reportPath + ".tmp";
            try
            {
                File.WriteAllText(stagedPath, CopyText(), System.Text.Encoding.UTF8);
                File.Move(stagedPath, reportPath, overwrite: true);
            }
            catch (IOException)
            {
                // Copy from Settings is still available if the data directory cannot be written.
            }
            catch (UnauthorizedAccessException)
            {
                // A file permissions problem should never interrupt the Bluetooth connection.
            }
        }
    }

    public static string CopyText()
    {
        lock (Sync)
        {
            var lines = new List<string>
            {
                "Galaxy Buds On (SM-U600) Bluetooth report",
                "Scope: this app launch. Raw payloads and device addresses are excluded."
            };
            if (Events.Count == 0)
                lines.Add("No Buds On connection attempt recorded. Select Galaxy Buds On and click Connect.");
            lines.AddRange(Events);
            if (_macBattery is int battery)
                lines.Add($"Headset battery reported by macOS: {battery}%");
            lines.Add($"Received RFCOMM chunks: {_chunks} ({_bytes} bytes)");
            if (FirstChunkLengths.Count > 0)
                lines.Add($"First chunk sizes: {string.Join(", ", FirstChunkLengths)}");
            lines.AddRange(FrameProbe.SnapshotLines());
            return string.Join(Environment.NewLine, lines);
        }
    }
}
''')

replace_once(bluetooth,
    '        /* Load from configuration */\n',
    '''        if (device.Model == Models.BudsOn && alternative)
            return false;

        /* Load from configuration */
''')
replace_once(bluetooth,
    '            var uuid = AlternativeModeEnabled ? Uuids.SmepSpp.ToString() : DeviceSpec.ServiceUuid.ToString();\n',
    '''            var uuid = device.Model == Models.BudsOn
                ? Uuids.SppNew.ToString()
                : AlternativeModeEnabled ? Uuids.SmepSpp.ToString() : DeviceSpec.ServiceUuid.ToString();
''')
replace_once(bluetooth,
    '            await _backend.ConnectAsync(device.MacAddress,  uuid, _connectCancelSource.Token);\n            return true;\n',
    '''#if OSX
            if (device.Model == Models.BudsOn &&
                _backend is OSX.BluetoothService macBackend)
            {
                BudsOnDiagnostics.Record("Buds On connection requested");
                await macBackend.ConnectAsync(device.MacAddress, uuid, _connectCancelSource.Token,
                    BudsOnDiagnostics.Record,
                    (frame, stamp) => BudsOnDiagnostics.RecordRx(device, frame, stamp),
                    () => BudsOnDiagnostics.ResetReceiveStream(device));
                return true;
            }
#endif

            await _backend.ConnectAsync(device.MacAddress, uuid, _connectCancelSource.Token);
            return true;
''')
replace_once(bluetooth,
    '        catch (BluetoothException ex)\n        {\n            OnBluetoothError(ex);\n            return false;\n        }\n',
    '''        catch (BluetoothException ex)
        {
            if (device.Model == Models.BudsOn)
                BudsOnDiagnostics.Record($"Connection error: {ex.ErrorCode}");
            OnBluetoothError(ex);
            return false;
        }
''')
replace_once(bluetooth,
    '        /* Discard data if not properly registered */\n',
    '''        if (CurrentModel == Models.BudsOn)
            return;

        /* Discard data if not properly registered */
''')

settings_page = 'GalaxyBudsClient/Interface/Pages/SettingsPage.axaml'
replace_once(settings_page,
    '            <ui:FASettingsExpander Header="{ext:Translate {x:Static i18N:Keys.SettingsMultipointHeader}}"',
    '''            <ui:FASettingsExpander x:Name="BudsOnAudioPanel" Header="Galaxy Buds On"
                                   IsExpanded="True" IsVisible="False">
                <StackPanel Spacing="8">
                    <CheckBox x:Name="BudsOnReadOnlyToggle" Content="Read-only diagnostics"
                              Click="OnBudsOnReadOnlyClicked" />
                    <controls:SettingsGroup>
                        <controls:SettingsSymbolItem Content="Gaming mode" Description="Experimental"
                                                     Symbol="DeviceEq">
                            <controls:SettingsSymbolItem.Footer>
                                <Button x:Name="BudsOnGamingButton" Click="OnBudsOnGamingClicked" />
                            </controls:SettingsSymbolItem.Footer>
                        </controls:SettingsSymbolItem>
                        <controls:SettingsSymbolItem Content="Pause when one earbud is removed"
                                                     Description="Experimental" Symbol="VideoPlayPause">
                            <controls:SettingsSymbolItem.Footer>
                                <Button x:Name="BudsOnPauseButton" Click="OnBudsOnPauseClicked" />
                            </controls:SettingsSymbolItem.Footer>
                        </controls:SettingsSymbolItem>
                    </controls:SettingsGroup>
                    <TextBlock x:Name="BudsOnAudioResult" TextWrapping="Wrap" IsVisible="False" />
                    <Button x:Name="BudsOnRefreshButton" Content="Refresh Buds On status"
                            Click="OnBudsOnRefreshClicked" />
                </StackPanel>
            </ui:FASettingsExpander>

            <Button Content="Copy Buds On connection report"
                    IsVisible="{x:Static platform:PlatformUtils.IsOSX}"
                    Click="OnCopyBudsOnReportClicked" />

            <ui:FASettingsExpander Header="{ext:Translate {x:Static i18N:Keys.SettingsMultipointHeader}}"''')
settings_code = 'GalaxyBudsClient/Interface/Pages/SettingsPage.axaml.cs'
replace_once(settings_code,
    'using Avalonia.Interactivity;\n',
    'using System;\nusing System.Threading.Tasks;\nusing Avalonia.Controls;\nusing Avalonia.Input.Platform;\n'
    'using Avalonia.Interactivity;\nusing Avalonia.Threading;\nusing GalaxyBudsClient.Model.Config;\n'
    'using GalaxyBudsClient.Model.Constants;\n')
replace_once(settings_code,
    '    public async void OnApplyMultipointClicked(object? sender, RoutedEventArgs e)\n',
    '''    public async void OnCopyBudsOnReportClicked(object? sender, RoutedEventArgs e)
    {
        var clipboard = TopLevel.GetTopLevel(this)?.Clipboard;
        if (clipboard == null)
            return;

        await clipboard.SetTextAsync(BudsOnDiagnostics.CopyText());
        await new MessageBox
        {
            Title = "Buds On connection report copied",
            Description = "The report contains service IDs and connection results."
        }.ShowAsync();
    }

    public async void OnApplyMultipointClicked(object? sender, RoutedEventArgs e)
''')

replace_once(settings_code,
    '        TrayIcon.AddHandler(SettingsSwitchItem.IsCheckedChangedEvent, OnIsTrayIconEnabledChanged);\n',
    '''        TrayIcon.AddHandler(SettingsSwitchItem.IsCheckedChangedEvent, OnIsTrayIconEnabledChanged);
        if (PlatformUtils.IsOSX)
        {
            _budsOnSettingsTimer.Tick += (_, _) => RefreshBudsOnAudioControls();
            AttachedToVisualTree += (_, _) =>
            {
                RefreshBudsOnAudioControls();
                _budsOnSettingsTimer.Start();
            };
            DetachedFromVisualTree += (_, _) => _budsOnSettingsTimer.Stop();
        }
''')
replace_once(settings_code,
    '    private void OnIsTrayIconEnabledChanged(object? sender, RoutedEventArgs e)\n',
    '''    private readonly DispatcherTimer _budsOnSettingsTimer = new() { Interval = TimeSpan.FromSeconds(1) };
    private Device? _budsOnAudioDevice;
    private bool _budsOnAudioBusy;

    private void RefreshBudsOnAudioControls()
    {
        var bluetooth = BluetoothImpl.Instance;
        var device = bluetooth.Device.Current;
        BudsOnAudioPanel.IsVisible = device?.Model == Models.BudsOn;
        if (!ReferenceEquals(_budsOnAudioDevice, device))
        {
            _budsOnAudioDevice = device;
            BudsOnAudioResult.IsVisible = false;
        }

        BudsOnReadOnlyToggle.IsChecked = bluetooth.BudsOnReadOnly;
        var connected = device != null && bluetooth.IsBudsOnSettingsDevice(device);
        BudsOnRefreshButton.IsEnabled = connected && !_budsOnAudioBusy;
        RefreshBudsOnAudioButton(BudsOnGamingButton, connected ? device : null, BudsOnDiagnostics.Option.GamingMode);
        RefreshBudsOnAudioButton(BudsOnPauseButton, connected ? device : null, BudsOnDiagnostics.Option.PauseOnRemoval);
    }

    private void RefreshBudsOnAudioButton(Button button, Device? device, BudsOnDiagnostics.Option option)
    {
        var value = device != null ? BudsOnDiagnostics.GetControlValue(device, option) : null;
        var canSend = device != null && BudsOnDiagnostics.GetOptionSample(device, option) != null;
        button.Content = value switch
        {
            true => canSend ? "On · Turn off" : "On · Last reported",
            false => canSend ? "Off · Turn on" : "Off · Last reported",
            _ => "Unavailable"
        };
        button.CommandParameter = value.HasValue ? (bool?)!value.Value : null;
        button.IsEnabled = canSend && !_budsOnAudioBusy && !BluetoothImpl.Instance.BudsOnReadOnly;
    }

    private void OnBudsOnReadOnlyClicked(object? sender, RoutedEventArgs e)
    {
        BluetoothImpl.Instance.BudsOnReadOnly = BudsOnReadOnlyToggle.IsChecked == true;
        RefreshBudsOnAudioControls();
    }

    private async void OnBudsOnGamingClicked(object? sender, RoutedEventArgs e)
    {
        if (BudsOnGamingButton.CommandParameter is bool desired)
            await RunBudsOnAudioAction(device =>
                BluetoothImpl.Instance.SetBudsOnOptionAsync(device, BudsOnDiagnostics.Option.GamingMode, desired));
    }

    private async void OnBudsOnPauseClicked(object? sender, RoutedEventArgs e)
    {
        if (BudsOnPauseButton.CommandParameter is bool desired)
            await RunBudsOnAudioAction(device =>
                BluetoothImpl.Instance.SetBudsOnOptionAsync(device, BudsOnDiagnostics.Option.PauseOnRemoval, desired));
    }

    private async void OnBudsOnRefreshClicked(object? sender, RoutedEventArgs e) =>
        await RunBudsOnAudioAction(async device =>
            await BluetoothImpl.Instance.RefreshBudsOnStatusAsync(device) ?? "Earbud status refreshed.");

    private async Task RunBudsOnAudioAction(Func<Device, Task<string>> action)
    {
        var bluetooth = BluetoothImpl.Instance;
        var device = bluetooth.Device.Current;
        if (_budsOnAudioBusy || device == null || !bluetooth.IsBudsOnSettingsDevice(device))
            return;

        _budsOnAudioBusy = true;
        BudsOnAudioResult.Text = "Checking earbuds…";
        BudsOnAudioResult.IsVisible = true;
        RefreshBudsOnAudioControls();
        try
        {
            BudsOnAudioResult.Text = await action(device);
        }
        catch (Exception ex)
        {
            Serilog.Log.Warning(ex, "Buds On audio settings operation failed");
            BudsOnAudioResult.Text = "The operation was interrupted. Check the current setting.";
        }
        finally
        {
            _budsOnAudioBusy = false;
            RefreshBudsOnAudioControls();
        }
    }

    private void OnIsTrayIconEnabledChanged(object? sender, RoutedEventArgs e)
''')

native = 'GalaxyBudsClient.Platform.OSX/Native/'
replace_once(native + 'src/Bluetooth.h',
    '''typedef void (*Bt_OnChannelClosed)(void);

@interface Bluetooth''',
    '''typedef void (*Bt_OnChannelClosed)(void);
typedef void (*Bt_OnDiagnostic)(const char *line);

@interface Bluetooth''')
replace_once(native + 'src/Bluetooth.h',
    '''    bool sdpQueryDone;
''',
    '''    bool sdpQueryDone;
    IOReturn sdpQueryStatus;
''')
replace_once(native + 'src/Bluetooth.h',
    '''- (BT_CONN_RESULT)connect:(NSString *)mac uuid:(const UInt8 *)uuid;
''',
    '''- (BT_CONN_RESULT)connect:(NSString *)mac uuid:(const UInt8 *)uuid diagnostic:(Bt_OnDiagnostic)diagnostic;
''')
replace_once(native + 'include/Native.h',
    '''extern BT_CONN_RESULT bt_connect(BluetoothImpl *self, const char *mac, const unsigned char *uuid);
''',
    '''extern BT_CONN_RESULT bt_connect(BluetoothImpl *self, const char *mac, const unsigned char *uuid);
extern BT_CONN_RESULT bt_connect_diagnostic(BluetoothImpl *self, const char *mac, const unsigned char *uuid, Bt_OnDiagnostic diagnostic);
''')
replace_once(native + 'src/bridge/Native.Bluetooth.mm',
    '''BT_CONN_RESULT bt_connect(BluetoothImpl *self, const char *mac, const unsigned char *uuid) {
    NSString *nsMac = [NSString stringWithCString:mac encoding:[NSString defaultCStringEncoding]];
    BT_CONN_RESULT res = [self->client connect:nsMac uuid:uuid];
    return res;
}
''',
    '''BT_CONN_RESULT bt_connect(BluetoothImpl *self, const char *mac, const unsigned char *uuid) {
    return bt_connect_diagnostic(self, mac, uuid, nullptr);
}

BT_CONN_RESULT bt_connect_diagnostic(BluetoothImpl *self, const char *mac, const unsigned char *uuid, Bt_OnDiagnostic diagnostic) {
    NSString *nsMac = [NSString stringWithCString:mac encoding:[NSString defaultCStringEncoding]];
    return [self->client connect:nsMac uuid:uuid diagnostic:diagnostic];
}
''')
replace_once(native + 'src/Bluetooth.mm',
    '''- (BT_CONN_RESULT)connect:(NSString *)mac uuid:(const UInt8 *)uuid {
''',
    '''// Report only advertised class IDs and channels, never record names, addresses, or raw attributes.
static void ReportSdpServices(IOBluetoothDevice *device, bool fresh, Bt_OnDiagnostic report) {
    NSArray *records = [device services];
    if (records == nil) {
        report("No SDP service records available");
        return;
    }

    report([[NSString stringWithFormat:@"SDP records (%@): %lu",
             fresh ? @"refreshed" : @"cached or freshness unconfirmed",
             (unsigned long)[records count]] UTF8String]);
    for (IOBluetoothSDPServiceRecord *record in records) {
        UInt8 channel = 0;
        NSString *channelDescription = [record getRFCOMMChannelID:&channel] == kIOReturnSuccess
            ? [NSString stringWithFormat:@"RFCOMM channel %u", (unsigned int)channel]
            : @"no RFCOMM channel";
        NSArray *classes = [[record getAttributeDataElement:kBluetoothSDPAttributeIdentifierServiceClassIDList] getArrayValue];
        bool reportedClass = false;
        for (IOBluetoothSDPDataElement *element in classes) {
            IOBluetoothSDPUUID *uuid = [[element getUUIDValue] getUUIDWithLength:16];
            if ([uuid length] != 16)
                continue;
            const auto bytes = static_cast<const unsigned char *>([uuid bytes]);
            NSUUID *normalized = [[NSUUID alloc] initWithUUIDBytes:bytes];
            report([[NSString stringWithFormat:@"SDP service %@, %@", [[normalized UUIDString] lowercaseString],
                     channelDescription] UTF8String]);
            reportedClass = true;
        }
        if (!reportedClass)
            report([[NSString stringWithFormat:@"SDP record without a class UUID, %@", channelDescription] UTF8String]);
    }
}

- (BT_CONN_RESULT)connect:(NSString *)mac uuid:(const UInt8 *)uuid diagnostic:(Bt_OnDiagnostic)diagnostic {
''')
replace_once(native + 'src/Bluetooth.mm',
    '''    sdpQueryDone = NO;
    // sdp query with uuids specified silently fails since Ventura, ref https://developer.apple.com/forums/thread/722228
    status = [device performSDPQuery:self];

    if (status != kIOReturnSuccess) {
        NSLog(@"Error: %s starting SDP query.\\n", mach_error_string(status));
        // Do not fail hard, instead get a proper error message and let it be
    } else {
        // Poll until SDP query is done, to keep code and threading simple.
        i = 0;
        while (!sdpQueryDone && i++ < 15)
            //[[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.1]];
            [NSThread sleepForTimeInterval:0.1];
        if (!sdpQueryDone)
            NSLog(@"Warning: SDP query timed out.\\n");
    }
''',
    '''    NSDate *previousServicesUpdate = diagnostic ? [device getLastServicesUpdate] : nil;
    @synchronized (self) {
        sdpQueryDone = NO;
        sdpQueryStatus = kIOReturnNotReady;
    }
    if (diagnostic)
        diagnostic("Starting SDP query");

    // sdp query with uuids specified silently fails since Ventura, ref https://developer.apple.com/forums/thread/722228
    status = [device performSDPQuery:self];
    bool queryCompleted = false;
    IOReturn completionStatus = kIOReturnNotReady;
    if (status != kIOReturnSuccess) {
        NSLog(@"Error: %s starting SDP query.\\n", mach_error_string(status));
        if (diagnostic)
            diagnostic([[NSString stringWithFormat:@"SDP query could not start (0x%08X)", (unsigned int)status] UTF8String]);
    } else {
        // Poll until SDP query is done, as in the regular connection path.
        for (int attempt = 0; attempt <= 15; ++attempt) {
            @synchronized (self) {
                queryCompleted = sdpQueryDone;
                completionStatus = sdpQueryStatus;
            }
            if (queryCompleted || attempt == 15)
                break;
            [NSThread sleepForTimeInterval:0.1];
        }

        if (!queryCompleted)
            NSLog(@"Warning: SDP query timed out.\\n");
        if (diagnostic) {
            if (!queryCompleted)
                diagnostic("SDP query timed out");
            else if (completionStatus == kIOReturnSuccess)
                diagnostic("SDP query completed");
            else
                diagnostic([[NSString stringWithFormat:@"SDP query completed with error (0x%08X)",
                             (unsigned int)completionStatus] UTF8String]);
        }
    }

    if (diagnostic) {
        NSDate *currentServicesUpdate = [device getLastServicesUpdate];
        bool timestampAdvanced = currentServicesUpdate != nil &&
            (previousServicesUpdate == nil || [currentServicesUpdate compare:previousServicesUpdate] == NSOrderedDescending);
        ReportSdpServices(device, queryCompleted && completionStatus == kIOReturnSuccess && timestampAdvanced, diagnostic);
    }
''')
replace_once(native + 'src/Bluetooth.mm',
    '''    if (serviceRecord == nil) {
        NSLog(@"Error - service in selected device. ***This should never happen.***");
''',
    '''    if (serviceRecord == nil) {
        if (diagnostic)
            diagnostic("Selected management service was not found in the available SDP records");
        NSLog(@"Error - service in selected device. ***This should never happen.***");
''')
replace_once(native + 'src/Bluetooth.mm',
    '''    NSLog(@"Service selected '%@' - RFCOMM Channel ID = %u\\n", [serviceRecord getServiceName], rfcommChannelID);
''',
    '''    if (diagnostic)
        diagnostic([[NSString stringWithFormat:@"Opening management RFCOMM channel %u",
                     (unsigned int)rfcommChannelID] UTF8String]);
    NSLog(@"Service selected '%@' - RFCOMM Channel ID = %u\\n", [serviceRecord getServiceName], rfcommChannelID);
''')
replace_once(native + 'src/Bluetooth.mm',
    '''        _macAddress = [[NSString alloc] initWithString:mac];
        return BT_CONN_SUCCESS;
''',
    '''        if (diagnostic) {
            @synchronized (self) {
                if (!_diagnosticOpening || mRFCOMMChannel != tempRFCOMMChannel)
                    return BT_CONN_EOPEN;

                _macAddress = [[NSString alloc] initWithString:mac];
                NSData *earlyData = _openingDiagnosticSource == tempRFCOMMChannel
                    ? _openingDiagnosticData : nil;
                [self clearOpeningDiagnosticData];
                if (_onChannelData && earlyData.length != 0) {
                    _onChannelData(const_cast<void *>(earlyData.bytes), earlyData.length,
                                   ++_diagnosticStamp);
                }
            }
            diagnostic("Management RFCOMM channel opened");
        } else {
            _macAddress = [[NSString alloc] initWithString:mac];
        }
        return BT_CONN_SUCCESS;
''')
replace_once(native + 'src/Bluetooth.mm',
    '''    sdpQueryDone = YES;
''',
    '''    @synchronized (self) {
        sdpQueryStatus = status;
        sdpQueryDone = YES;
    }
''')

replace_once(native + 'src/Bluetooth.mm',
    '    BOOL _channelClosedSignalled;\n',
    '''    BOOL _channelClosedSignalled;
    bool _diagnosticChannel;
    bool _diagnosticOpening;
    IOBluetoothRFCOMMChannel *_openingDiagnosticSource;
    NSMutableData *_openingDiagnosticData;
''')
replace_once(native + 'src/Bluetooth.mm',
    '''    IOBluetoothRFCOMMChannel *tempRFCOMMChannel = mRFCOMMChannel;
    status = [device openRFCOMMChannelSync:&tempRFCOMMChannel withChannelID:rfcommChannelID delegate:self];
    @synchronized (self) {
        mRFCOMMChannel = tempRFCOMMChannel;
        _channelClosedSignalled = NO;
    }
''',
    '''    IOBluetoothRFCOMMChannel *tempRFCOMMChannel = mRFCOMMChannel;
    if (diagnostic) {
        @synchronized (self) {
            _diagnosticOpening = true;
            _openingDiagnosticSource = nil;
            _openingDiagnosticData = [NSMutableData data];
        }
    }
    status = [device openRFCOMMChannelSync:&tempRFCOMMChannel withChannelID:rfcommChannelID delegate:self];
    bool cancelledOpening;
    @synchronized (self) {
        cancelledOpening = diagnostic && !_diagnosticOpening;
        if (!cancelledOpening) {
            mRFCOMMChannel = tempRFCOMMChannel;
            _diagnosticChannel = diagnostic != nullptr;
            ++_diagnosticStamp;
            _channelClosedSignalled = NO;
            if (_openingDiagnosticSource && _openingDiagnosticSource != tempRFCOMMChannel) {
                _openingDiagnosticSource = nil;
                _openingDiagnosticData = [NSMutableData data];
            }
        }
    }

    if (cancelledOpening) {
        [tempRFCOMMChannel setDelegate:nil];
        [tempRFCOMMChannel closeChannel];
        return BT_CONN_EOPEN;
    }
''')
replace_once(native + 'src/Bluetooth.mm',
    '        mRFCOMMChannel = nil;\n',
    '''        mRFCOMMChannel = nil;
        _diagnosticChannel = false;
        [self clearOpeningDiagnosticData];
        ++_diagnosticStamp;
''')
replace_once(native + 'src/Bluetooth.mm',
    '        channel = mRFCOMMChannel;\n    }\n\n    if (channel != nil) {\n        if (![channel isOpen]) {',
    '''        // Check the mode while taking the native channel snapshot. A previously queued
        // write may have raced with a reconnect after the managed guard ran.
        if (_diagnosticOpening || _diagnosticChannel)
            return BT_SEND_SUCCESS;
        channel = mRFCOMMChannel;
    }

    if (channel != nil) {
        if (![channel isOpen]) {''')

home_view = 'GalaxyBudsClient/Interface/Pages/HomePage.axaml'
replace_once(home_view,
    '                    <controls:EarbudStatusUnit Margin="0, 30" />\n',
    '''                    <StackPanel>
                        <controls:EarbudStatusUnit Margin="0, 30" />
                        <TextBlock Text="{Binding BudsOnBatteryText}"
                                   IsVisible="{Binding HasBudsOnBattery}"
                                   HorizontalAlignment="Center"
                                   Margin="0,0,0,16" />
                    </StackPanel>
''')

home_vm = 'GalaxyBudsClient/Interface/ViewModels/Pages/HomePageViewModel.cs'
replace_once(home_vm,
    'using System.Threading.Tasks;\n',
    'using System.Threading;\nusing System.Threading.Tasks;\n')
replace_once(home_vm,
    'using GalaxyBudsClient.Platform;\n',
    'using GalaxyBudsClient.Platform;\nusing GalaxyBudsClient.Model.Config;\nusing GalaxyBudsClient.Model.Constants;\nusing ReactiveUI;\n')
replace_once(home_vm,
    '    private readonly DispatcherTimer _refreshTimer = new();\n',
    '''    private readonly DispatcherTimer _refreshTimer = new();
    private bool _readingBudsOnBattery;
    private string? _budsOnBatteryText;

    public bool HasBudsOnBattery => _budsOnBatteryText != null;

    public string? BudsOnBatteryText
    {
        get => _budsOnBatteryText;
        private set
        {
            this.RaiseAndSetIfChanged(ref _budsOnBatteryText, value);
            this.RaisePropertyChanged(nameof(HasBudsOnBattery));
        }
    }
''')
replace_once(home_vm,
    '            if (BluetoothImpl.Instance.IsConnected)\n                await BluetoothImpl.Instance.SendRequestAsync(MsgIds.DEBUG_GET_ALL_DATA);\n',
    '''            if (BluetoothImpl.Instance.CurrentModel == Models.BudsOn)
                await RefreshBudsOnBatteryAsync();
            else if (BluetoothImpl.Instance.IsConnected)
                await BluetoothImpl.Instance.SendRequestAsync(MsgIds.DEBUG_GET_ALL_DATA);
''')
replace_once(home_vm,
    '        SppMessageReceiver.Instance.StatusUpdate += OnStatusUpdateReceived;\n',
    '''        BluetoothImpl.Instance.Device.DeviceChanged += (_, _) => ClearBudsOnBatteryText();
        BluetoothImpl.Instance.Disconnected += (_, _) => ClearBudsOnBatteryText();
        BluetoothImpl.Instance.BluetoothError += (_, _) => ClearBudsOnBatteryText();
        SppMessageReceiver.Instance.StatusUpdate += OnStatusUpdateReceived;
''')
replace_once(home_vm,
    '            await Task.Delay(1000);\n            await BluetoothImpl.Instance.SendRequestAsync(MsgIds.DEBUG_GET_ALL_DATA);\n',
    '''            await Task.Delay(1000);
            if (BluetoothImpl.Instance.CurrentModel == Models.BudsOn)
                await RefreshBudsOnBatteryAsync();
            else
                await BluetoothImpl.Instance.SendRequestAsync(MsgIds.DEBUG_GET_ALL_DATA);
''')
replace_once(home_vm,
    '    public override void OnNavigatedTo() => _refreshTimer.Start();\n',
    '''    private void ClearBudsOnBatteryText() =>
        Dispatcher.UIThread.Post(() =>
        {
            BudsOnBatteryText = null;
            BudsOnDiagnostics.SetMacBattery(null);
        });

    private bool ShowBudsOnFrameBattery(BluetoothImpl bluetooth, Device device)
    {
        if (!bluetooth.IsConnected)
            return false;

        var (left, right, caseBattery) = BudsOnDiagnostics.GetBattery(device);
        if (left == null && right == null && caseBattery == null)
            return false;

        var levels = new System.Collections.Generic.List<string>(3);
        if (left is int level && left == right)
        {
            levels.Add($"Earbuds {level}%");
        }
        else
        {
            if (left is int leftLevel)
                levels.Add($"Left {leftLevel}%");
            if (right is int rightLevel)
                levels.Add($"Right {rightLevel}%");
        }
        if (caseBattery is int caseLevel)
            levels.Add($"Case {caseLevel}%");

        var summary = string.Join(" · ", levels);
        BudsOnBatteryText = BudsOnDiagnostics.HasLiveBudsOnStatus(device) ? summary : $"{summary} (last reported)";
        return true;
    }

    private async Task RefreshBudsOnBatteryAsync()
    {
        var bluetooth = BluetoothImpl.Instance;
        var device = bluetooth.Device.Current;
        if (!PlatformUtils.IsOSX || device?.Model != Models.BudsOn ||
            ShowBudsOnFrameBattery(bluetooth, device) || _readingBudsOnBattery ||
            string.IsNullOrWhiteSpace(device.Name))
            return;

        var name = device.Name;
        _readingBudsOnBattery = true;
        try
        {
            var battery = await BudsOnMacBattery.ReadAsync(name, CancellationToken.None);
            if (!ReferenceEquals(bluetooth.Device.Current, device) || device.Name != name)
                return;

            BudsOnDiagnostics.SetMacBattery(battery);
            if (!ShowBudsOnFrameBattery(bluetooth, device))
                BudsOnBatteryText = battery is int percentage ? $"Battery {percentage}% (macOS)" : null;
        }
        finally
        {
            _readingBudsOnBattery = false;
        }
    }

    public override void OnNavigatedTo()
    {
        _refreshTimer.Start();
        _ = RefreshBudsOnBatteryAsync();
    }
''')

touchpad_view = 'GalaxyBudsClient/Interface/Pages/TouchpadPage.axaml'
replace_once(touchpad_view,
    '                <ext:RequiresConnectedDeviceBehavior />\n'
    '            </Interaction.Behaviors>\n',
    '''                <ext:RequiresConnectedDeviceBehavior />
            </Interaction.Behaviors>

            <StackPanel IsVisible="{Binding IsBudsOnTouchpad}" Spacing="8">
                <controls:SettingsGroup IsEnabled="{Binding !IsBudsOnTouchpadBusy}">
                    <controls:SettingsSymbolItem
                        Content="Media controls"
                        Description="{Binding BudsOnMedia.Description}"
                        Symbol="VideoPlayPause">
                        <controls:SettingsSymbolItem.Footer>
                            <Button Content="{Binding BudsOnMedia.Action}"
                                    IsEnabled="{Binding BudsOnMedia.CanChange}"
                                    CommandParameter="{Binding BudsOnMedia.DesiredValue}"
                                    AutomationProperties.Name="Change Media controls"
                                    Click="OnBudsOnMediaClicked" />
                        </controls:SettingsSymbolItem.Footer>
                    </controls:SettingsSymbolItem>
                    <controls:SettingsSymbolItem
                        Content="Answer call or end call"
                        Description="{Binding BudsOnAnswerOrEnd.Description}"
                        Symbol="CallInbound">
                        <controls:SettingsSymbolItem.Footer>
                            <Button Content="{Binding BudsOnAnswerOrEnd.Action}"
                                    IsEnabled="{Binding BudsOnAnswerOrEnd.CanChange}"
                                    CommandParameter="{Binding BudsOnAnswerOrEnd.DesiredValue}"
                                    AutomationProperties.Name="Change Answer call or end call"
                                    Click="OnBudsOnAnswerOrEndClicked" />
                        </controls:SettingsSymbolItem.Footer>
                    </controls:SettingsSymbolItem>
                    <controls:SettingsSymbolItem
                        Content="Decline call"
                        Description="{Binding BudsOnDecline.Description}"
                        Symbol="CallProhibited">
                        <controls:SettingsSymbolItem.Footer>
                            <Button Content="{Binding BudsOnDecline.Action}"
                                    IsEnabled="{Binding BudsOnDecline.CanChange}"
                                    CommandParameter="{Binding BudsOnDecline.DesiredValue}"
                                    AutomationProperties.Name="Change Decline call"
                                    Click="OnBudsOnDeclineClicked" />
                        </controls:SettingsSymbolItem.Footer>
                    </controls:SettingsSymbolItem>
                    <controls:SettingsSymbolItem
                        Content="Volume on left hold"
                        Description="{Binding BudsOnLeftHoldVolume.Description}"
                        Symbol="ArrowStepInLeft">
                        <controls:SettingsSymbolItem.Footer>
                            <Button Content="{Binding BudsOnLeftHoldVolume.Action}"
                                    IsEnabled="{Binding BudsOnLeftHoldVolume.CanChange}"
                                    CommandParameter="{Binding BudsOnLeftHoldVolume.DesiredValue}"
                                    AutomationProperties.Name="Change Volume on left hold"
                                    Click="OnBudsOnLeftHoldVolumeClicked" />
                        </controls:SettingsSymbolItem.Footer>
                    </controls:SettingsSymbolItem>
                    <controls:SettingsSymbolItem
                        Content="Volume on right hold"
                        Description="{Binding BudsOnRightHoldVolume.Description}"
                        Symbol="ArrowStepInRight">
                        <controls:SettingsSymbolItem.Footer>
                            <Button Content="{Binding BudsOnRightHoldVolume.Action}"
                                    IsEnabled="{Binding BudsOnRightHoldVolume.CanChange}"
                                    CommandParameter="{Binding BudsOnRightHoldVolume.DesiredValue}"
                                    AutomationProperties.Name="Change Volume on right hold"
                                    Click="OnBudsOnRightHoldVolumeClicked" />
                        </controls:SettingsSymbolItem.Footer>
                    </controls:SettingsSymbolItem>
                </controls:SettingsGroup>
                <Button Content="Refresh status"
                        IsEnabled="{Binding CanRefreshBudsOnTouchpad}"
                        Click="OnRefreshBudsOnTouchpadClicked" />
                <TextBlock Text="{Binding BudsOnTouchpadResult}"
                           IsVisible="{Binding HasBudsOnTouchpadResult}"
                           TextWrapping="Wrap" />
            </StackPanel>
''')
replace_once(touchpad_view,
    '            <controls:SettingsGroup>\n'
    '                <Interaction.Behaviors>\n'
    '                    <ext:RequiresFeatureBehavior Feature="TouchpadLock" />',
    '            <controls:SettingsGroup IsVisible="{Binding !IsBudsOnTouchpad}">\n'
    '                <Interaction.Behaviors>\n'
    '                    <ext:RequiresFeatureBehavior Feature="TouchpadLock" />')
replace_once(touchpad_view,
    '            <controls:SettingsGroup>\n'
    '                <controls:SettingsGroup.IsEnabled>',
    '            <controls:SettingsGroup IsVisible="{Binding !IsBudsOnTouchpad}">\n'
    '                <controls:SettingsGroup.IsEnabled>')
replace_once(touchpad_view,
    '            <controls:SettingsGroup IsEnabled="{Binding !IsTouchpadLocked}">',
    '            <controls:SettingsGroup IsVisible="{Binding !IsBudsOnTouchpad}"\n'
    '                                    IsEnabled="{Binding !IsTouchpadLocked}">')

touchpad_vm = 'GalaxyBudsClient/Interface/ViewModels/Pages/TouchpadPageViewModel.cs'
replace_once(touchpad_vm,
    '    public override Control CreateView() => new TouchpadPage { DataContext = this };\n',
    '''    public sealed record BudsOnTouchSetting(bool? Enabled, bool Experimental = false,
        bool ReadOnly = false, bool CanSend = false)
    {
        public string Description => (Enabled switch
        {
            true => "On",
            false => "Off",
            null => "Unavailable"
        }) + (Experimental ? " · Experimental" : "") +
            (Enabled.HasValue && !CanSend ? " · Last reported" : "");

        public bool CanChange => Enabled.HasValue && CanSend && !ReadOnly;
        public bool DesiredValue => Enabled == false;
        public string Action => Enabled switch
        {
            true => "Turn off",
            false => "Turn on",
            null => "Change"
        };
    }

    private readonly DispatcherTimer _budsOnTouchpadTimer = new() { Interval = TimeSpan.FromSeconds(1) };
    private Device? _budsOnTouchpadDevice;
    private bool _isBudsOnTouchpad;
    private bool _canRefreshBudsOnTouchpad;
    private bool _isBudsOnTouchpadBusy;
    private string? _budsOnTouchpadResult;
    private BudsOnTouchSetting _budsOnMedia = new(null);
    private BudsOnTouchSetting _budsOnAnswerOrEnd = new(null);
    private BudsOnTouchSetting _budsOnDecline = new(null);
    private BudsOnTouchSetting _budsOnLeftHoldVolume = new(null, Experimental: true);
    private BudsOnTouchSetting _budsOnRightHoldVolume = new(null, Experimental: true);

    public bool IsBudsOnTouchpad => _isBudsOnTouchpad;
    public bool CanRefreshBudsOnTouchpad => _canRefreshBudsOnTouchpad && !IsBudsOnTouchpadBusy;
    public BudsOnTouchSetting BudsOnMedia => _budsOnMedia;
    public BudsOnTouchSetting BudsOnAnswerOrEnd => _budsOnAnswerOrEnd;
    public BudsOnTouchSetting BudsOnDecline => _budsOnDecline;
    public BudsOnTouchSetting BudsOnLeftHoldVolume => _budsOnLeftHoldVolume;
    public BudsOnTouchSetting BudsOnRightHoldVolume => _budsOnRightHoldVolume;
    public bool HasBudsOnTouchpadResult => !string.IsNullOrEmpty(BudsOnTouchpadResult);

    public bool IsBudsOnTouchpadBusy
    {
        get => _isBudsOnTouchpadBusy;
        internal set
        {
            this.RaiseAndSetIfChanged(ref _isBudsOnTouchpadBusy, value);
            this.RaisePropertyChanged(nameof(CanRefreshBudsOnTouchpad));
        }
    }

    public string? BudsOnTouchpadResult
    {
        get => _budsOnTouchpadResult;
        internal set
        {
            this.RaiseAndSetIfChanged(ref _budsOnTouchpadResult, value);
            this.RaisePropertyChanged(nameof(HasBudsOnTouchpadResult));
        }
    }

    public override Control CreateView() => new TouchpadPage { DataContext = this };
''')
replace_once(touchpad_vm,
    '    public TouchpadPageViewModel()\n    {\n',
    '    public TouchpadPageViewModel()\n    {\n'
    '        _budsOnTouchpadTimer.Tick += (_, _) => RefreshBudsOnTouchpad();\n')
replace_once(touchpad_vm,
    '    public override void OnNavigatedTo() => UpdateEditStates();\n',
    '''    public override void OnNavigatedTo()
    {
        UpdateEditStates();
        RefreshBudsOnTouchpad();
        if (PlatformUtils.IsOSX)
            _budsOnTouchpadTimer.Start();
    }

    public override void OnNavigatedFrom() => _budsOnTouchpadTimer.Stop();

    internal void RefreshBudsOnTouchpad()
    {
        var bluetooth = BluetoothImpl.Instance;
        var device = bluetooth.Device.Current;
        if (!ReferenceEquals(_budsOnTouchpadDevice, device))
        {
            _budsOnTouchpadDevice = device;
            BudsOnTouchpadResult = null;
        }

        this.RaiseAndSetIfChanged(ref _isBudsOnTouchpad, device?.Model == Models.BudsOn, nameof(IsBudsOnTouchpad));
        var canRead = device != null && bluetooth.IsBudsOnSettingsDevice(device);
        this.RaiseAndSetIfChanged(ref _canRefreshBudsOnTouchpad, canRead, nameof(CanRefreshBudsOnTouchpad));

        BudsOnTouchSetting Read(BudsOnDiagnostics.Option option, bool experimental = false) =>
            new(canRead ? BudsOnDiagnostics.GetControlValue(device!, option) : null, experimental,
                bluetooth.BudsOnReadOnly, canRead && BudsOnDiagnostics.GetOptionSample(device!, option) != null);

        this.RaiseAndSetIfChanged(ref _budsOnMedia, Read(BudsOnDiagnostics.Option.Media), nameof(BudsOnMedia));
        this.RaiseAndSetIfChanged(ref _budsOnAnswerOrEnd, Read(BudsOnDiagnostics.Option.AnswerOrEnd), nameof(BudsOnAnswerOrEnd));
        this.RaiseAndSetIfChanged(ref _budsOnDecline, Read(BudsOnDiagnostics.Option.Decline), nameof(BudsOnDecline));
        this.RaiseAndSetIfChanged(ref _budsOnLeftHoldVolume,
            Read(BudsOnDiagnostics.Option.LeftHoldVolume, experimental: true), nameof(BudsOnLeftHoldVolume));
        this.RaiseAndSetIfChanged(ref _budsOnRightHoldVolume,
            Read(BudsOnDiagnostics.Option.RightHoldVolume, experimental: true), nameof(BudsOnRightHoldVolume));
    }
''')

write_once(native + 'src/BudsOnCallControl.h', '''#pragma once

#include <array>
#include <cstdint>
#include <optional>

template <std::size_t Size>
inline void FinishBudsOnFrame(std::array<uint8_t, Size> &frame, std::size_t length = Size) {
    uint16_t crc = 0;
    for (std::size_t i = 3; i < length - 3; ++i) {
        crc ^= static_cast<uint16_t>(frame[i]) << 8;
        for (int bit = 0; bit < 8; ++bit)
            crc = static_cast<uint16_t>((crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0));
    }
    frame[length - 3] = static_cast<uint8_t>(crc);
    frame[length - 2] = static_cast<uint8_t>(crc >> 8);
    frame[length - 1] = 0xdd;
}

inline bool IsBudsOnCallTestAllowed(uint8_t flags, uint8_t mask, uint8_t enabled) {
    // Samsung's Media controls switches bits 1, 2, 3, and 6 together.
    // The combined test may turn those flags and Decline (bit 5) off once.
    if (mask == 0x4e)
        return (enabled == 0 && (flags & mask) == mask) || (enabled == 1 && (flags & mask) == 0);
    if (mask != 0x10 && mask != 0x20)
        return false;

    return enabled <= 1 && (((flags & mask) != 0) != (enabled != 0));
}

inline std::array<uint8_t, 17> MakeBudsOnCallFrame(uint8_t flags) {
    // The SM-U600 Samsung app writes its full touch control vector. The caller
    // changes the selected control in an otherwise unmodified status sample.
    constexpr std::array<uint8_t, 8> order{7, 3, 2, 1, 0, 4, 5, 6};
    std::array<uint8_t, 17> frame{0xfd, 0x0d, 0x00, 0x90};
    for (std::size_t i = 0; i < order.size(); ++i)
        frame[4 + i] = (flags >> order[i]) & 1;
    frame[12] = 1;
    frame[13] = 1;

    FinishBudsOnFrame(frame);
    return frame;
}

inline std::array<uint8_t, 8> MakeBudsOnEqualizerFrame(uint8_t preset) {
    std::array<uint8_t, 8> frame{0xfd, 0x04, 0x00, 0x86, preset};
    FinishBudsOnFrame(frame);
    return frame;
}

struct BudsOnOptionFrame {
    std::array<uint8_t, 11> bytes;
    uint16_t length;
};

inline std::optional<BudsOnOptionFrame> MakeBudsOnOptionFrame(uint8_t control, uint8_t value, uint8_t sibling) {
    BudsOnOptionFrame frame{{0xfd, 0, 0, control}, 0};
    switch (control) {
        case 0x85: // Gaming mode.
        case 0x6c: // Pause when one earbud is removed.
            if (value > 1 || sibling != 0)
                return std::nullopt;
            frame.bytes[4] = value;
            frame.length = 8;
            break;
        case 0x92: // Set only verified hold actions, preserving both sides.
            if ((value != 0 && value != 6) || (sibling != 0 && sibling != 6))
                return std::nullopt;
            frame.bytes[4] = value;
            frame.bytes[5] = sibling;
            frame.length = 11;
            break;
        case 0x69: // Read equalizer curves.
            if (value != 0 || sibling != 0)
                return std::nullopt;
            frame.length = 7;
            break;
        default:
            return std::nullopt;
    }

    frame.bytes[1] = static_cast<uint8_t>(frame.length - 4);
    FinishBudsOnFrame(frame.bytes, frame.length);
    return frame;
}
''')

replace_once(native + 'src/Bluetooth.h',
    'typedef void (*Bt_OnChannelData)(void *data, unsigned long size);\n',
    'typedef void (*Bt_OnChannelData)(void *data, unsigned long size, uint64_t diagnosticStamp);\n')
replace_once(native + 'src/Bluetooth.h',
    '- (BT_SEND_RESULT)sendData:(char *)buffer length:(UInt32)length;\n',
    '''- (BT_SEND_RESULT)sendData:(char *)buffer length:(UInt32)length;
- (BT_SEND_RESULT)sendBudsOnCallTest:(uint64_t)stamp flags:(UInt8)flags mask:(UInt8)mask enabled:(UInt8)enabled;
- (BT_SEND_RESULT)sendBudsOnEqualizerTest:(uint64_t)stamp preset:(UInt8)preset;
- (BT_SEND_RESULT)sendBudsOnOption:(uint64_t)stamp control:(UInt8)control value:(UInt8)value sibling:(UInt8)sibling;
''')
replace_once(native + 'include/Native.h',
    'extern BT_SEND_RESULT bt_send(BluetoothImpl *self, void *data, unsigned int length);\n',
    '''extern BT_SEND_RESULT bt_send(BluetoothImpl *self, void *data, unsigned int length);
extern BT_SEND_RESULT bt_send_budson_call_test(BluetoothImpl *self, uint64_t stamp, uint8_t flags, uint8_t mask, uint8_t enabled);
extern BT_SEND_RESULT bt_send_budson_eq_test(BluetoothImpl *self, uint64_t stamp, uint8_t preset);
extern BT_SEND_RESULT bt_send_budson_option(BluetoothImpl *self, uint64_t stamp, uint8_t control, uint8_t value, uint8_t sibling);
''')
replace_once(native + 'src/bridge/Native.Bluetooth.mm',
    '''BT_SEND_RESULT bt_send(BluetoothImpl *self, void *data, unsigned int length) {
    return [self->client sendData:static_cast<char *>(data) length:length];
}
''',
    '''BT_SEND_RESULT bt_send(BluetoothImpl *self, void *data, unsigned int length) {
    return [self->client sendData:static_cast<char *>(data) length:length];
}

BT_SEND_RESULT bt_send_budson_call_test(BluetoothImpl *self, uint64_t stamp, uint8_t flags, uint8_t mask, uint8_t enabled) {
    return [self->client sendBudsOnCallTest:stamp flags:flags mask:mask enabled:enabled];
}

BT_SEND_RESULT bt_send_budson_eq_test(BluetoothImpl *self, uint64_t stamp, uint8_t preset) {
    return [self->client sendBudsOnEqualizerTest:stamp preset:preset];
}

BT_SEND_RESULT bt_send_budson_option(BluetoothImpl *self, uint64_t stamp, uint8_t control, uint8_t value, uint8_t sibling) {
    return [self->client sendBudsOnOption:stamp control:control value:value sibling:sibling];
}
''')
replace_once(native + 'src/Bluetooth.mm',
    '#import "NativeStringUtils.h"\n',
    '#import "NativeStringUtils.h"\n#include "BudsOnCallControl.h"\n')
replace_once(native + 'src/Bluetooth.mm',
    '    NSString *_macAddress;\n',
    '''    NSString *_macAddress;
    uint64_t _diagnosticStamp;
    uint64_t _lastTestStamp;
''')
replace_once(native + 'src/Bluetooth.mm',
    '''- (void)rfcommChannelData:(IOBluetoothRFCOMMChannel *)rfcommChannel data:(void *)dataPointer length:(size_t)dataLength {
    if (_onChannelData) {
        _onChannelData(dataPointer, dataLength);
    }
}
''',
    '''// Call only while holding the channel lock.
- (void)clearOpeningDiagnosticData {
    _diagnosticOpening = false;
    _openingDiagnosticSource = nil;
    _openingDiagnosticData = nil;
}

- (void)rfcommChannelData:(IOBluetoothRFCOMMChannel *)rfcommChannel data:(void *)dataPointer length:(size_t)dataLength {
    @synchronized (self) {
        if (_diagnosticOpening) {
            // Apple's synchronous open can deliver data before returning its channel.
            // Keep one candidate, then deliver its data only if the returned channel matches.
            constexpr NSUInteger maxOpeningBytes = 32 * 1024;
            if (!rfcommChannel || !dataPointer || dataLength == 0 ||
                (mRFCOMMChannel && rfcommChannel != mRFCOMMChannel))
                return;
            if (!_openingDiagnosticSource)
                _openingDiagnosticSource = rfcommChannel;
            if (rfcommChannel != _openingDiagnosticSource || !_openingDiagnosticData)
                return;
            if (dataLength > maxOpeningBytes - _openingDiagnosticData.length) {
                _openingDiagnosticData = nil;
                return;
            }
            [_openingDiagnosticData appendBytes:dataPointer length:dataLength];
            return;
        }

        if (_diagnosticChannel) {
            // Serialize diagnostic callbacks with the opening batch so stamps reach managed code
            // in receive order. The diagnostic callback only copies and records received data.
            if (rfcommChannel == mRFCOMMChannel && _onChannelData)
                _onChannelData(dataPointer, dataLength, ++_diagnosticStamp);
            return;
        }
    }
    if (_onChannelData)
        _onChannelData(dataPointer, dataLength, 0);
}
''')
replace_once(native + 'src/Bluetooth.mm',
    '- (void)setOnChannelData:(Bt_OnChannelData)callback {\n',
    '''- (BT_SEND_RESULT)sendBudsOnTestFrame:(uint64_t)stamp data:(void *)data length:(UInt16)length {
    IOBluetoothRFCOMMChannel *channel;
    @synchronized (self) {
        if (!_diagnosticChannel || _diagnosticOpening || _channelClosedSignalled || stamp == 0 ||
            stamp != _diagnosticStamp || stamp == _lastTestStamp || mRFCOMMChannel == nil)
            return BT_SEND_ENULL;

        _lastTestStamp = stamp;
        channel = mRFCOMMChannel;
    }

    // The same retained channel either accepts the complete frame or fails.
    // A close or reconnect cannot redirect a queued test to another channel.
    if (![channel isOpen] || [channel getMTU] < length)
        return BT_SEND_ENULL;

    const auto result = [channel writeSync:data length:length];
    return result == kIOReturnSuccess ? BT_SEND_SUCCESS : BT_SEND_EUNKNOWN;
}

- (BT_SEND_RESULT)sendBudsOnCallTest:(uint64_t)stamp flags:(UInt8)flags mask:(UInt8)mask enabled:(UInt8)enabled {
    if (!IsBudsOnCallTestAllowed(flags, mask, enabled))
        return BT_SEND_ENULL;

    auto frame = MakeBudsOnCallFrame(flags ^ mask);
    return [self sendBudsOnTestFrame:stamp data:frame.data() length:static_cast<UInt16>(frame.size())];
}

- (BT_SEND_RESULT)sendBudsOnEqualizerTest:(uint64_t)stamp preset:(UInt8)preset {
    if (preset > 5)
        return BT_SEND_ENULL;

    auto frame = MakeBudsOnEqualizerFrame(preset);
    return [self sendBudsOnTestFrame:stamp data:frame.data() length:static_cast<UInt16>(frame.size())];
}

- (BT_SEND_RESULT)sendBudsOnOption:(uint64_t)stamp control:(UInt8)control value:(UInt8)value sibling:(UInt8)sibling {
    auto frame = MakeBudsOnOptionFrame(control, value, sibling);
    if (!frame)
        return BT_SEND_ENULL;

    return [self sendBudsOnTestFrame:stamp data:frame->bytes.data() length:frame->length];
}

- (void)setOnChannelData:(Bt_OnChannelData)callback {
''')
replace_once('GalaxyBudsClient.Platform.OSX/Unmanaged.cs',
    '    internal delegate void Bt_OnChannelData(IntPtr data, ulong size);\n',
    '    internal delegate void Bt_OnChannelData(IntPtr data, ulong size, ulong diagnosticStamp);\n')
replace_once('GalaxyBudsClient.Platform.OSX/Unmanaged.cs',
    '    internal static extern unsafe BT_SEND_RESULT bt_send(BluetoothImpl* self, byte* data, uint length);\n',
    '''    internal static extern unsafe BT_SEND_RESULT bt_send(BluetoothImpl* self, byte* data, uint length);

    [DllImport(DSO.Name, CallingConvention = CallingConvention.Cdecl)]
    internal static extern unsafe BT_SEND_RESULT bt_send_budson_call_test(
        BluetoothImpl* self, ulong stamp, byte flags, byte mask, byte enabled);

    [DllImport(DSO.Name, CallingConvention = CallingConvention.Cdecl)]
    internal static extern unsafe BT_SEND_RESULT bt_send_budson_eq_test(
        BluetoothImpl* self, ulong stamp, byte preset);

    [DllImport(DSO.Name, CallingConvention = CallingConvention.Cdecl)]
    internal static extern unsafe BT_SEND_RESULT bt_send_budson_option(
        BluetoothImpl* self, ulong stamp, byte control, byte value, byte sibling);
''')
replace_once(mac_bluetooth,
    '        private void OnChannelData(IntPtr data, ulong size)\n',
    '        private void OnChannelData(IntPtr data, ulong size, ulong stamp)\n')
replace_once(mac_bluetooth,
    '        #region Transmission\n',
    '''        #region Transmission
        public bool TrySendBudsOnCallTest(string expectedMac, byte flags, byte mask, bool enabled,
            Func<ulong?> getCurrentStamp)
        {
            unsafe
            {
                return TrySendBudsOnTest(expectedMac, getCurrentStamp, stamp =>
                    Bluetooth.bt_send_budson_call_test(_nativePtr, stamp, flags, mask, enabled ? (byte)1 : (byte)0)
                    == BT_SEND_RESULT.BT_SEND_SUCCESS);
            }
        }

        public bool TrySendBudsOnEqualizerTest(string expectedMac, byte preset, Func<ulong?> getCurrentStamp)
        {
            if (preset > 5)
                return false;

            unsafe
            {
                return TrySendBudsOnTest(expectedMac, getCurrentStamp, stamp =>
                    Bluetooth.bt_send_budson_eq_test(_nativePtr, stamp, preset) == BT_SEND_RESULT.BT_SEND_SUCCESS);
            }
        }

        public bool TrySendBudsOnOption(string expectedMac, byte control, byte value, byte sibling,
            Func<ulong?> getCurrentStamp)
        {
            var valid = control switch
            {
                0x85 or 0x6c => value <= 1 && sibling == 0,
                0x92 => (value is 0 or 6) && (sibling is 0 or 6),
                0x69 => value == 0 && sibling == 0,
                _ => false
            };
            if (!valid)
                return false;

            unsafe
            {
                return TrySendBudsOnTest(expectedMac, getCurrentStamp, stamp =>
                    Bluetooth.bt_send_budson_option(_nativePtr, stamp, control, value, sibling)
                    == BT_SEND_RESULT.BT_SEND_SUCCESS);
            }
        }

        private bool TrySendBudsOnTest(string expectedMac, Func<ulong?> getCurrentStamp, Func<ulong, bool> send)
        {
            if (!ConnSemaphore.Wait(0))
                return false;

            try
            {
                if (!SendSemaphore.Wait(0))
                    return false;

                try
                {
                    if (_currentDiagnosticRx == null ||
                        !string.Equals(_currentMac, expectedMac, StringComparison.OrdinalIgnoreCase) ||
                        getCurrentStamp() is not { } stamp)
                        return false;

                    return send(stamp);
                }
                finally
                {
                    SendSemaphore.Release();
                }
            }
            finally
            {
                ConnSemaphore.Release();
            }
        }

''')

replace_once(bluetooth,
    '    public async Task SendAltAsync(SppAlternativeMessage msg)\n    {\n'
    '        // Block SMEP/MDE property writes',
    '''    internal bool IsBudsOnSettingsDevice(Device device) =>
        PlatformUtils.IsOSX && !AlternativeModeEnabled && IsConnected &&
        device.Model == Models.BudsOn && ReferenceEquals(Device.Current, device);

#if OSX
    private int _budsOnOperationInProgress;
#endif
    private int _budsOnReadOnly;

    internal bool BudsOnReadOnly
    {
        get => Volatile.Read(ref _budsOnReadOnly) != 0;
        set => Volatile.Write(ref _budsOnReadOnly, value ? 1 : 0);
    }

    internal async Task<string?> RefreshBudsOnStatusAsync(Device device)
    {
#if OSX
        if (_backend is OSX.BluetoothService && IsBudsOnSettingsDevice(device))
        {
            if (Interlocked.CompareExchange(ref _budsOnOperationInProgress, 1, 0) != 0)
                return "A Buds On operation is in progress.";

            try
            {
                if (await RefreshBudsOnStatusCoreAsync(device))
                    return null;
                if (IsBudsOnSettingsDevice(device))
                    return "The earbuds connected. A fresh status is still pending.";
            }
            finally
            {
                Volatile.Write(ref _budsOnOperationInProgress, 0);
            }
        }
#endif
        return "Connect your Buds On in the Mac app and try refreshing their status.";
    }

    internal async Task<string> SetBudsOnOptionAsync(Device device, BudsOnDiagnostics.Option option, bool desired)
    {
        if (BudsOnReadOnly)
            return "Buds On is in read-only mode.";

#if OSX
        if (_backend is OSX.BluetoothService backend && IsBudsOnSettingsDevice(device))
        {
            if (Interlocked.CompareExchange(ref _budsOnOperationInProgress, 1, 0) != 0)
                return "A Buds On operation is in progress.";

            try
            {
                if (BudsOnDiagnostics.GetOptionSample(device, option) is not { } expected)
                    return "This setting needs a fresh reading. Use Refresh status.";
                if (expected.CurrentValue == desired)
                    return "The earbuds already report the selected setting.";
                if (BudsOnDiagnostics.PrepareOption(option, expected, desired) is not { } outbound)
                    return "This setting is unavailable for the current earbud state.";

                var expectedMac = device.MacAddress;
                BudsOnDiagnostics.OptionWrite? sentWrite = null;
                ulong? GetStamp()
                {
                    if (BudsOnReadOnly || !IsBudsOnSettingsDevice(device))
                        return null;

                    sentWrite = BudsOnDiagnostics.TakeOptionSample(device, option, desired, expected);
                    return sentWrite?.Stamp;
                }

                var sent = await Task.Run(() => outbound.Mask != 0
                    ? backend.TrySendBudsOnCallTest(expectedMac, outbound.Flags, outbound.Mask, desired, GetStamp)
                    : backend.TrySendBudsOnOption(expectedMac, outbound.Opcode, outbound.Value, outbound.Sibling, GetStamp));
                if (!sent || sentWrite is not { } write)
                    return "The setting could not be sent. Refresh status before trying again.";

                BudsOnDiagnostics.Record($"Buds On setting sent ({option} {(desired ? "On" : "Off")})");
                var result = await WaitForBudsOnOptionAsync(device, option, desired, write);
                BudsOnDiagnostics.Record($"{option}: {result}");
                return result;
            }
            finally
            {
                Volatile.Write(ref _budsOnOperationInProgress, 0);
            }
        }
#endif
        return "Connect your Buds On in the Mac app to change this setting.";
    }

    internal async Task<string> SetBudsOnEqualizerAsync(Device device, BudsOnDiagnostics.EqualizerSample expected,
        byte targetPreset)
    {
        if (BudsOnReadOnly)
            return "Buds On is in read-only mode.";

#if OSX
        if (_backend is OSX.BluetoothService backend && IsBudsOnSettingsDevice(device) &&
            expected.Preset <= 5 && targetPreset <= 5 && targetPreset != expected.Preset)
        {
            if (Interlocked.CompareExchange(ref _budsOnOperationInProgress, 1, 0) != 0)
                return "A Buds On operation is in progress.";

            try
            {
                var expectedMac = device.MacAddress;
                long replyBarrier = 0;
                var sent = await Task.Run(() => backend.TrySendBudsOnEqualizerTest(expectedMac, targetPreset, () =>
                {
                    if (BudsOnReadOnly || !IsBudsOnSettingsDevice(device) ||
                        BudsOnDiagnostics.TakeEqualizerTestSample(device, expected, targetPreset) is not { } approved)
                        return null;

                    replyBarrier = approved.ReplyBarrier;
                    return approved.Stamp;
                }));
                if (!sent)
                    return "The preset could not be sent. Refresh status and select the preset again.";

                var name = BudsOnDiagnostics.GetEqualizerPresetName(targetPreset);
                BudsOnDiagnostics.Record($"Buds On EQ preset sent ({name})");
                for (var i = 0; i < 10; i++)
                {
                    await Task.Delay(200);
                    if (!IsBudsOnSettingsDevice(device) ||
                        BudsOnDiagnostics.GetEqualizerTestReadback(device, expected.Session, replyBarrier) is not { } readback)
                        return "The connection changed. Check the EQ preset after reconnecting.";

                    if (readback.Preset == targetPreset)
                    {
                        BudsOnDiagnostics.Record($"Buds On EQ preset verified ({name})");
                        return $"The earbuds report {name}.";
                    }
                    if (BudsOnDiagnostics.ConfirmEqualizerReply(device, expected.Session, replyBarrier, targetPreset))
                    {
                        BudsOnDiagnostics.Record($"Buds On EQ preset confirmed by device reply ({name})");
                        return $"The earbuds confirmed {name}.";
                    }
                }

                BudsOnDiagnostics.Record("Buds On EQ change awaiting readback");
                return "The preset change was sent. Use Refresh status or check the preset on your Galaxy.";
            }
            finally
            {
                Volatile.Write(ref _budsOnOperationInProgress, 0);
            }
        }
#endif
        return "Connect your Buds On with a standard preset selected to change EQ.";
    }

    internal async Task<string> ReadBudsOnEqualizerCurvesAsync(Device device)
    {
#if OSX
        if (_backend is OSX.BluetoothService backend && IsBudsOnSettingsDevice(device))
        {
            if (Interlocked.CompareExchange(ref _budsOnOperationInProgress, 1, 0) != 0)
                return "A Buds On operation is in progress.";

            try
            {
                var expectedMac = device.MacAddress;
                (ulong Stamp, long Session, long ReplyBarrier)? request = null;
                var sent = await Task.Run(() => backend.TrySendBudsOnOption(expectedMac, 0x69, 0, 0, () =>
                {
                    if (!IsBudsOnSettingsDevice(device))
                        return null;

                    request = BudsOnDiagnostics.TakeEqualizerCurvesRequest(device);
                    return request?.Stamp;
                }));
                if (!sent || request is not { } sentRequest)
                    return "The curve request could not be sent. Refresh status and try again.";

                for (var i = 0; i < 16; i++)
                {
                    await Task.Delay(200);
                    if (!IsBudsOnSettingsDevice(device))
                        break;
                    if (BudsOnDiagnostics.GetEqualizerCurvesReadback(device, sentRequest.Session,
                            sentRequest.ReplyBarrier) is { } custom)
                    {
                        BudsOnDiagnostics.Record("Buds On returned a valid nine-band Custom EQ curve");
                        string[] frequencies = ["63 Hz", "125 Hz", "250 Hz", "500 Hz", "1 kHz", "2 kHz",
                            "4 kHz", "8 kHz", "16 kHz"];
                        return string.Join(Environment.NewLine,
                            frequencies.Select((frequency, index) => $"{frequency}   {custom[index]:+0;-0;0}"));
                    }
                }

                BudsOnDiagnostics.Record("Buds On Custom EQ curve request had no validated reply");
                return "The earbuds did not return a validated nine-band curve.";
            }
            finally
            {
                Volatile.Write(ref _budsOnOperationInProgress, 0);
            }
        }
#endif
        return "Connect your Buds On to read the stored Custom EQ curve.";
    }

#if OSX
    private async Task<string> WaitForBudsOnOptionAsync(Device device, BudsOnDiagnostics.Option option,
        bool desired, BudsOnDiagnostics.OptionWrite write)
    {
        var acknowledged = false;
        const string state = "The earbuds report the selected value.";
        const string changed = "Another setting changed during the update. Review the earbuds’ current settings.";
        for (var i = 0; i < 10; i++)
        {
            await Task.Delay(200);
            if (!IsBudsOnSettingsDevice(device) ||
                BudsOnDiagnostics.GetOptionReadback(device, option, write) is not { } readback)
                return "The connection changed. Check the setting after reconnecting.";

            acknowledged |= readback.Acknowledged;
            if (readback.OtherChanged)
                return changed;
            if (readback.Value == desired)
                return state;
        }

        return acknowledged
            ? "The earbuds acknowledged the command. Use Refresh status to verify the value."
            : "The setting was sent. Use Refresh status or check the value on your Galaxy.";
    }

    private async Task<bool> RefreshBudsOnStatusCoreAsync(Device device)
    {
        if (!IsBudsOnSettingsDevice(device))
            return false;

        await DisconnectAsync();
        if (!ReferenceEquals(Device.Current, device) || AlternativeModeEnabled || !await ConnectAsync(device))
            return false;

        for (var i = 0; i < 20; i++)
        {
            if (!ReferenceEquals(Device.Current, device) || AlternativeModeEnabled)
                return false;
            if (IsConnected && BudsOnDiagnostics.HasFreshStatus(device))
                return true;
            await Task.Delay(200);
        }
        return false;
    }
#endif

    public async Task SendAltAsync(SppAlternativeMessage msg)
    {
        // Block SMEP/MDE property writes''')

touchpad_code = 'GalaxyBudsClient/Interface/Pages/TouchpadPage.axaml.cs'
replace_once(touchpad_code,
    'using Avalonia.Interactivity;\n',
    'using Avalonia.Controls;\nusing Avalonia.Interactivity;\nusing FluentAvalonia.UI.Controls;\n')
replace_once(touchpad_code,
    'using GalaxyBudsClient.Model.Config;\n',
    'using GalaxyBudsClient.Model.Config;\nusing GalaxyBudsClient.Platform;\n')
replace_once(touchpad_code,
    '    private void OnEditLeftCustomActionClicked(object? sender, RoutedEventArgs e)\n',
    '''    private async void OnBudsOnMediaClicked(object? sender, RoutedEventArgs e) =>
        await SetBudsOnTouchpadOptionAsync(sender, BudsOnDiagnostics.Option.Media);

    private async void OnBudsOnAnswerOrEndClicked(object? sender, RoutedEventArgs e) =>
        await SetBudsOnTouchpadOptionAsync(sender, BudsOnDiagnostics.Option.AnswerOrEnd);

    private async void OnBudsOnDeclineClicked(object? sender, RoutedEventArgs e) =>
        await SetBudsOnTouchpadOptionAsync(sender, BudsOnDiagnostics.Option.Decline);

    private async void OnBudsOnLeftHoldVolumeClicked(object? sender, RoutedEventArgs e) =>
        await SetBudsOnTouchpadOptionAsync(sender, BudsOnDiagnostics.Option.LeftHoldVolume, "left");

    private async void OnBudsOnRightHoldVolumeClicked(object? sender, RoutedEventArgs e) =>
        await SetBudsOnTouchpadOptionAsync(sender, BudsOnDiagnostics.Option.RightHoldVolume, "right");

    private async Task SetBudsOnTouchpadOptionAsync(object? sender, BudsOnDiagnostics.Option option,
        string? holdSide = null)
    {
        if (sender is not Button { CommandParameter: bool desired } ||
            ViewModel is not { IsBudsOnTouchpadBusy: false } viewModel)
            return;

        var bluetooth = BluetoothImpl.Instance;
        var device = bluetooth.Device.Current;
        if (device == null || !bluetooth.IsBudsOnSettingsDevice(device))
            return;

        if (BudsOnDiagnostics.GetControlValue(device, option) != !desired)
        {
            viewModel.RefreshBudsOnTouchpad();
            viewModel.BudsOnTouchpadResult = "Check the current setting and try again.";
            return;
        }

        viewModel.IsBudsOnTouchpadBusy = true;
        try
        {
            if (holdSide is not null)
            {
                if (TopLevel.GetTopLevel(this) is not { } host)
                    return;

                var target = desired ? "on" : "off";
                var dialog = new FAContentDialog
                {
                    Title = $"Volume on {holdSide} hold",
                    Content = $"This experimental change turns {target} volume control when you hold the {holdSide} earbud. You can reverse it here after the earbuds report the new state.",
                    PrimaryButtonText = $"Turn {target}",
                    CloseButtonText = "Cancel",
                    DefaultButton = FAContentDialogButton.Close
                };
                if (await dialog.ShowAsync(host) != FAContentDialogResult.Primary)
                    return;
            }

            viewModel.BudsOnTouchpadResult = "Applying change…";
            var result = await bluetooth.SetBudsOnOptionAsync(device, option, desired);
            if (ReferenceEquals(bluetooth.Device.Current, device))
                viewModel.BudsOnTouchpadResult = result;
        }
        finally
        {
            viewModel.IsBudsOnTouchpadBusy = false;
            viewModel.RefreshBudsOnTouchpad();
        }
    }

    private async void OnRefreshBudsOnTouchpadClicked(object? sender, RoutedEventArgs e)
    {
        if (ViewModel is not { IsBudsOnTouchpadBusy: false } viewModel)
            return;

        var bluetooth = BluetoothImpl.Instance;
        var device = bluetooth.Device.Current;
        if (device == null || !bluetooth.IsBudsOnSettingsDevice(device))
            return;

        viewModel.IsBudsOnTouchpadBusy = true;
        viewModel.BudsOnTouchpadResult = "Refreshing status…";
        try
        {
            var result = await bluetooth.RefreshBudsOnStatusAsync(device);
            if (ReferenceEquals(bluetooth.Device.Current, device))
                viewModel.BudsOnTouchpadResult = result;
        }
        finally
        {
            viewModel.IsBudsOnTouchpadBusy = false;
            viewModel.RefreshBudsOnTouchpad();
        }
    }

    private void OnEditLeftCustomActionClicked(object? sender, RoutedEventArgs e)
''')


equalizer_view = 'GalaxyBudsClient/Interface/Pages/EqualizerPage.axaml'
replace_once(equalizer_view,
    '            <controls:SettingsGroup>\n'
    '                <controls:SettingsComboBoxItem\n',
    '''            <StackPanel IsVisible="{Binding IsBudsOnEqualizer}" Spacing="8">
                <controls:SettingsGroup>
                    <controls:SettingsSymbolItem Content="Current preset"
                                                 Description="{Binding BudsOnEqualizerDescription, Mode=OneWay}"
                                                 Symbol="DeviceEq" />
                </controls:SettingsGroup>
                <Button Content="Change preset…"
                        IsEnabled="{Binding CanSetBudsOnEqualizer}"
                        Click="OnSetBudsOnEqualizerClicked" />
                <TextBlock IsVisible="{Binding IsBudsOnCustomEqualizer}"
                           Text="Select a standard preset on your Galaxy to change presets here."
                           TextWrapping="Wrap" />
                <Button Content="View custom EQ curves…"
                        IsEnabled="{Binding CanReadBudsOnEqualizerCurves}"
                        Click="OnReadBudsOnEqualizerCurvesClicked" />
                <Button Content="Refresh status"
                        IsEnabled="{Binding CanReadBudsOnEqualizerCurves}"
                        Click="OnRefreshBudsOnEqualizerClicked" />
            </StackPanel>

            <controls:SettingsGroup IsVisible="{Binding !IsBudsOnEqualizer}">
                <controls:SettingsComboBoxItem
''')

equalizer_vm = 'GalaxyBudsClient/Interface/ViewModels/Pages/EqualizerPageViewModel.cs'
replace_once(equalizer_vm,
    'using Avalonia.Controls;\n',
    'using Avalonia.Controls;\nusing Avalonia.Threading;\n')
replace_once(equalizer_vm,
    '    public EqualizerPageViewModel()\n    {\n',
    '''    private readonly DispatcherTimer _budsOnEqualizerTimer = new() { Interval = TimeSpan.FromSeconds(1) };
    private byte? _budsOnEqualizerPreset;

    public bool IsBudsOnEqualizer { get; private set; }
    public bool CanSetBudsOnEqualizer { get; private set; }
    public bool CanReadBudsOnEqualizerCurves { get; private set; }
    private bool _hasLiveBudsOnEqualizer;
    public bool IsBudsOnCustomEqualizer => IsBudsOnEqualizer && _budsOnEqualizerPreset == 6;
    public string BudsOnEqualizerDescription => _budsOnEqualizerPreset is { } preset
        ? (BudsOnDiagnostics.GetEqualizerPresetName(preset) ?? "Unknown preset") +
            (_hasLiveBudsOnEqualizer ? "" : " · Last reported")
        : "Waiting for earbuds";

    public EqualizerPageViewModel()
    {
        _budsOnEqualizerTimer.Tick += (_, _) => RefreshBudsOnEqualizer();
''')
replace_once(equalizer_vm,
    '    public override async void OnNavigatedTo()\n    {\n',
    '''    public override async void OnNavigatedTo()
    {
        RefreshBudsOnEqualizer();
        _budsOnEqualizerTimer.Start();
        if (IsBudsOnEqualizer)
            return;

''')
replace_once(equalizer_vm,
    '    private void OnAnyMessageDecoded(object? sender, BaseMessageDecoder decoder)\n',
    '''    public override void OnNavigatedFrom() => _budsOnEqualizerTimer.Stop();

    private void RefreshBudsOnEqualizer()
    {
        var bluetooth = BluetoothImpl.Instance;
        var device = bluetooth.Device.Current;
        var isBudsOn = device?.Model == Models.BudsOn;
        var canReadCurves = device is not null && isBudsOn && bluetooth.IsBudsOnSettingsDevice(device);
        var preset = device is not null && canReadCurves
            ? BudsOnDiagnostics.GetEqualizerPreset(device)
            : null;
        var livePreset = canReadCurves && BudsOnDiagnostics.HasLiveBudsOnEqualizer(device!);
        var canSet = canReadCurves && !bluetooth.BudsOnReadOnly && BudsOnDiagnostics.GetEqualizerTestSample(device!) != null;
        if (IsBudsOnEqualizer == isBudsOn && _budsOnEqualizerPreset == preset &&
            CanReadBudsOnEqualizerCurves == canReadCurves && CanSetBudsOnEqualizer == canSet &&
            _hasLiveBudsOnEqualizer == livePreset)
            return;

        IsBudsOnEqualizer = isBudsOn;
        _budsOnEqualizerPreset = preset;
        _hasLiveBudsOnEqualizer = livePreset;
        CanSetBudsOnEqualizer = canSet;
        CanReadBudsOnEqualizerCurves = canReadCurves;
        this.RaisePropertyChanged(nameof(IsBudsOnEqualizer));
        this.RaisePropertyChanged(nameof(BudsOnEqualizerDescription));
        this.RaisePropertyChanged(nameof(CanSetBudsOnEqualizer));
        this.RaisePropertyChanged(nameof(IsBudsOnCustomEqualizer));
        this.RaisePropertyChanged(nameof(CanReadBudsOnEqualizerCurves));
    }

    private void OnAnyMessageDecoded(object? sender, BaseMessageDecoder decoder)
''')
replace_once(equalizer_vm,
    '    private async void OnPropertyChanged(object? sender, PropertyChangedEventArgs args)\n    {\n',
    '''    private async void OnPropertyChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (BluetoothImpl.Instance.CurrentModel == Models.BudsOn)
            return;

''')
replace_once(equalizer_vm,
    '    protected override void OnEventReceived(Event type, object? parameter)\n    {\n',
    '''    protected override void OnEventReceived(Event type, object? parameter)
    {
        if (BluetoothImpl.Instance.CurrentModel == Models.BudsOn)
            return;

''')

equalizer_code = 'GalaxyBudsClient/Interface/Pages/EqualizerPage.axaml.cs'
replace_once(equalizer_code,
    'using GalaxyBudsClient.Interface.ViewModels.Pages;\n',
    '''using System;
using System.Collections.Generic;
using System.Linq;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using FluentAvalonia.UI.Controls;
using GalaxyBudsClient.Interface.Dialogs;
using GalaxyBudsClient.Interface.ViewModels.Pages;
using GalaxyBudsClient.Platform;
using Serilog;
''')
replace_once(equalizer_code,
    '    public EqualizerPage()\n',
    '''    private bool _budsOnEqualizerActionOpen;

    public EqualizerPage()
''')
replace_once(equalizer_code,
    '        InitializeComponent();\n    }\n',
    '''        InitializeComponent();
    }

    private async void OnSetBudsOnEqualizerClicked(object? sender, RoutedEventArgs e)
    {
        if (_budsOnEqualizerActionOpen || TopLevel.GetTopLevel(this) is not { } host)
            return;

        var bluetooth = BluetoothImpl.Instance;
        var device = bluetooth.Device.Current;
        if (device == null || !bluetooth.IsBudsOnSettingsDevice(device))
            return;

        _budsOnEqualizerActionOpen = true;
        try
        {
            if (bluetooth.BudsOnReadOnly)
            {
                await new MessageBox
                {
                    Title = "Buds On is in read-only mode",
                    Description = "You can turn off read-only mode in Settings."
                }.ShowAsync();
                return;
            }

            if (BudsOnDiagnostics.GetEqualizerTestSample(device) is not { } sample ||
                BudsOnDiagnostics.GetEqualizerPresetName(sample.Preset) is not { } currentName)
            {
                await new MessageBox
                {
                    Title = "Fresh standard preset needed",
                    Description = "Use Refresh status. If Custom is active, select a standard preset on your Galaxy first."
                }.ShowAsync();
                return;
            }

            var choices = new List<(byte Preset, string Name)>();
            for (byte preset = 0; preset <= 5; preset++)
            {
                if (preset != sample.Preset && BudsOnDiagnostics.GetEqualizerPresetName(preset) is { } name)
                    choices.Add((preset, name));
            }

            if (choices.Count == 0)
                return;

            var picker = new ComboBox
            {
                ItemsSource = choices.Select(choice => choice.Name).ToArray(),
                SelectedIndex = 0,
                MinWidth = 180
            };
            var dialog = new FAContentDialog
            {
                Title = "Change preset",
                Content = new StackPanel
                {
                    Spacing = 8,
                    Children =
                    {
                        new TextBlock
                        {
                            Text = $"Your earbuds report {currentName}. Choose a different preset.",
                            TextWrapping = TextWrapping.Wrap
                        },
                        picker
                    }
                },
                PrimaryButtonText = "Apply preset",
                CloseButtonText = "Cancel",
                DefaultButton = FAContentDialogButton.Close
            };
            if (await dialog.ShowAsync(host) != FAContentDialogResult.Primary ||
                (uint)picker.SelectedIndex >= (uint)choices.Count)
                return;

            var outcome = await bluetooth.SetBudsOnEqualizerAsync(device, sample, choices[picker.SelectedIndex].Preset);
            await new MessageBox
            {
                Title = "Equalizer preset",
                Description = outcome
            }.ShowAsync();
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Buds On preset change failed");
            await new MessageBox
            {
                Title = "Preset change interrupted",
                Description = "Check the current preset on your Galaxy."
            }.ShowAsync();
        }
        finally
        {
            _budsOnEqualizerActionOpen = false;
        }
    }

    private async void OnRefreshBudsOnEqualizerClicked(object? sender, RoutedEventArgs e)
    {
        if (_budsOnEqualizerActionOpen)
            return;

        var bluetooth = BluetoothImpl.Instance;
        var device = bluetooth.Device.Current;
        if (device == null || !bluetooth.IsBudsOnSettingsDevice(device))
            return;

        _budsOnEqualizerActionOpen = true;
        try
        {
            if (await bluetooth.RefreshBudsOnStatusAsync(device) is { } error)
                await new MessageBox { Title = "Refresh status", Description = error }.ShowAsync();
        }
        catch (Exception ex)
        {
            Log.Warning(ex, "Buds On status refresh interrupted");
            await new MessageBox
            {
                Title = "Refresh status",
                Description = "Reconnect your Buds On and try again."
            }.ShowAsync();
        }
        finally
        {
            _budsOnEqualizerActionOpen = false;
        }
    }

    private async void OnReadBudsOnEqualizerCurvesClicked(object? sender, RoutedEventArgs e)
    {
        if (_budsOnEqualizerActionOpen || TopLevel.GetTopLevel(this) is not { } host)
            return;

        var bluetooth = BluetoothImpl.Instance;
        var device = bluetooth.Device.Current;
        if (device == null || !bluetooth.IsBudsOnSettingsDevice(device))
            return;

        _budsOnEqualizerActionOpen = true;
        try
        {
            var summary = await bluetooth.ReadBudsOnEqualizerCurvesAsync(device);
            var dialog = new FAContentDialog
            {
                Title = "Custom EQ curves",
                Content = new ScrollViewer
                {
                    MaxHeight = 400,
                    Content = new TextBlock { Text = summary, TextWrapping = TextWrapping.Wrap }
                },
                CloseButtonText = "Close",
                DefaultButton = FAContentDialogButton.Close
            };
            await dialog.ShowAsync(host);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Buds On custom EQ read failed");
            await new MessageBox
            {
                Title = "Could not read custom EQ curves",
                Description = "Reconnect your Buds On and try again."
            }.ShowAsync();
        }
        finally
        {
            _budsOnEqualizerActionOpen = false;
        }
    }
''')


replace_once(native + 'src/Bluetooth.mm',
    '''- (BOOL)disconnect
{
''',
    '''- (BOOL)disconnect {
    return [self disconnectExpectedChannel:nil];
}

- (BOOL)disconnectExpectedChannel:(IOBluetoothRFCOMMChannel *)expected
{
''')
replace_once(native + 'src/Bluetooth.mm',
    '''    @synchronized (self) {
        channel = mRFCOMMChannel;
        mRFCOMMChannel = nil;
''',
    '''    @synchronized (self) {
        if (expected && mRFCOMMChannel != expected)
            return FALSE;
        channel = mRFCOMMChannel;
        mRFCOMMChannel = nil;
''')
replace_once(native + 'src/Bluetooth.mm',
    '''- (void)rfcommChannelClosed:(IOBluetoothRFCOMMChannel *)rfcommChannel {
    [self disconnect];
    [self signalChannelClosedOnce];
}
''',
    '''- (void)rfcommChannelClosed:(IOBluetoothRFCOMMChannel *)rfcommChannel {
    if (rfcommChannel && [self disconnectExpectedChannel:rfcommChannel])
        [self signalChannelClosedOnce];
}
''')

print('Done. Galaxy Buds On settings and diagnostics enabled.')
