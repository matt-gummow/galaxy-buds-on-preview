using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;

public static class AnalyzeSavedTrace
{
    private const string Header = "Galaxy Buds On | Galaxy Book call-switch test";
    private const string Prefix = "Capture start UTC ";
    private const string ReportName = "Buds-On-report.txt";
    private const string EtlName = "Bluetooth-private.etl";

    private sealed class Capture
    {
        public string Folder;
        public string Etl;
        public DateTimeOffset Origin;
        public long Size;
    }

    private static Capture ReadCapture(string folder)
    {
        string report = Path.Combine(folder, ReportName);
        string etl = Path.Combine(folder, EtlName);
        if (!File.Exists(report) || !File.Exists(etl)) return null;
        DateTimeOffset origin;
        using (StreamReader reader = File.OpenText(report))
        {
            if (reader.ReadLine() != Header) return null;
            string start = reader.ReadLine();
            if (start == null || !start.StartsWith(Prefix, StringComparison.Ordinal)) return null;
            // WPR launcher writes DateTime.UtcNow with the standard round-trip format.
            if (!DateTimeOffset.TryParseExact(start.Substring(Prefix.Length),
                "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out origin)) return null;
        }
        long size = new FileInfo(etl).Length;
        return size > 0 ? new Capture { Folder = folder, Etl = etl, Origin = origin, Size = size } : null;
    }

    private static Capture FindCapture(string dropped)
    {
        if (!String.IsNullOrWhiteSpace(dropped))
        {
            string path = Path.GetFullPath(dropped);
            if (Directory.Exists(path)) return ReadCapture(path);
            string name = Path.GetFileName(path);
            if (!File.Exists(path) || (!String.Equals(name, ReportName, StringComparison.OrdinalIgnoreCase)
                && !String.Equals(name, EtlName, StringComparison.OrdinalIgnoreCase))) return null;
            return ReadCapture(Path.GetDirectoryName(path));
        }
        string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BudsOnTrace");
        var matches = new List<Capture>();
        if (Directory.Exists(root))
        {
            foreach (string dir in Directory.GetDirectories(root))
            {
                try
                {
                    Capture result = ReadCapture(dir);
                    if (result != null) matches.Add(result);
                }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }
            }
        }
        if (matches.Count == 0) return null;
        if (matches.Count == 1) return matches[0];
        matches.Sort(delegate(Capture a, Capture b)
        {
            int order = b.Origin.CompareTo(a.Origin);
            return order != 0 ? order : String.Compare(a.Folder, b.Folder, StringComparison.Ordinal);
        });
        Console.WriteLine("Select the call recording. Times below use the Book's local time.");
        for (int i = 0; i < matches.Count; i++)
        {
            Capture trace = matches[i];
            Console.WriteLine("{0}. {1}   ({2:F1} MB)", i + 1,
                trace.Origin.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss zzz", CultureInfo.InvariantCulture),
                trace.Size / 1048576.0);
        }
        while (true)
        {
            Console.Write("Number, or Q to quit: ");
            string raw = Console.ReadLine();
            if (raw == null || raw.Trim().Equals("Q", StringComparison.OrdinalIgnoreCase))
                throw new OperationCanceledException();
            int n;
            if (Int32.TryParse(raw, out n) && n >= 1 && n <= matches.Count) return matches[n-1];
        }
    }

    public static int Run(string dropped)
    {
        try
        {
            Capture capture = FindCapture(dropped);
            if (capture == null)
            {
                Console.WriteLine("No matching Buds-On-report.txt and Bluetooth-private.etl pair was found.");
                Console.WriteLine("Drag the original report, ETL, or their folder onto Read-Buds-Settings.cmd.");
                return 1;
            }
            string output = Path.Combine(capture.Folder, "Buds-On-audio-handoff-" + Guid.NewGuid().ToString("N").Substring(0,8) + ".txt");
            Console.WriteLine("Reading the saved Galaxy Book trace. This can take a minute.");
            using (StreamWriter writer = new StreamWriter(new FileStream(output, FileMode.CreateNew, FileAccess.Write, FileShare.None)))
            {
                writer.WriteLine("Galaxy Buds On | Galaxy Book audio handoff check");
                writer.WriteLine("Times are seconds from the original report start. Only the Book's Bluetooth link was captured. The Fold's simultaneous audio connection cannot be determined from this file.");
                writer.WriteLine("This check looks for a Book-to-Buds request matching a published Buds4 Pro audio-handoff format. It also reports audio channels, version messages and transport announcements when captured. A matching request cannot establish that it caused a switch. Other message formats, missing packets and low-energy connections can fall outside this scan.");
                try { SavedBudsReader.Scan(capture.Etl, capture.Origin, writer); }
                catch (Exception) { writer.WriteLine("Reading stopped. Any displayed matches form a partial timeline."); }
            }
            Console.WriteLine("Share the selected Buds-On-audio-handoff text file in chat. Keep the original ETL local.");
            try { Process.Start("explorer.exe", "/select,\"" + output + "\""); }
            catch (System.ComponentModel.Win32Exception) { Console.WriteLine("The summary is in the same folder as the original report."); }
            return 0;
        }
        catch (OperationCanceledException) { return 1; }
        catch (Exception) { Console.WriteLine("Could not open the trace folder or save the summary."); return 1; }
    }
}
