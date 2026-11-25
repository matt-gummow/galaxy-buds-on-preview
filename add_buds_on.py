#!/usr/bin/env python3
"""Read-only Buds On recognition and Bluetooth connection diagnostics.

Usage: python3 add_buds_on.py /path/to/GalaxyBudsClient
Targets upstream commit 85dfc8bb39fc45d3c30ecf71ab2c663fb1d41729.
This intentionally DOES NOT enable multipoint or settings writes.
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
/// EXPERIMENTAL detection-only profile for SM-U600 (Galaxy Buds On).
/// No configuration, firmware, or multipoint message is verified on this model.
/// The SPP service UUID and framing below are hypotheses awaiting a device trace.
/// BluetoothImpl blocks outgoing messages and skips SPP decoding for this model.
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
    '        // SM-U600 commands have not been verified. Block ALL outgoing normal frames.\n'
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
        private Action<byte[]>? _currentDiagnosticRx;
''')
replace_once(mac_bluetooth,
    'await ConnectAsync(_currentMac, _currentUuid, CancellationToken.None);',
    'await ConnectAsync(_currentMac, _currentUuid, CancellationToken.None,\n                            _currentDiagnostics, _currentDiagnosticRx);')
replace_once(mac_bluetooth,
    '                NewDataAvailable?.Invoke(this, byteArray);\n',
    '''                if (_currentDiagnosticRx is { } diagnosticRx)
                    diagnosticRx(byteArray);
                else
                    NewDataAvailable?.Invoke(this, byteArray);
''')
replace_once(mac_bluetooth,
    '        public async Task ConnectAsync(string macAddress, string uuid, CancellationToken cancelToken)\n',
    '''        public Task ConnectAsync(string macAddress, string uuid, CancellationToken cancelToken) =>
            ConnectAsync(macAddress, uuid, cancelToken, null, null);

        public async Task ConnectAsync(string macAddress, string uuid, CancellationToken cancelToken,
            Action<string>? diagnostics, Action<byte[]>? diagnosticRx)
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
    '''                    // The native diagnostic connection accepts no app protocol writes, even
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

write_once('GalaxyBudsClient/Platform/BudsOnFrameProbe.cs', '''using System;
using System.Collections.Generic;
using GalaxyBudsClient.Message;
using GalaxyBudsClient.Utils;

namespace GalaxyBudsClient.Platform;

// Caller serializes all access. The stream buffer retains at most one maximum-size
// modern SPP frame, and the report contains only metadata and battery candidates.
internal sealed class BudsOnFrameProbe
{
    private const byte Start = (byte)MsgConstants.Som;
    private const byte End = (byte)MsgConstants.Eom;
    private const int MaximumBodyLength = 0x03ff;
    private const int MaximumSignatures = 32;

    private readonly byte[] _pending = new byte[MaximumBodyLength + 4];
    private readonly Dictionary<(byte Id, int PayloadLength), long> _signatures = new();
    private int _pendingLength;
    private long _validFrames;
    private long _otherSignatures;
    private (long Count, byte Left, byte Right, byte Case) _basicStatus;
    private (long Count, byte Left, byte Right, byte Case) _extendedStatus;

    public void ResetStream()
    {
        _pendingLength = 0;
        _basicStatus = default;
        _extendedStatus = default;
    }

    public void Append(byte[] chunk)
    {
        foreach (var value in chunk)
        {
            if (_pendingLength == 0 && value != Start)
                continue;

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
                MoveToNextStart(1);
                continue;
            }

            int frameLength = size + 4;
            if (_pendingLength < frameLength)
                return;

            if (_pending[frameLength - 1] != End || !HasValidChecksum(size))
            {
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
            return;

        var payload = _pending.AsSpan(4, payloadLength);
        if (id == (byte)MsgIds.STATUS_UPDATED && payloadLength >= 7)
            RecordBatteryCandidate(payload, batteryOffset: 1, ref _basicStatus);
        if (id == (byte)MsgIds.EXTENDED_STATUS_UPDATED && payloadLength >= 8)
            RecordBatteryCandidate(payload, batteryOffset: 2, ref _extendedStatus);
    }

    private static void RecordBatteryCandidate(ReadOnlySpan<byte> payload, int batteryOffset,
        ref (long Count, byte Left, byte Right, byte Case) status)
    {
        var left = payload[batteryOffset];
        var right = payload[batteryOffset + 1];
        var placement = payload[batteryOffset + 4];
        var caseBattery = payload[batteryOffset + 5];
        if (left > 101 || right > 101 || caseBattery > 101 ||
            payload[batteryOffset + 2] > 1 || payload[batteryOffset + 3] > 1 ||
            (placement >> 4) > 4 || (placement & 0x0f) > 4)
            return;

        status = (status.Count + 1, left, right, caseBattery);
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
    }

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
using System.IO;
using System.Threading;

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

    public static void ResetReceiveStream()
    {
        lock (Sync)
        {
            FrameProbe.ResetStream();
            ScheduleSave();
        }
    }

    public static void RecordRx(byte[] frame)
    {
        lock (Sync)
        {
            _chunks++;
            _bytes += frame.Length;
            if (FirstChunkLengths.Count < 16)
                FirstChunkLengths.Add(frame.Length);
            FrameProbe.Append(frame);
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
                BudsOnDiagnostics.ResetReceiveStream();
                BudsOnDiagnostics.Record("Buds On connection requested");
                await macBackend.ConnectAsync(device.MacAddress, uuid, _connectCancelSource.Token,
                    BudsOnDiagnostics.Record, HandleBudsOnDiagnosticRx);
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
    '    private void OnNewDataAvailable(object? sender, byte[] frame)\n',
    '''    private static void HandleBudsOnDiagnosticRx(byte[] frame)
    {
        BudsOnDiagnostics.RecordRx(frame);
    }

    private void OnNewDataAvailable(object? sender, byte[] frame)
''')
replace_once(bluetooth,
    '        /* Discard data if not properly registered */\n',
    '''        if (CurrentModel == Models.BudsOn)
        {
            HandleBudsOnDiagnosticRx(frame);
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
    '        mRFCOMMChannel = tempRFCOMMChannel;\n        _diagnosticChannel = diagnostic != nullptr;\n')
replace_once(native + 'src/Bluetooth.mm',
    '        mRFCOMMChannel = nil;\n',
    '        mRFCOMMChannel = nil;\n        _diagnosticChannel = false;\n')
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
                                   ToolTip.Tip="Headset battery level reported by macOS"
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
    'using GalaxyBudsClient.Platform;\nusing GalaxyBudsClient.Model.Constants;\nusing ReactiveUI;\n')
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
    '''        BluetoothImpl.Instance.Device.DeviceChanged += (_, _) =>
            Dispatcher.UIThread.Post(() =>
            {
                BudsOnBatteryText = null;
                BudsOnDiagnostics.SetMacBattery(null);
            });
        SppMessageReceiver.Instance.StatusUpdate += OnStatusUpdateReceived;
''')
replace_once(home_vm,
    '            await Task.Delay(1000);\n            await BluetoothImpl.Instance.SendRequestAsync(MsgIds.DEBUG_GET_ALL_DATA);\n',
    '''            await Task.Delay(1000);
            if (BluetoothImpl.Instance.CurrentModel != Models.BudsOn)
                await BluetoothImpl.Instance.SendRequestAsync(MsgIds.DEBUG_GET_ALL_DATA);
''')
replace_once(home_vm,
    '    public override void OnNavigatedTo() => _refreshTimer.Start();\n',
    '''    private async Task RefreshBudsOnBatteryAsync()
    {
        var bluetooth = BluetoothImpl.Instance;
        var device = bluetooth.Device.Current;
        if (_readingBudsOnBattery || !PlatformUtils.IsOSX || device?.Model != Models.BudsOn
            || string.IsNullOrWhiteSpace(device.Name))
            return;

        var name = device.Name;
        _readingBudsOnBattery = true;
        try
        {
            var battery = await BudsOnMacBattery.ReadAsync(name, CancellationToken.None);
            if (!ReferenceEquals(bluetooth.Device.Current, device) || device.Name != name)
                return;

            BudsOnBatteryText = battery is int percentage ? $"Battery {percentage}%" : null;
            BudsOnDiagnostics.SetMacBattery(battery);
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

print('Done. Buds On connection diagnostics enabled. All Buds On protocol writes are blocked.')
