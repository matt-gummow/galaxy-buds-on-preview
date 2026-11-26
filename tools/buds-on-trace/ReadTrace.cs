using System;
using System.Collections.Generic;
using System.Diagnostics.Eventing.Reader;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Security;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Win32;

public static class SavedBudsReader
{
    private static readonly Regex TargetName = new Regex(@"\b(?:Buds\s+On|SM-U600)\b",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    [StructLayout(LayoutKind.Sequential)]
    private struct Search
    {
        public uint Size;
        public int Authenticated, Remembered, Unknown, Connected, IssueInquiry;
        public byte Timeout;
        public IntPtr Radio;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct SystemTime
    {
        public ushort Year, Month, Weekday, Day, Hour, Minute, Second, Milliseconds;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct Device
    {
        public uint Size;
        public ulong Address;
        public uint ClassOfDevice;
        public int Connected, Remembered, Authenticated;
        public SystemTime LastSeen, LastUsed;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 248)]
        public string Name;
    }

    [DllImport("bthprops.cpl", ExactSpelling = true, SetLastError = true)]
    private static extern IntPtr BluetoothFindFirstDevice(ref Search search, ref Device device);
    [DllImport("bthprops.cpl", ExactSpelling = true, SetLastError = true)]
    private static extern int BluetoothFindNextDevice(IntPtr find, ref Device device);
    [DllImport("bthprops.cpl", ExactSpelling = true)]
    private static extern int BluetoothFindDeviceClose(IntPtr find);

    // Read the same classic cache used by the recording. No device inquiry or connection.
    private static HashSet<ulong> ClassicTargets()
    {
        var matches = new HashSet<ulong>();
        Search search = new Search { Size = (uint)Marshal.SizeOf(typeof(Search)),
            Authenticated = 1, Remembered = 1, Connected = 1, IssueInquiry = 0 };
        uint size = (uint)Marshal.SizeOf(typeof(Device));
        Device device = new Device { Size = size };
        IntPtr find = BluetoothFindFirstDevice(ref search, ref device);
        if (find == IntPtr.Zero) return matches;
        try
        {
            do
            {
                if (device.Address != 0 && (device.Remembered != 0 || device.Authenticated != 0 || device.Connected != 0)
                    && HasTargetName(device.Name)) matches.Add(device.Address);
                device = new Device { Size = size };
            } while (BluetoothFindNextDevice(find, ref device) != 0);
            // An incomplete listing cannot reliably identify one pair; use the registry fallback.
            if (Marshal.GetLastWin32Error() != 259 && matches.Count < 2) matches.Clear();
            return matches;
        }
        finally { BluetoothFindDeviceClose(find); }
    }

    [DllImport("bthprops.cpl", ExactSpelling = true, SetLastError = true)]
    private static extern IntPtr BluetoothFindFirstRadio(ref uint size, out IntPtr radio);
    [DllImport("bthprops.cpl", ExactSpelling = true, SetLastError = true)]
    private static extern int BluetoothFindNextRadio(IntPtr find, out IntPtr radio);
    [DllImport("bthprops.cpl", ExactSpelling = true)]
    private static extern int BluetoothFindRadioClose(IntPtr find);
    [DllImport("kernel32.dll", ExactSpelling = true)]
    private static extern int CloseHandle(IntPtr handle);

    private static int RadioCount()
    {
        uint size = 4; // BLUETOOTH_FIND_RADIO_PARAMS contains a single DWORD.
        IntPtr radio;
        IntPtr find = BluetoothFindFirstRadio(ref size, out radio);
        if (find == IntPtr.Zero) return 0;
        int count = 0;
        try
        {
            do
            {
                CloseHandle(radio);
                count++;
                if (count > 1) return count;
            } while (BluetoothFindNextRadio(find, out radio) != 0);
            return Marshal.GetLastWin32Error() == 259 ? count : -1;
        }
        finally { BluetoothFindRadioClose(find); }
    }

    private static bool HasTargetName(object value)
    {
        string name = value as string;
        if (name != null) return TargetName.IsMatch(name.TrimEnd('\0'));
        byte[] bytes = value as byte[];
        if (bytes == null || bytes.Length < 2) return false;
        if (TargetName.IsMatch(Encoding.UTF8.GetString(bytes).TrimEnd('\0'))) return true;
        return TargetName.IsMatch(Encoding.Unicode.GetString(bytes).TrimEnd('\0'));
    }

    private static void FindTargets(HashSet<ulong> matches, string path, bool enumerated)
    {
        using (RegistryKey root = Registry.LocalMachine.OpenSubKey(path))
        {
            if (root == null) return;
            foreach (string sub in root.GetSubKeyNames())
            {
                if (enumerated && !sub.StartsWith("Dev_", StringComparison.OrdinalIgnoreCase)) continue;
                string hex = enumerated ? sub.Substring(4) : sub;
                ulong addr;
                if (hex.Length != 12 || !ulong.TryParse(hex, NumberStyles.AllowHexSpecifier,
                    CultureInfo.InvariantCulture, out addr) || addr == 0) continue;
                using (RegistryKey device = root.OpenSubKey(sub))
                {
                    if (device == null) continue;
                    if (!enumerated)
                    {
                        if (HasTargetName(device.GetValue("Name"))) matches.Add(addr);
                        continue;
                    }
                    foreach (string id in device.GetSubKeyNames())
                    {
                        using (RegistryKey inst = device.OpenSubKey(id))
                        {
                            if (inst != null && HasTargetName(inst.GetValue("FriendlyName"))) matches.Add(addr);
                        }
                    }
                }
            }
        }
    }

    private static void ReadDeviceCache(HashSet<ulong> matches, string path, bool enumerated)
    {
        try { FindTargets(matches, path, enumerated); }
        catch (UnauthorizedAccessException) { }
        catch (SecurityException) { }
        catch (IOException) { }
    }

    // Windows normally renders BIP_Data as bytes. Some provider manifests
    // expose a hex string instead. The largest HCI ACL packet has a four-byte
    // header and a 16-bit length. Reject malformed content without logging it.
    private static byte[] PacketBytes(object value, int maximum)
    {
        byte[] bytes = value as byte[];
        if (bytes != null) return bytes.Length <= maximum ? bytes : null;
        string hex = value as string;
        if (hex == null || hex.Length > maximum * 4 + 8) return null;
        hex = Regex.Replace(hex, @"\s+", "");
        if ((hex.Length & 1) != 0 || hex.Length / 2 > maximum) return null;
        bytes = new byte[hex.Length / 2];
        for (int i = 0; i < bytes.Length; i++)
        {
            if (!byte.TryParse(hex.Substring(i * 2, 2), NumberStyles.AllowHexSpecifier,
                CultureInfo.InvariantCulture, out bytes[i])) return null;
        }
        return bytes;
    }

    private static int PacketLength(int type, byte[] bytes)
    {
        if (bytes == null) return -1;
        if (type == 1) return bytes.Length >= 3 ? bytes[2] + 3 : -1;
        if (type == 2) return bytes.Length >= 2 ? bytes[1] + 2 : -1;
        return bytes.Length >= 4 ? bytes[2] + (bytes[3] << 8) + 4 : -1;
    }

    private static void Gap(TraceTransport transport, int type, DateTimeOffset time, byte[] bytes)
    {
        if (type == 3 || type == 4)
        {
            // If the HCI length proves truncation, retain the available L2CAP
            // header so a missing audio fragment need not break control traffic.
            // For other corruption retain only the handle and boundary flags.
            if (bytes != null && bytes.Length >= 8 && PacketLength(type, bytes) > bytes.Length)
                transport.Observe(time, type, bytes);
            else
                transport.Observe(time, type, bytes != null && bytes.Length >= 2
                    ? new byte[] { bytes[0], bytes[1] } : null);
        }
        else
        {
            transport.Observe(time, type, null);
        }
    }

    public static void Scan(string etl, DateTimeOffset origin, TextWriter output)
    {
        HashSet<ulong> targets = ClassicTargets();
        if (targets.Count == 0)
        {
            ReadDeviceCache(targets, @"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices", false);
            ReadDeviceCache(targets, @"SYSTEM\CurrentControlSet\Enum\BTHENUM", true);
        }
        if (targets.Count != 1)
        {
            output.WriteLine(targets.Count == 0 ? "The Buds could not be identified in this PC's Bluetooth device cache." :
                "More than one cached device matched Buds On. The trace cannot be attributed to one pair.");
            return;
        }
        if (RadioCount() != 1)
        {
            output.WriteLine("A single Windows Bluetooth radio could not be identified. Link attribution is inconclusive.");
            return;
        }
        ulong address = 0;
        foreach (ulong candidate in targets) address = candidate;
        var transport = new TraceTransport(address, origin, output);
        output.WriteLine("Controller attribution assumes the Book used its one current radio during the recording.");
        long[] valid = new long[5];
        long[] gaps = new long[5];
        long untyped = 0;
        bool complete = false;
        const string query = "*[System[Provider[@Name='Microsoft-Windows-BTH-BTHPORT']]]";
        const string dataPath = "Event/EventData/Data[@Name='";
        try
        {
            var filter = new EventLogQuery(etl, PathType.FilePath, query);
            using (var reader = new EventLogReader(filter))
            using (var typeField = new EventLogPropertySelector(new[] { dataPath + "BIP_Type']" }))
            using (var packetFields = new EventLogPropertySelector(new[] { dataPath + "BIP_DataLen']", dataPath + "BIP_Data']" }))
            {
                EventRecord record;
                while ((record = reader.ReadEvent()) != null)
                {
                    using (record)
                    {
                        // These are the BTHPORT manifest packet events or an
                        // event explicitly marked with the HCI channel keyword.
                        if (record.Id != 402 && record.Id != 403
                            && (record.Keywords.GetValueOrDefault() & long.MinValue) == 0) continue;
                        var native = record as EventLogRecord;
                        if (native == null) continue;
                        DateTime? recorded = record.TimeCreated;
                        DateTimeOffset time = recorded.HasValue
                            ? new DateTimeOffset(recorded.Value).ToUniversalTime() : origin;
                        var fields = native.GetPropertyValues(typeField);
                        if (fields.Count == 0 || fields[0] == null)
                        {
                            // Other BTHPORT events also use the keyword. A missing type
                            // on a known packet record breaks safe continuity.
                            if (record.Id == 402)
                            {
                                untyped++;
                                transport.Observe(time, 2, null);
                            }
                            continue;
                        }
                        int type = Convert.ToInt32(fields[0], CultureInfo.InvariantCulture);
                        if (type < 1 || type > 4) continue;
                        var data = native.GetPropertyValues(packetFields);
                        int maximum = type >= 3 ? 65539 : type == 1 ? 258 : 257;
                        long declared = data.Count == 2 && data[0] != null
                            ? Convert.ToInt64(data[0], CultureInfo.InvariantCulture) : -1;
                        byte[] packet = data.Count == 2 ? PacketBytes(data[1], maximum) : null;
                        if (!recorded.HasValue || packet == null || declared != packet.Length
                            || PacketLength(type, packet) != packet.Length)
                        {
                            gaps[type]++;
                            Gap(transport, type, time, packet);
                            continue;
                        }
                        valid[type]++;
                        transport.Observe(time, type, packet);
                    }
                }
            }
            complete = true;
        }
        catch (EventLogException) { }
        catch (UnauthorizedAccessException) { }
        catch (SecurityException) { }
        catch (IOException) { }
        catch (FormatException) { }
        catch (OverflowException) { }
        catch (InvalidCastException) { }
        transport.Finish();
        output.WriteLine("Readable controller events = " + valid[2] + ", ACL records received by Book = " + valid[3]
            + ", ACL records sent by Book = " + valid[4] + " (all devices).");
        long omitted = untyped + gaps[1] + gaps[2] + gaps[3] + gaps[4];
        if (omitted != 0) output.WriteLine("Incomplete or unusable HCI records = " + omitted
            + ", including ACL = " + (gaps[3] + gaps[4]) + ". They reduce coverage.");
        if (!complete) output.WriteLine("Reading stopped before the end of the ETL. Coverage is incomplete.");
        if (valid[3] == 0 || valid[4] == 0)
            output.WriteLine("The ETL does not provide readable ACL traffic in both directions. Request/response attribution is limited.");
        output.WriteLine("A missing match can reflect an uncaptured exchange or a protocol this reader does not recognize.");
    }
}
