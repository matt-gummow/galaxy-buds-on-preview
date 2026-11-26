using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;

// Inspect only the historical Book recording window; output vocabulary and numbers are fixed.
public static class ConnectLogReader
{
    internal static readonly DateTimeOffset Start = new DateTimeOffset(2026, 11, 26, 2, 2, 57, TimeSpan.Zero).AddTicks(7359101);
    private static readonly DateTimeOffset End = Start.AddSeconds(240.1);
    private const long MiB = 1024L * 1024L;
    private const int MaxEntries = 4096;
    private static readonly string[] Labels = { "SM-U600 / Buds On", "Auto Switch", "Buds BLE advertisement task",
        "EasyConnect", "Host version (MDE_VERSION)", "Audio output switch", "Profile control" };
    private static readonly Regex[] Markers = { Token("SM[-_]?U600(?:N[A-Z0-9]*)?|Galaxy[ _-]?Buds[ _-]+On"),
        Token("Auto[ _.-]?Switch(?:[ _.-]?(?:Buds|Audio[ _.-]?Output))?|Buds[ _.-]?Auto[ _.-]?Switch"),
        Token("BudsBLEAdvertisementBackgroundTask"), Token("EasyConnect2|ModuleEasyConnect|EasyConnectLib"),
        Token("MDE_VERSION"), Token("AUTO_SWITCH_AUDIO_(?:OUTPUT|OUPUT)"), Token("PROFILE_CONTROL") };
    private static readonly Regex OtherModel = Token("SM[-_]?R[0-9]{3}[A-Z0-9]*|Galaxy[ _-]?Buds[ _-]?(?:[234](?:[ _-]?Pro)?|Pro|Live|FE|Core|Plus)");
    private static readonly Regex Stamp = new Regex(
        @"^\s*(?:[\[\(]\s*|\{\s*""(?:timestamp|time|datetime)""\s*:\s*"")?(?<d>20\d\d-\d\d-\d\d)[ T](?<t>\d\d:\d\d:\d\d(?:[.,]\d{1,7})?)(?<z>Z|[+-]\d\d:?\d\d|[ \t]+UTC)?(?=$|[\s\]\)"",;|])",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
    private static Regex Token(string pattern)
    {
        return new Regex(@"(?<![A-Za-z0-9_])(?:" + pattern + @")(?![A-Za-z0-9_])",
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
    }
    private sealed class Bucket { public int N; public double First = Double.MaxValue; public double Last = -1; }
    private sealed class State
    {
        public readonly Dictionary<int,Bucket> Counts = new Dictionary<int,Bucket>();
        public int Visited, TextFiles, Skipped, InWindow, LocalCandidates, NoTimeMarkers;
        public bool Limit;
        public long Bytes;
    }
    // 0: explicit offset, 1: unzoned only under UTC, 2: unzoned only under Book local,
    // 3: unzoned under either. A local clock never becomes an offset-verified timestamp.
    private static bool InRange(DateTimeOffset point) { return point >= Start && point <= End; }
    private static int Window(string line, TimeZoneInfo local, out double sec)
    {
        sec = 0;
        Match m = Stamp.Match(line);
        if (!m.Success) return -2;
        string date = m.Groups["d"].Value + "T" + m.Groups["t"].Value.Replace(',', '.');
        string zone = m.Groups["z"].Value.Trim();
        if (zone.Length != 0)
        {
            if (zone.Equals("UTC", StringComparison.OrdinalIgnoreCase) || zone.Equals("Z", StringComparison.OrdinalIgnoreCase)) zone = "+00:00";
            if (zone.Length == 5 && zone[3] != ':') zone = zone.Insert(3, ":");
            DateTimeOffset instant;
            if (!DateTimeOffset.TryParseExact(date + zone, new[] {"yyyy-MM-dd'T'HH:mm:sszzz", "yyyy-MM-dd'T'HH:mm:ss.FFFFFFFzzz"},
                CultureInfo.InvariantCulture, DateTimeStyles.None, out instant)) return -2;
            if (!InRange(instant)) return -1;
            sec = (instant - Start).TotalSeconds;
            return 0;
        }
        DateTime wall;
        if (!DateTime.TryParseExact(date, new[] {"yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd'T'HH:mm:ss.FFFFFFF"},
            CultureInfo.InvariantCulture, DateTimeStyles.None, out wall)) return -2;
        bool utcMatch = InRange(new DateTimeOffset(wall, TimeSpan.Zero)), localMatch = false;
        if (!local.IsInvalidTime(wall))
        {
            TimeSpan[] offsets = local.IsAmbiguousTime(wall) ? local.GetAmbiguousTimeOffsets(wall) : new[] { local.GetUtcOffset(wall) };
            foreach (TimeSpan offset in offsets)
                if (InRange(new DateTimeOffset(wall, offset))) localMatch = true;
        }
        if (utcMatch && localMatch) return 3;
        if (utcMatch) return 1;
        return localMatch ? 2 : -1;
    }
    private static void Line(string line, TimeZoneInfo local, State s)
    {
        if (line.Length > 8192) { s.Limit = true; return; }
        double sec;
        int clock = Window(line, local, out sec);
        if (clock == -1) return;
        if (clock == 0) s.InWindow++;
        if (clock > 0) s.LocalCandidates++;
        if (OtherModel.IsMatch(line)) return; // mixed-model records are ambiguous, too
        bool model = Markers[0].IsMatch(line);
        bool has = false;
        for (int i = 0; i < Labels.Length; i++)
        {
            if (!(i == 0 ? model : Markers[i].IsMatch(line))) continue;
            has = true;
            if (clock < 0) break;
            int key = (clock * Labels.Length + i) * 2 + (model ? 1 : 0);
            Bucket b;
            if (!s.Counts.TryGetValue(key, out b)) { b = new Bucket(); s.Counts.Add(key, b); }
            b.N++;
            if (clock == 0) { b.First = Math.Min(b.First, sec); b.Last = Math.Max(b.Last, sec); }
        }
        if (clock == -2 && has) s.NoTimeMarkers++;
    }
    private static bool IsText(string name)
    {
        return Regex.IsMatch(name, @"\.(?:log|txt|json|jsonl|ndjson|csv|trace)(?:\.\d{1,3})?$",
            RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
    }
    private static bool Decode(byte[] data, int n, out string text)
    {
        text = null;
        int skip = 0;
        Encoding enc = new UTF8Encoding(false, true);
        if (n >= 2 && data[0] == 255 && data[1] == 254) { enc = new UnicodeEncoding(false, true, true); skip = 2; }
        else if (n >= 2 && data[0] == 254 && data[1] == 255) { enc = new UnicodeEncoding(true, true, true); skip = 2; }
        else if (n >= 3 && data[0] == 239 && data[1] == 187 && data[2] == 191) skip = 3;
        try { text = enc.GetString(data, skip, n - skip); }
        catch (DecoderFallbackException) { return false; }
        return text.IndexOf('\0') < 0;
    }
    private static void Archive(Stream input, int depth, TimeZoneInfo local, State s)
    {
        using (var zip = new ZipArchive(input, ZipArchiveMode.Read, true))
        {
            foreach (ZipArchiveEntry e in zip.Entries)
            {
                if (++s.Visited > MaxEntries || s.Bytes >= 128 * MiB) { s.Limit = true; return; }
                if (e.Name.Length == 0) continue;
                bool nested = e.Name.EndsWith(".zip", StringComparison.OrdinalIgnoreCase);
                if ((!IsText(e.Name) && !nested) || (nested && depth != 0)) { s.Skipped++; continue; }
                if (e.Length > (nested ? 32 : 12) * MiB || e.Length > 128 * MiB - s.Bytes) { s.Skipped++; s.Limit = true; continue; }
                try
                {
                    int n = checked((int)e.Length), used = 0;
                    byte[] data = new byte[n];
                    s.Bytes += n;
                    using (Stream source = e.Open())
                    {
                        while (used < n)
                        {
                            int read = source.Read(data, used, n - used);
                            if (read == 0) break;
                            used += read;
                        }
                        if (used != n || source.ReadByte() != -1) { s.Skipped++; continue; }
                    }
                    if (nested) { using (var inner = new MemoryStream(data, false)) Archive(inner, depth + 1, local, s); continue; }
                    string body;
                    if (!Decode(data, n, out body)) { s.Skipped++; continue; }
                    s.TextFiles++;
                    using (var reader = new StringReader(body))
                    {
                        string line;
                        while ((line = reader.ReadLine()) != null) Line(line, local, s);
                    }
                }
                catch (InvalidDataException) { s.Skipped++; }
                catch (IOException) { s.Skipped++; }
                catch (NotSupportedException) { s.Skipped++; }
            }
        }
    }
    public static void Summarize(Stream archive, TimeZoneInfo local, TextWriter output)
    {
        State s = new State();
        Archive(archive, 0, local, s);
        output.WriteLine("Galaxy Connect | historical Galaxy Book handoff check");
        output.WriteLine("Window UTC: 2026-11-26 02:02:57.7359101 to 02:06:57.8359101.");
        output.WriteLine("Readable text entries: {0}. Skipped or unreadable entries: {1}. Scan limit reached: {2}.", s.TextFiles, s.Skipped, s.Limit ? "yes" : "no");
        output.WriteLine("Lines in window with explicit UTC/offset: {0}. Possible lines with unspecified timezone: {1}.", s.InWindow, s.LocalCandidates);
        output.WriteLine("Lines with known terms and no usable timestamp: {0}. These cannot be tied to the test.", s.NoTimeMarkers);
        string[] basis = { "verified clock", "if unmarked clock was UTC", "if unmarked clock used Book local time", "if unmarked clock was UTC or Book local time" };
        for (int clock = 0; clock < 4; clock++)
        {
            for (int i = 0; i < Labels.Length; i++)
            {
                for (int model = 0; model < 2; model++)
                {
                    Bucket b;
                    if (!s.Counts.TryGetValue((clock * Labels.Length + i) * 2 + model, out b)) continue;
                    string seconds = clock == 0 ? String.Format(CultureInfo.InvariantCulture, ", first {0:F2}s, last {1:F2}s", b.First, b.Last) : "";
                    output.WriteLine("{0} | {1} | {2} | {3} line(s){4}", basis[clock], Labels[i],
                        model != 0 ? "Buds On named on same line" : "model unspecified", b.N, seconds);
                }
            }
        }
        if (s.Counts.Count == 0) output.WriteLine("No matching dated vocabulary in this window or under either candidate timezone.");
        output.WriteLine("A term on a line establishes only a textual reference. It cannot establish transmission, audio movement or a held connection. Coverage depends on retained readable entries and recognized timestamp/marker formats.");
    }
    private static string Choose()
    {
        Console.WriteLine("Press Enter to collect existing Samsung logs, or type E to select a ZIP you already have. Q exits.");
        string choice = Console.ReadLine();
        if (choice == null || choice.Trim().Equals("Q", StringComparison.OrdinalIgnoreCase)) return null;
        if (choice.Trim().Length == 0)
        {
            try { Process.Start(new ProcessStartInfo("samsung-mcfcore://collectlogs") { UseShellExecute = true }); }
            catch (System.ComponentModel.Win32Exception) { Console.WriteLine("Samsung's collector could not open. You can still select an existing ZIP."); }
            Console.WriteLine("When Samsung shows the collected ZIP in Explorer, press Enter to select it. You can also copy and paste its full path in the next dialog.");
            if (Console.ReadLine() == null) return null;
        }
        using (var picker = new OpenFileDialog())
        {
            picker.Title = "Select the GalaxyConnectLogs ZIP from Samsung";
            picker.Filter = "Galaxy Connect archives (*.zip)|*.zip";
            picker.CheckFileExists = true;
            return picker.ShowDialog() == DialogResult.OK ? picker.FileName : null;
        }
    }
    public static int Run(string inputZip)
    {
        try
        {
            string path = String.IsNullOrWhiteSpace(inputZip) ? Choose() : inputZip;
            if (path == null) return 0;
            path = Path.GetFullPath(path);
            var desk = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            if (String.IsNullOrWhiteSpace(desk)) throw new IOException();
            string report = Path.Combine(desk, "Galaxy-Connect-handoff-" + Guid.NewGuid().ToString("N").Substring(0,8) + ".txt");
            using (var input = File.OpenRead(path))
            using (var text = new StringWriter(CultureInfo.InvariantCulture))
            {
                if (input.Length > 512 * MiB) { Console.WriteLine("This ZIP exceeds the 512 MiB archive limit."); return 1; }
                Summarize(input, TimeZoneInfo.Local, text);
                using (var writer = new StreamWriter(new FileStream(report, FileMode.CreateNew, FileAccess.Write, FileShare.None)))
                    writer.Write(text.ToString());
            }
            Console.WriteLine("The summary is on your Desktop. Share only the selected Galaxy-Connect-handoff text file.");
            try { Process.Start("explorer.exe", "/select,\"" + report + "\""); } catch (System.ComponentModel.Win32Exception) { }
            return 0;
        }
        catch (Exception) { Console.WriteLine("Could not read the archive or write the report. Confirm the selected ZIP can be opened in Windows and the Desktop is writable."); return 1; }
    }
}
