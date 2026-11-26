using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.Eventing.Reader;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;

public sealed class OverlapHciTimeline
{
    private readonly ulong address;
    private readonly DateTimeOffset origin;
    private readonly List<string> lines = new List<string>();
    private int handle = -1, readable, unusable, omitted;
    public OverlapHciTimeline(ulong address, DateTimeOffset origin)
    {
        if (address == 0 || address > 0xffffffffffffUL) throw new ArgumentOutOfRangeException("address");
        this.address = address;
        this.origin = origin;
    }
    private void Mark(DateTimeOffset time, string state)
    {
        if (lines.Count >= 256) { omitted++; return; }
        double seconds = (time - origin).TotalSeconds;
        lines.Add(string.Format(CultureInfo.InvariantCulture, "t={0:F3}s  Book HCI: {1}", seconds, state));
    }
    public void Gap(DateTimeOffset time)
    {
        unusable++;
        if (handle < 0) return;
        Mark(time, "controller coverage interrupted; target handle no longer attributed.");
        handle = -1;
    }
    private static int U16(byte[] b, int i) { return b[i] | (b[i + 1] << 8); }

    public void Event(DateTimeOffset time, byte[] b)
    {
        if (b == null || b.Length < 2 || b[1] != b.Length - 2 ||
            (b[0] == 3 && b.Length != 13) || (b[0] == 5 && b.Length != 6) ||
            (b[0] == 0x2c && b.Length != 19)) { Gap(time); return; }
        readable++;
        if (time < origin) return;
        if ((b[0] == 3 || b[0] == 0x2c) && b[2] == 0)
        {
            ulong peer = 0;
            for (int i = 0; i < 6; i++) peer |= (ulong)b[5+i] << (8*i);
            int next = U16(b, 3);
            if (next >= 0xf00) { Gap(time); return; }
            if (peer == address && b[0] == 3 && b[11] == 1)
            {
                if (handle >= 0) Gap(time);
                handle = next;
                Mark(time, "target classic ACL connected.");
            }
            else if (next == handle) Gap(time);
        }
        else if (b[0] == 5 && b[2] == 0 && U16(b, 3) == handle)
        {
            Mark(time, "target classic ACL disconnected.");
            handle = -1;
        }
        else if ((b[0] == 0x10 && b.Length == 3) ||
            (b[0] == 0x0e && b.Length == 6 && U16(b, 3) == 0x0c03 && b[5] == 0))
            Gap(time);
        else if (b[0] == 0x3e && b.Length >= 6 && b[3] == 0 && U16(b, 4) == handle &&
            (b[2] == 1 || b[2] == 0x0a || b[2] == 0x19 || b[2] == 0x29 || b[2] == 0x2a)) Gap(time);
    }
    public string[] Finish(bool completed)
    {
        var result = new List<string>(lines);
        result.Add(string.Format(CultureInfo.InvariantCulture,
            "Book HCI coverage: {0} readable controller events, {1} gaps, {2} omitted transitions, scan {3}.",
            readable, unusable, omitted, completed ? "complete" : "partial"));
        result.Add("Book HCI attributes classic links only after a captured target connection. A missing transition does not establish continuous connectivity.");
        return result.ToArray();
    }
}

public static class OverlapHci
{
    [DllImport("bthprops.cpl", ExactSpelling = true, SetLastError = true)]
    private static extern IntPtr BluetoothFindFirstRadio(ref uint size, out IntPtr radio);
    [DllImport("bthprops.cpl", ExactSpelling = true, SetLastError = true)]
    private static extern int BluetoothFindNextRadio(IntPtr find, out IntPtr radio);
    [DllImport("bthprops.cpl", ExactSpelling = true)]
    private static extern int BluetoothFindRadioClose(IntPtr find);
    [DllImport("kernel32.dll", ExactSpelling = true)]
    private static extern int CloseHandle(IntPtr handle);
    public static bool SingleRadio()
    {
        uint size = 4;
        IntPtr radio;
        IntPtr find = BluetoothFindFirstRadio(ref size, out radio);
        if (find == IntPtr.Zero) return false;
        try
        {
            CloseHandle(radio);
            if (BluetoothFindNextRadio(find, out radio) != 0) { CloseHandle(radio); return false; }
            return Marshal.GetLastWin32Error() == 259;
        }
        finally { BluetoothFindRadioClose(find); }
    }

    // Arguments are generated locally: instance is a GUID, paths are system/application-generated.
    public static int Wpr(string executable, string arguments)
    {
        using (var process = Process.Start(new ProcessStartInfo(executable, arguments) {
            UseShellExecute = false, CreateNoWindow = true }))
        {
            process.WaitForExit();
            return process.ExitCode;
        }
    }
    public static byte[] DecodePacket(object value)
    {
        var bytes = value as byte[];
        if (bytes != null) return bytes.Length <= 257 ? bytes : null;
        var hex = value as string;
        if (hex == null || hex.Length > 1036) return null;
        hex = Regex.Replace(hex, @"\s+", "");
        if (hex.Length > 514 || (hex.Length & 1) != 0) return null;
        bytes = new byte[hex.Length / 2];
        for (int i = 0; i < bytes.Length; i++)
            if (!byte.TryParse(hex.Substring(2*i, 2), NumberStyles.AllowHexSpecifier,
                CultureInfo.InvariantCulture, out bytes[i])) return null;
        return bytes;
    }
    public static string[] Scan(string path, ulong address, DateTimeOffset origin)
    {
        var trace = new OverlapHciTimeline(address, origin);
        const string query = "*[System[Provider[@Name='Microsoft-Windows-BTH-BTHPORT']]]";
        const string field = "Event/EventData/Data[@Name='";
        bool complete = false;
        try
        {
            using (var reader = new EventLogReader(new EventLogQuery(path, PathType.FilePath, query)))
            using (var type = new EventLogPropertySelector(new[] {field + "BIP_Type']"}))
            using (var data = new EventLogPropertySelector(new[] {field + "BIP_DataLen']", field + "BIP_Data']"}))
            {
                EventRecord record;
                while ((record = reader.ReadEvent()) != null)
                    using (record)
                    {
                        if (record.Id != 402 && record.Id != 403 &&
                            (record.Keywords.GetValueOrDefault() & long.MinValue) == 0) continue;
                        var native = record as EventLogRecord;
                        if (native == null) continue;
                        var time = record.TimeCreated;
                        var stamp = time.HasValue ? new DateTimeOffset(time.Value).ToUniversalTime() : origin;
                        var fields = native.GetPropertyValues(type);
                        if (fields.Count == 0 || fields[0] == null)
                        {
                            if (record.Id == 402) trace.Gap(stamp);
                            continue;
                        }
                        if (Convert.ToInt32(fields[0], CultureInfo.InvariantCulture) != 2) continue;
                        var body = native.GetPropertyValues(data);
                        byte[] packet = body.Count == 2 ? DecodePacket(body[1]) : null;
                        if (!time.HasValue || packet == null || body[0] == null ||
                            Convert.ToInt64(body[0], CultureInfo.InvariantCulture) != packet.Length)
                            trace.Gap(stamp);
                        else trace.Event(stamp, packet);
                    }
            }
            complete = true;
        }
        catch (EventLogException) { }
        catch (UnauthorizedAccessException) { }
        catch (System.IO.IOException) { }
        catch (InvalidCastException) { }
        catch (FormatException) { }
        catch (OverflowException) { }
        return trace.Finish(complete);
    }
}
