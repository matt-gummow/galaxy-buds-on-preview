using System;
using System.Runtime.InteropServices;
using BudsOverlap;

public static class BookEvidenceTests
{
    private static void Expect(bool value, string reason)
    {
        if (!value) throw new Exception(reason);
    }

    private static BookCache.Candidate Candidate(ulong number, string name, bool connected)
    {
        return new BookCache.Candidate { Number = number, Name = name, Connected = connected };
    }

    public static void Run()
    {
        BookTarget pinned = null;
        var buds = Candidate(0xabc12340005UL, "Matthew\u2019s Buds On", true);
        var other = Candidate(0x321UL, "My Buds On Repeater", true);
        var second = Candidate(3, "Galaxy Buds On (AB12)", false);
        Expect(BookCache.Select(new[]{other}, ref pinned) == "Unknown" && pinned == null, "similar name");
        Expect(BookCache.Select(new[]{buds, second}, ref pinned) == "Unknown" && pinned == null, "ambiguous names");
        Expect(BookCache.Select(new[]{other, buds}, ref pinned) == "Connected", "connected");
        Expect(pinned.Address == "0A:BC:12:34:00:05", "leading zero address");
        Expect(BookCache.Select(new[]{second}, ref pinned) == "Unknown", "pinned device missing");
        var disconnected = Candidate(buds.Number, "renamed", false);
        Expect(BookCache.Select(new[]{disconnected}, ref pinned) == "Disconnected", "renamed");
        Expect(BookCache.Select(new[]{buds, disconnected}, ref pinned) == "Unknown", "conflicting same address");
        pinned = null;
        Expect(BookCache.Select(new[]{second}, ref pinned) == "Disconnected", "model suffix");
        Expect(BookCache.Select(new BookCache.Candidate[0], ref pinned) == "Unknown", "empty list");

        const int size = 48;
        const long address = 0x123456789abcL;
        var utc = new DateTime(2026, 1, 2, 3, 4, 5, DateTimeKind.Utc);
        IntPtr p = Marshal.AllocHGlobal(size);
        try
        {
            Marshal.Copy(new byte[size], 0, p, size);
            Marshal.WriteInt32(p, 0, 1);
            Marshal.StructureToPtr(BookEvents.Hci, IntPtr.Add(p, 8), false);
            Marshal.WriteInt32(p, 28, 16);
            Marshal.WriteInt64(p, 32, address);
            Marshal.WriteByte(p, 40, 1);
            Marshal.WriteByte(p, 41, 1);
            var item = BookEvents.Parse(utc,address,p,size);
            Expect(item != null && item.Utc == utc && item.Kind == "Classic" && item.State == "Connected", "ACL connected");
            Marshal.WriteByte(p, 41, 0);
            Expect(BookEvents.Parse(utc,address,p,size).State == "Disconnected", "ACL disconnected");
            Marshal.WriteByte(p, 40, 2);
            Expect(BookEvents.Parse(utc,address,p,size).Kind == "CallAudio", "SCO");
            Marshal.WriteByte(p, 40, 3);
            Expect(BookEvents.Parse(utc,address,p,size) == null, "LE not classic");
            Marshal.StructureToPtr(BookEvents.L2cap, IntPtr.Add(p, 8), false);
            Marshal.WriteInt16(p, 40, 0x19);
            Marshal.WriteByte(p, 42, 1);
            Expect(BookEvents.Parse(utc,address,p,size).Kind == "MediaChannel", "AVDTP event");
            Expect(BookEvents.Parse(utc,address+1,p,size) == null, "wrong device");
            Expect(BookEvents.Parse(utc,address,p,38) == null, "truncated");
            Marshal.WriteInt32(p, 28, 10);
            Expect(BookEvents.Parse(utc,address,p,size) == null, "truncated media");
            Marshal.WriteInt32(p, 28, 16);
            Marshal.WriteInt32(p, 0, 0);
            Expect(BookEvents.Parse(utc,address,p,size) == null, "wrong filter");
        }
        finally { Marshal.FreeHGlobal(p); }
    }
}
