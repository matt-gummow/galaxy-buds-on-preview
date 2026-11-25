#!/usr/bin/env python3
"""Conservative Buds On recognition + opt-in RX diagnostics patch.

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
    '    private void OnNewDataAvailable(object? sender, byte[] frame)\n    {\n',
    '    private void OnNewDataAvailable(object? sender, byte[] frame)\n    {\n'
    '        // Raw RX only when explicitly opted in. Logs can contain device identifiers.\n'
    '        if (CurrentModel == Models.BudsOn &&\n'
    '            Environment.GetEnvironmentVariable("GALAXYBUDS_ON_LOG_RAW") == "1")\n'
    '        {\n'
    '            Log.Information("Buds On raw RX ({Length} bytes): {Hex}",\n'
    '                frame.Length, Convert.ToHexString(frame));\n'
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
print('Done. Buds On may be recognized; multipoint and write commands are intentionally disabled.')
