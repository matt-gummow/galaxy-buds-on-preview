#!/usr/bin/env python3
"""Buds On recognition, diagnostics and a one-shot call control test.

Usage: python3 add_buds_on.py /path/to/GalaxyBudsClient
Targets upstream commit 85dfc8bb39fc45d3c30ecf71ab2c663fb1d41729.
Includes an explicit, one-shot call control tests on macOS.
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
/// The call control tests use the dedicated macOS diagnostic transport.
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
    '        // The generic encoder never sends commands to SM-U600.\n'
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
    private const int EqualizerOffset = 9;
    private const int GestureFlagsOffset = 10;
    private const int CallDoubleTapBit = 4;
    private const int CallHoldBit = 5;
    private const int HoldStatusOffset = 11;
    // Bits 0–5 and 7 are candidates for the controls visible in Galaxy Wearable.
    private const byte ObservedGestureMask = 0xBF;

    private readonly record struct SettingsSnapshot(byte EqualizerCode, byte GestureFlags,
        byte LeftHoldStatus, byte RightHoldStatus);

    private readonly byte[] _pending = new byte[MaximumBodyLength + 4];
    private readonly Dictionary<(byte Id, int PayloadLength), long> _signatures = new();
    private readonly Queue<(long Connection, long Frame, SettingsSnapshot Settings)> _settingsObservations = new();
    private bool _observeSettings;
    private long _settingsConnection;
    private SettingsSnapshot? _lastSettings;
    public (long Frame, byte Flags)? LatestCallStatus { get; private set; }
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
        _lastSettings = null;
        LatestCallStatus = null;
        CallCommandAckFrame = 0;

        if (newSettingsDevice)
        {
            _settingsObservations.Clear();
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
                LatestCallStatus = null;
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
                LatestCallStatus = null;
                MoveToNextStart(1);
                continue;
            }

            int frameLength = size + 4;
            if (_pendingLength < frameLength)
                return;

            if (_pending[frameLength - 1] != End || !HasValidChecksum(size))
            {
                LatestCallStatus = null;
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
                LatestCallStatus = null;
            return;
        }

        var payload = _pending.AsSpan(4, payloadLength);
        if (id == 0x42 && payload.Length > 0 && payload[0] == 0x90)
            CallCommandAckFrame = _validFrames;
        if (id == (byte)MsgIds.STATUS_UPDATED && payloadLength >= 7)
            RecordBatteryCandidate(payload, batteryOffset: 1, ref _basicStatus);
        if (id == (byte)MsgIds.EXTENDED_STATUS_UPDATED)
        {
            if (payloadLength == 63 && RecordBatteryCandidate(payload, batteryOffset: 2, ref _extendedStatus))
                RecordSettingsCandidate(payload);
            else
                LatestCallStatus = null;
        }
    }

    private void RecordSettingsCandidate(ReadOnlySpan<byte> payload)
    {
        if (!_observeSettings)
            return;

        LatestCallStatus = (_validFrames, payload[GestureFlagsOffset]);
        var assignments = payload[HoldStatusOffset];
        var settings = new SettingsSnapshot(payload[EqualizerOffset],
            (byte)(payload[GestureFlagsOffset] & ObservedGestureMask),
            (byte)(assignments >> 4), (byte)(assignments & 0x0F));
        if (_lastSettings == settings)
            return;

        _lastSettings = settings;
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

    public (bool AnswerOrEnd, bool Decline)? GetCallControls() =>
        _lastSettings is { } settings
            ? (IsFlagSet(settings.GestureFlags, CallDoubleTapBit), IsFlagSet(settings.GestureFlags, CallHoldBit))
            : null;

    public (int? Earbuds, int? Case) GetBattery()
    {
        if (_extendedStatus.Count < 2)
            return (null, null);

        var (_, left, right, caseBattery) = _extendedStatus;
        int? earbuds = left <= 100 && right <= 100 ? Math.Min(left, right) : null;
        return (earbuds, caseBattery <= 100 ? caseBattery : null);
    }

    public IEnumerable<string> SnapshotLines()
    {
        yield return $"CRC-valid modern Samsung SPP frames: {_validFrames}";
        foreach (var entry in _signatures)
            yield return $"SPP ID 0x{entry.Key.Id:X2}, payload length {entry.Key.PayloadLength}: {entry.Value} frame(s)";
        if (_otherSignatures > 0)
            yield return $"Frames with other ID/length signatures: {_otherSignatures}";
        if (_basicStatus.Count >= 2)
            yield return FormatBatteryCandidate((byte)MsgIds.STATUS_UPDATED, _basicStatus);
        if (_extendedStatus.Count >= 2)
            yield return FormatBatteryCandidate((byte)MsgIds.EXTENDED_STATUS_UPDATED, _extendedStatus);
        if (_settingsObservations.Count > 0)
            yield return "Unverified Buds On candidate settings (extended status 0x61)";
        foreach (var (connection, frame, settings) in _settingsObservations)
            yield return $"  Connection {connection}, valid frame {frame} | {FormatSettings(settings)}";
    }

    private static string FormatSettings(SettingsSnapshot settings)
    {
        var flags = settings.GestureFlags;
        return $"EQ code {settings.EqualizerCode} | Hold status nibbles L={settings.LeftHoldStatus} R={settings.RightHoldStatus} | " +
            $"Touch master candidate {FormatFlag(flags, 7)}, tap {FormatFlag(flags, 3)}, double {FormatFlag(flags, 2)}, " +
            $"triple {FormatFlag(flags, 1)}, hold {FormatFlag(flags, 0)} | " +
            $"Call double {FormatFlag(flags, CallDoubleTapBit)}, call hold {FormatFlag(flags, CallHoldBit)}";
    }

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
    private static long _attemptedStatusFrame;

    internal enum CallControl : byte
    {
        AnswerOrEnd = 0x10,
        Decline = 0x20
    }

    internal readonly record struct CallSample(long Session, long Frame, byte Flags)
    {
        public bool IsOn(CallControl control) => (Flags & (byte)control) != 0;
    }

    public static CallSample? GetCallTestSample(Device device)
    {
        lock (Sync)
        {
            if (!ReferenceEquals(_receiveDevice, device) || _receiveStamp == 0 ||
                FrameProbe.HasPartialFrame || FrameProbe.LatestCallStatus is not { } status ||
                status.Frame == _attemptedStatusFrame ||
                Stopwatch.GetElapsedTime(_statusObservedAt) > TimeSpan.FromSeconds(60))
                return null;

            return new CallSample(_receiveSession, status.Frame, status.Flags);
        }
    }

    public static (ulong Stamp, CallSample Sample, long ReplyBarrier)? TakeCallTestSample(Device device, CallSample expected)
    {
        lock (Sync)
        {
            if (GetCallTestSample(device) is not { } current || current.Session != expected.Session ||
                current.Flags != expected.Flags)
                return null;

            _attemptedStatusFrame = current.Frame;
            return (_receiveStamp, current, FrameProbe.LastFrame);
        }
    }

    public static (byte? Flags, bool Acknowledged)? GetCallTestReadback(Device device, long session, long replyBarrier)
    {
        lock (Sync)
        {
            if (!ReferenceEquals(_receiveDevice, device) || _receiveSession != session)
                return null;

            var newer = FrameProbe.LatestCallStatus is { } status && status.Frame > replyBarrier
                ? (byte?)status.Flags
                : null;
            return (newer, FrameProbe.CallCommandAckFrame > replyBarrier);
        }
    }

    public static (int? Earbuds, int? Case) GetBattery(Device device)
    {
        lock (Sync)
            return ReferenceEquals(_receiveDevice, device) ? FrameProbe.GetBattery() : (null, null);
    }

    public static (bool AnswerOrEnd, bool Decline)? GetCallControls(Device device)
    {
        lock (Sync)
            return ReferenceEquals(_receiveDevice, device) ? FrameProbe.GetCallControls() : null;
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
            _receiveDevice = device;
            _receiveSession++;
            _receiveStamp = 0;
            _statusObservedAt = 0;
            _attemptedStatusFrame = 0;
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
            if (!ReferenceEquals(_receiveDevice, device))
                return;
            if (_receiveStamp != 0 && stamp != _receiveStamp + 1)
            {
                // A missing or out-of-order callback invalidates the status and any partial frame.
                _receiveSession++;
                FrameProbe.ResetStream(observeSettings: device != null, newSettingsDevice: false);
                _statusObservedAt = 0;
                if (stamp != 0 && stamp <= _receiveStamp)
                    return;
            }
            _receiveStamp = stamp;
            _chunks++;
            _bytes += frame.Length;
            if (FirstChunkLengths.Count < 16)
                FirstChunkLengths.Add(frame.Length);
            var previous = FrameProbe.LatestCallStatus?.Frame;
            FrameProbe.Append(frame);
            if (FrameProbe.LatestCallStatus?.Frame != previous)
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
                "Galaxy Buds On (SM-U600) read-only Bluetooth report",
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
        {
            BudsOnDiagnostics.RecordRx(null, frame);
            return;
        }

        /* Discard data if not properly registered */
''')

settings_page = 'GalaxyBudsClient/Interface/Pages/SettingsPage.axaml'
replace_once(settings_page,
    '            <ui:FASettingsExpander Header="{ext:Translate {x:Static i18N:Keys.SettingsMultipointHeader}}"',
    '''            <Button Content="Copy Buds On connection report"
                    IsVisible="{x:Static platform:PlatformUtils.IsOSX}"
                    Click="OnCopyBudsOnReportClicked" />

            <ui:FASettingsExpander Header="{ext:Translate {x:Static i18N:Keys.SettingsMultipointHeader}}"''')
settings_code = 'GalaxyBudsClient/Interface/Pages/SettingsPage.axaml.cs'
replace_once(settings_code,
    'using Avalonia.Interactivity;\n',
    'using Avalonia.Controls;\nusing Avalonia.Input.Platform;\nusing Avalonia.Interactivity;\n')
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
    '''        _macAddress = [[NSString alloc] initWithString:mac];
        if (diagnostic)
            diagnostic("Management RFCOMM channel opened");
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
    '    BOOL _channelClosedSignalled;\n    bool _diagnosticChannel;\n')
replace_once(native + 'src/Bluetooth.mm',
    '        mRFCOMMChannel = tempRFCOMMChannel;\n',
    '        mRFCOMMChannel = tempRFCOMMChannel;\n        _diagnosticChannel = diagnostic != nullptr;\n        ++_diagnosticStamp;\n')
replace_once(native + 'src/Bluetooth.mm',
    '        mRFCOMMChannel = nil;\n',
    '        mRFCOMMChannel = nil;\n        _diagnosticChannel = false;\n        ++_diagnosticStamp;\n')
replace_once(native + 'src/Bluetooth.mm',
    '        channel = mRFCOMMChannel;\n    }\n\n    if (channel != nil) {\n        if (![channel isOpen]) {',
    '''        // Check the mode while taking the native channel snapshot. A previously queued
        // write may have raced with a reconnect after the managed guard ran.
        if (_diagnosticChannel)
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

        var (earbuds, caseBattery) = BudsOnDiagnostics.GetBattery(device);
        if (earbuds is int level)
            BudsOnBatteryText = caseBattery is int caseLevel
                ? $"Earbuds {level}% · Case {caseLevel}%"
                : $"Earbuds {level}%";
        else if (caseBattery is int caseOnly)
            BudsOnBatteryText = $"Case {caseOnly}%";
        else
            return false;

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

            <controls:SettingsGroup IsVisible="{Binding HasBudsOnCallControls}">
                <controls:SettingsSymbolItem
                    Content="{ext:Translate {x:Static i18N:Keys.TouchpadGestureDoubleForCall}}"
                    Description="{Binding BudsOnCallDoubleTapDescription, Mode=OneWay}"
                    Symbol="CallInbound" />
                <controls:SettingsSymbolItem
                    Content="{ext:Translate {x:Static i18N:Keys.TouchpadGestureHoldForCall}}"
                    Description="{Binding BudsOnCallHoldDescription, Mode=OneWay}"
                    Symbol="CallProhibited" />
                <Button Content="Test Double tap during call…"
                        Click="OnTestBudsOnAnswerCallClicked" />
                <Button Content="Test Touch and hold during call…"
                        Click="OnTestBudsOnDeclineCallClicked" />
            </controls:SettingsGroup>
''')

touchpad_vm = 'GalaxyBudsClient/Interface/ViewModels/Pages/TouchpadPageViewModel.cs'
replace_once(touchpad_vm,
    '    public override Control CreateView() => new TouchpadPage { DataContext = this };\n',
    '''    private readonly DispatcherTimer _budsOnCallTimer = new() { Interval = TimeSpan.FromSeconds(1) };
    private (bool AnswerOrEnd, bool Decline)? _budsOnCallControls;

    public bool HasBudsOnCallControls => _budsOnCallControls.HasValue;
    public string? BudsOnCallDoubleTapDescription => DescribeCallControl(_budsOnCallControls?.AnswerOrEnd);
    public string? BudsOnCallHoldDescription => DescribeCallControl(_budsOnCallControls?.Decline);

    private static string? DescribeCallControl(bool? enabled) => enabled switch
    {
        true => "On",
        false => "Off",
        null => null
    };

    public override Control CreateView() => new TouchpadPage { DataContext = this };
''')
replace_once(touchpad_vm,
    '    public TouchpadPageViewModel()\n    {\n',
    '    public TouchpadPageViewModel()\n    {\n'
    '        _budsOnCallTimer.Tick += (_, _) => RefreshBudsOnCallControls();\n')
replace_once(touchpad_vm,
    '    public override void OnNavigatedTo() => UpdateEditStates();\n',
    '''    public override void OnNavigatedTo()
    {
        UpdateEditStates();
        RefreshBudsOnCallControls();
        if (PlatformUtils.IsOSX)
            _budsOnCallTimer.Start();
    }

    public override void OnNavigatedFrom() => _budsOnCallTimer.Stop();

    private void RefreshBudsOnCallControls()
    {
        var bluetooth = BluetoothImpl.Instance;
        var device = bluetooth.Device.Current;
        var controls = PlatformUtils.IsOSX && bluetooth.IsConnected && device?.Model == Models.BudsOn
            ? BudsOnDiagnostics.GetCallControls(device)
            : null;
        if (_budsOnCallControls == controls)
            return;

        _budsOnCallControls = controls;
        this.RaisePropertyChanged(nameof(HasBudsOnCallControls));
        this.RaisePropertyChanged(nameof(BudsOnCallDoubleTapDescription));
        this.RaisePropertyChanged(nameof(BudsOnCallHoldDescription));
    }
''')

write_once(native + 'src/BudsOnCallControl.h', '''#pragma once

#include <array>
#include <cstdint>

inline std::array<uint8_t, 17> MakeBudsOnCallFrame(uint8_t flags) {
    // The SM-U600 Samsung app writes its full touch control vector. The caller
    // changes the selected control in an otherwise unmodified status sample.
    constexpr std::array<uint8_t, 8> order{7, 3, 2, 1, 0, 4, 5, 6};
    std::array<uint8_t, 17> frame{0xfd, 0x0d, 0x00, 0x90};
    for (std::size_t i = 0; i < order.size(); ++i)
        frame[4 + i] = (flags >> order[i]) & 1;
    frame[12] = 1;
    frame[13] = 1;

    uint16_t crc = 0;
    for (std::size_t i = 3; i < 14; ++i) {
        crc ^= static_cast<uint16_t>(frame[i]) << 8;
        for (int bit = 0; bit < 8; ++bit)
            crc = static_cast<uint16_t>((crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0));
    }
    frame[14] = static_cast<uint8_t>(crc);
    frame[15] = static_cast<uint8_t>(crc >> 8);
    frame[16] = 0xdd;
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
''')
replace_once(native + 'include/Native.h',
    'extern BT_SEND_RESULT bt_send(BluetoothImpl *self, void *data, unsigned int length);\n',
    '''extern BT_SEND_RESULT bt_send(BluetoothImpl *self, void *data, unsigned int length);
extern BT_SEND_RESULT bt_send_budson_call_test(BluetoothImpl *self, uint64_t stamp, uint8_t flags, uint8_t mask, uint8_t enabled);
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
    '''- (void)rfcommChannelData:(IOBluetoothRFCOMMChannel *)rfcommChannel data:(void *)dataPointer length:(size_t)dataLength {
    uint64_t stamp = 0;
    @synchronized (self) {
        if (_diagnosticChannel) {
            if (rfcommChannel != mRFCOMMChannel)
                return;
            stamp = ++_diagnosticStamp;
        }
    }
    if (_onChannelData)
        _onChannelData(dataPointer, dataLength, stamp);
}
''')
replace_once(native + 'src/Bluetooth.mm',
    '- (void)setOnChannelData:(Bt_OnChannelData)callback {\n',
    '''- (BT_SEND_RESULT)sendBudsOnCallTest:(uint64_t)stamp flags:(UInt8)flags mask:(UInt8)mask enabled:(UInt8)enabled {
    if ((mask != 0x10 && mask != 0x20) || enabled > 1 || ((flags & mask) != 0) == (enabled != 0))
        return BT_SEND_ENULL;

    auto frame = MakeBudsOnCallFrame(flags ^ mask);
    IOBluetoothRFCOMMChannel *channel;
    @synchronized (self) {
        if (!_diagnosticChannel || _channelClosedSignalled || stamp == 0 ||
            stamp != _diagnosticStamp || stamp == _lastTestStamp || mRFCOMMChannel == nil)
            return BT_SEND_ENULL;

        _lastTestStamp = stamp;
        channel = mRFCOMMChannel;
    }

    // The same retained channel either accepts the complete frame or fails.
    // A close or reconnect cannot redirect a queued test to another channel.
    if (![channel isOpen] || [channel getMTU] < frame.size())
        return BT_SEND_ENULL;

    const auto result = [channel writeSync:frame.data() length:static_cast<UInt16>(frame.size())];
    return result == kIOReturnSuccess ? BT_SEND_SUCCESS : BT_SEND_EUNKNOWN;
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

                    unsafe
                    {
                        return Bluetooth.bt_send_budson_call_test(_nativePtr, stamp, flags, mask, enabled ? (byte)1 : (byte)0)
                            == BT_SEND_RESULT.BT_SEND_SUCCESS;
                    }
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
    '''    internal bool IsBudsOnCallTestDevice(Device device) =>
        PlatformUtils.IsOSX && !AlternativeModeEnabled && IsConnected &&
        device.Model == Models.BudsOn && ReferenceEquals(Device.Current, device);

#if OSX
    private int _budsOnCallTestInProgress;
#endif

    internal async Task<string> TestBudsOnCallAsync(Device device, BudsOnDiagnostics.CallSample expected,
        BudsOnDiagnostics.CallControl control)
    {
#if OSX
        if (_backend is OSX.BluetoothService backend && IsBudsOnCallTestDevice(device) &&
            control is (BudsOnDiagnostics.CallControl.AnswerOrEnd or BudsOnDiagnostics.CallControl.Decline))
        {
            if (Interlocked.CompareExchange(ref _budsOnCallTestInProgress, 1, 0) != 0)
                return "A call control test is already in progress.";

            try
            {
                long replyBarrier = 0;
                var sentSample = expected;
                var enable = !expected.IsOn(control);
                var sent = await Task.Run(() => backend.TrySendBudsOnCallTest(
                    device.MacAddress, expected.Flags, (byte)control, enable, () =>
                    {
                        if (!IsBudsOnCallTestDevice(device) ||
                            BudsOnDiagnostics.TakeCallTestSample(device, expected) is not { } approved)
                            return null;

                        sentSample = approved.Sample;
                        replyBarrier = approved.ReplyBarrier;
                        return approved.Stamp;
                    }));
                if (sent)
                {
                    BudsOnDiagnostics.Record($"Call control test sent ({control} {(enable ? "On" : "Off")})");
                    var outcome = await WaitForBudsOnCallTestAsync(device, sentSample, control, replyBarrier);
                    BudsOnDiagnostics.Record(outcome);
                    return outcome;
                }
            }
            finally
            {
                Volatile.Write(ref _budsOnCallTestInProgress, 0);
            }
        }
#endif
        return "The test frame was not sent. Reconnect to refresh the earbuds’ status before testing again.";
    }

    private async Task<string> WaitForBudsOnCallTestAsync(Device device, BudsOnDiagnostics.CallSample sent,
        BudsOnDiagnostics.CallControl control, long replyBarrier)
    {
        var acknowledged = false;
        var mask = (byte)control;
        for (var i = 0; i < 32; i++)
        {
            await Task.Delay(250);
            if (!IsBudsOnCallTestDevice(device) ||
                BudsOnDiagnostics.GetCallTestReadback(device, sent.Session, replyBarrier) is not { } readback)
                return "The connection changed before the result could be verified. Check the setting on your Galaxy.";

            acknowledged |= readback.Acknowledged;
            if (readback.Flags == (byte)(sent.Flags ^ mask))
                return "The earbuds reported the new call setting and the other touch flags matched.";
            if (readback.Flags is byte flags && ((flags ^ sent.Flags) & ~mask) != 0)
                return "Other touch flags changed during the test. Check the settings on your Galaxy.";
        }

        return acknowledged
            ? "The earbuds acknowledged the command. Check your Galaxy to confirm the setting changed."
            : "The command was sent. Check your Galaxy to confirm the setting changed.";
    }

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
    '    public TouchpadPage()\n',
    '''    private bool _budsOnCallTestOpen;

    public TouchpadPage()
''')
replace_once(touchpad_code,
    '    private void OnEditLeftCustomActionClicked(object? sender, RoutedEventArgs e)\n',
    '''    private async void OnTestBudsOnAnswerCallClicked(object? sender, RoutedEventArgs e) =>
        await RunBudsOnCallTestAsync(BudsOnDiagnostics.CallControl.AnswerOrEnd, "Double tap during call");

    private async void OnTestBudsOnDeclineCallClicked(object? sender, RoutedEventArgs e) =>
        await RunBudsOnCallTestAsync(BudsOnDiagnostics.CallControl.Decline, "Touch and hold during call");

    private async Task RunBudsOnCallTestAsync(BudsOnDiagnostics.CallControl control, string label)
    {
        if (_budsOnCallTestOpen || TopLevel.GetTopLevel(this) is not { } host)
            return;

        var bluetooth = BluetoothImpl.Instance;
        var device = bluetooth.Device.Current;
        if (device == null || !bluetooth.IsBudsOnCallTestDevice(device))
            return;

        _budsOnCallTestOpen = true;
        try
        {
            if (BudsOnDiagnostics.GetCallTestSample(device) is not { } sample)
            {
                await new MessageBox
                {
                    Title = "Fresh earbuds status needed",
                    Description = "Reconnect your Buds On, then open this test as soon as the call settings appear."
                }.ShowAsync();
                return;
            }

            var target = sample.IsOn(control) ? "Off" : "On";
            var dialog = new FAContentDialog
            {
                Title = $"Test {label}",
                Content = $"Confirm these are your Galaxy Buds On (SM-U600). This sends one Bluetooth command to turn the setting {target}. Check the setting on your Galaxy afterward.",
                PrimaryButtonText = $"Set {target} once",
                CloseButtonText = "Cancel",
                DefaultButton = FAContentDialogButton.Close
            };
            if (await dialog.ShowAsync(host) != FAContentDialogResult.Primary)
                return;

            await new MessageBox
            {
                Title = "Call control test",
                Description = await bluetooth.TestBudsOnCallAsync(device, sample, control)
            }.ShowAsync();
        }
        finally
        {
            _budsOnCallTestOpen = false;
        }
    }

    private void OnEditLeftCustomActionClicked(object? sender, RoutedEventArgs e)
''')

print('Done. Buds On diagnostics and one-shot call control test enabled.')
