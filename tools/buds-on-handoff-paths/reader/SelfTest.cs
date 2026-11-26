using System.Reflection;
internal static class SelfTest
{
    public static int Run()
    {
        using var fixture = Assembly.GetExecutingAssembly().GetManifestResourceStream("BudsOnFixture.dll");
        if (fixture == null) throw new InvalidDataException("Missing test fixture.");
        using var scanner = new CallsiteReader(fixture);
        using var result = new StringWriter();
        scanner.Write(result);
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
        Console.WriteLine("Static fixture passed for async and same-assembly generic paths, native imports, exact literals, unrelated and accessor decoys.");
        return 0;
    }
}
