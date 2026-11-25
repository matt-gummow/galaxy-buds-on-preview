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
    private static readonly Timer ReportTimer = new(_ => SaveReport());
    private static bool _savePending;
    private static long _chunks;
    private static long _bytes;

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

    public static void RecordRx(int bytes)
    {
        lock (Sync)
        {
            _chunks++;
            _bytes += bytes;
            if (FirstChunkLengths.Count < 16)
                FirstChunkLengths.Add(bytes);
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
            lines.Add($"Received RFCOMM chunks: {_chunks} ({_bytes} bytes)");
            if (FirstChunkLengths.Count > 0)
                lines.Add($"First chunk sizes: {string.Join(", ", FirstChunkLengths)}");
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
        BudsOnDiagnostics.RecordRx(frame.Length);
        if (Environment.GetEnvironmentVariable("GALAXYBUDS_ON_LOG_RAW") == "1")
        {
            Log.Information("Buds On raw RX ({Length} bytes): {Hex}",
                frame.Length, Convert.ToHexString(frame));
        }
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

print('Done. Buds On connection diagnostics enabled. All Buds On protocol writes are blocked.')
