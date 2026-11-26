using System;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Text;

public static class TestReader
{
    private static void Add(ZipArchive z, string name, string text, Encoding encoding)
    {
        using (Stream s = z.CreateEntry(name).Open())
        using (var w = new StreamWriter(s, encoding)) w.Write(text);
    }
    private static void Need(string report, string match)
    {
        if (!report.Contains(match)) throw new Exception("Missing expected summary: " + match + "\n" + report);
    }
    public static int Main()
    {
        InstalledConnectEvidenceTests.Run();
        using (var writer = new StringWriter())
        {
            ConnectLogReader.InstalledVersions("4.6.1327.0", "SECRET_PATH", writer);
            Need(writer.ToString(), "Galaxy Connect package: 4.6.1327.0");
            Need(writer.ToString(), "Settings 1.5 family: unknown for the checked package family");
            if (writer.ToString().Contains("SECRET_PATH")) throw new Exception("Untrusted version reached report.");
        }
        var local = TimeZoneInfo.CreateCustomTimeZone("test", TimeSpan.FromHours(-7), "test", "test");
        using (var ms = new MemoryStream())
        {
            using (var z = new ZipArchive(ms, ZipArchiveMode.Create, true))
            {
                Add(z,"PRIVATE/SECRET_PATH/User.log",
                    "2026-11-26T02:02:57.7359100Z EasyConnect2\n" + // 1 tick before start
                    "2026-11-26T02:02:58Z EasyConnect2 SM-U600 privateID=SECRET_PHONE\n" +
                    "2026-11-25 19:03:10.123-0700 Auto Switch SM-U600N\n" +
                    "2026-11-26T02:06:57.8359101Z MDE_VERSION\n" + // inclusive boundary
                    "2026-11-26T02:06:57.8359102Z MDE_VERSION\n" +
                    "2026-11-26 02:04:00 UTC Auto Switch Galaxy Buds4 Pro\n" + // ignore wrong model
                    "2026-11-26T02:03:30Z do not count EasyConnect2Wrong\n" +
                    "2026-11-26T02:04:00 BudsBLEAdvertisementBackgroundTask SM-U600\n" +
                    "2026-11-25 19:05:00 AUTO_SWITCH_AUDIO_OUTPUT\n" +
                    "SM-U600 - untimed marker\n" +
                    "private: 2026-11-26T02:03:00Z AutoSwitchBuds\n", Encoding.UTF8);
                Add(z, "PERSONAL/Documents.binary", "2026-11-26T02:03:00Z Auto Switch Galaxy Buds On", Encoding.UTF8);
                using (var nested = new MemoryStream())
                {
                    using (var inner = new ZipArchive(nested, ZipArchiveMode.Create, true))
                        Add(inner, "hidden.log.1",
                            "[2026-11-26 02:03:04Z] ModuleEasyConnect Galaxy Buds On SECRET_ADDRESS\n", Encoding.Unicode);
                    using (var outStream = z.CreateEntry("inside.zip").Open())
                    { nested.Position = 0; nested.CopyTo(outStream); }
                }
            }
            ms.Position = 0;
            using (var output = new StringWriter(CultureInfo.InvariantCulture))
            {
                ConnectLogReader.Summarize(ms, local, output);
                string report = output.ToString();
                Need(report, "Readable text entries: 2. Skipped or unreadable entries: 1.");
                Need(report, "explicit UTC/offset: 6. Possible lines with unspecified timezone: 2.");
                Need(report, "no usable timestamp: 2.");
                Need(report, "verified clock | EasyConnect | Buds On named on same line | 2 line(s)");
                Need(report, "verified clock | Auto Switch | Buds On named on same line | 1 line(s)");
                Need(report, "verified clock | Host version (MDE_VERSION) | model unspecified | 1 line(s)");
                Need(report, "if unmarked clock was UTC | Buds BLE advertisement task | Buds On named on same line | 1 line(s)");
                Need(report, "if unmarked clock used Book local time | Audio output switch | model unspecified | 1 line(s)");
                foreach (string secret in new[] {"SECRET","PERSONAL","privateID","SM-U600N","hidden.log","19:03:10"})
                    if (report.Contains(secret)) throw new Exception("Private or raw value escaped into output.");
            }
        }
        using (var ms = new MemoryStream())
        {
            using (var zip = new ZipArchive(ms, ZipArchiveMode.Create, true)) Add(zip,"archive.log","unknown",Encoding.UTF8);
            ms.Position = 0;
            using (var output = new StringWriter())
            {
                ConnectLogReader.Summarize(ms, local, output);
                Need(output.ToString(), "No matching dated vocabulary");
            }
        }
        Console.WriteLine("Galaxy Connect archive, date correlation, classifier and privacy tests passed.");
        return 0;
    }
}
