using System;
using System.Collections.Generic;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;

namespace BudsOverlap
{
    // In-memory only. The caller uses Address for private matching on both hosts.
    public sealed class BookTarget
    {
        public string Address { get; private set; }
        public string Name { get; private set; }
        internal ulong Number { get; private set; }

        internal BookTarget(ulong address, string name)
        {
            Number = address;
            string hex = address.ToString("X12", CultureInfo.InvariantCulture);
            var octets = new string[6];
            for (int i = 0; i < octets.Length; i++) octets[i] = hex.Substring(2 * i, 2);
            Address = String.Join(":", octets);
            Name = name;
        }
    }

    public static class BookCache
    {
        private const int NoMoreItems = 259;
        private static readonly Regex Model = new Regex(
            @"^(?:(?:.+['\u2019]s\s+)?(?:Galaxy\s+)?Buds\s+On|SM-U600)(?:\s*\([0-9a-f]{4}\))?$",
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
        private static readonly object Gate = new object();
        private static BookTarget target;

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

        internal sealed class Candidate
        {
            public ulong Number;
            public string Name;
            public bool Connected;
        }

        internal static string Select(IEnumerable<Candidate> candidates, ref BookTarget pinned)
        {
            Candidate only = null;
            foreach (Candidate candidate in candidates)
            {
                if (candidate.Number == 0 || candidate.Number > 0xffffffffffffUL) continue;
                if (pinned != null ? candidate.Number != pinned.Number :
                    !Model.IsMatch((candidate.Name ?? "").Trim())) continue;
                if (only != null && (only.Number != candidate.Number || only.Connected != candidate.Connected))
                    return "Unknown";
                only = candidate;
            }
            if (only == null) return "Unknown";
            if (pinned == null) pinned = new BookTarget(only.Number, only.Name.Trim());
            return only.Connected ? "Connected" : "Disconnected";
        }

        public static BookTarget Target { get { lock (Gate) return target; } }
        internal static void Clear() { lock (Gate) target = null; }

        public static string Status()
        {
            try { return ReadStatus(); }
            catch (DllNotFoundException) { return "Unknown"; }
            catch (EntryPointNotFoundException) { return "Unknown"; }
        }

        // No inquiry, connection, audio endpoint activation or pairing.
        private static string ReadStatus()
        {
            Search search = new Search { Size = (uint)Marshal.SizeOf(typeof(Search)),
                Authenticated = 1, Remembered = 1, Connected = 1, IssueInquiry = 0 };
            uint size = (uint)Marshal.SizeOf(typeof(Device));
            Device device = new Device { Size = size };
            IntPtr find = BluetoothFindFirstDevice(ref search, ref device);
            if (find == IntPtr.Zero) return "Unknown";
            var candidates = new List<Candidate>();
            try
            {
                do
                {
                    if (device.Remembered != 0 || device.Authenticated != 0)
                        candidates.Add(new Candidate { Number = device.Address, Name = device.Name,
                            Connected = device.Connected != 0 });
                    device = new Device { Size = size };
                } while (BluetoothFindNextDevice(find, ref device) != 0);
                if (Marshal.GetLastWin32Error() != NoMoreItems) return "Unknown";
            }
            finally { BluetoothFindDeviceClose(find); }
            lock (Gate) return Select(candidates, ref target);
        }
    }
}
