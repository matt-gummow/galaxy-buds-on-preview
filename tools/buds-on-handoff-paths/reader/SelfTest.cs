using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
internal static class SelfTest
{
    public static int Run()
    {
        using var fixture = Assembly.GetExecutingAssembly().GetManifestResourceStream("BudsOnFixture.dll");
        if (fixture == null) throw new InvalidDataException("Missing test fixture.");
        using var result = new StringWriter();
        if (Program.Inspect(fixture, result) != 0) return 1;
        var lines = result.ToString().Split('\n');
        bool Found(string s) => lines.Any(l => l.Contains("async body") && l.Contains(s, StringComparison.Ordinal));
        if (!lines.Any(l => l.Contains("explicitly switch-named accessor") && l.Contains("get_BudsAutoSwitch") &&
            l.Contains("delegate target reference") && l.Contains("BluetoothLEAdvertisementWatcher.Stop")) ||
            !Found("BLE watcher / BluetoothLEAdvertisementWatcher.Start") || !Found("Buds formatter native import / FixtureOnly") ||
            !Found("host-version name / DeviceInfo.GetMdeVersion") || !Found("ldstr / exact SM-U600 literal") || lines.Any(l => l.Contains("BluetoothLEAdvertisementPublisher.Start") ||
            l.Contains("ldstr / exact Galaxy Buds On literal") || l.Contains("ldstr / exact MDE_VERSION literal")))
        {
            Console.Error.WriteLine(result.ToString());
            Console.Error.WriteLine("Fixture mismatch.");
            return 1;
        }
        // Corrupt only the method-body headers. The declarations still exist in the
        // managed metadata, so their names should survive without any claimed paths.
        fixture.Position = 0;
        using var corrupted = new MemoryStream();
        fixture.CopyTo(corrupted);
        corrupted.Position = 0;
        using (var pe = new PEReader(corrupted, PEStreamOptions.LeaveOpen))
        {
            var m = pe.GetMetadataReader();
            var offsets = new HashSet<int>();
            foreach (var method in m.MethodDefinitions)
            {
                int rva = m.GetMethodDefinition(method).RelativeVirtualAddress;
                if (rva == 0) continue;
                var section = pe.PEHeaders.SectionHeaders.Single(s => rva >= s.VirtualAddress &&
                    rva - s.VirtualAddress < s.SizeOfRawData);
                offsets.Add(rva - section.VirtualAddress + section.PointerToRawData);
            }
            foreach (var offset in offsets) corrupted.GetBuffer()[offset] = 0;
        }
        corrupted.Position = 0;
        using var inventory = new StringWriter();
        if (Program.Inspect(corrupted, inventory) != 21 ||
            !inventory.ToString().StartsWith("Managed method inventory only." + Environment.NewLine, StringComparison.Ordinal) ||
            !inventory.ToString().Contains("formatter import declaration / FixtureOnly") ||
            !inventory.ToString().Contains("TransferPreferences.get_BudsAutoSwitch") ||
            inventory.ToString().Contains(" -> ") || !inventory.ToString().TrimEnd().EndsWith("Inventory complete.", StringComparison.Ordinal))
            return 1;

        using var malformed = new MemoryStream(new byte[256]);
        using var error = new StringWriter();
        if (Program.Inspect(malformed, error) != 20 || error.ToString().Length != 0) return 1;
        Console.WriteLine("Static fixture passed for async, generic calls, imports, literals and decoys. Invalid method bodies retain a metadata-only inventory; a non-PE has no report.");
        return 0;
    }
}
