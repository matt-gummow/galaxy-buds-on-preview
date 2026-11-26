using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;

// Offline BTHPORT HCI records. Each link is bound only after a successful classic
// Connection Complete for the local paired address. BudsSession receives complete
// basic-mode SDUs on observed SDP/RFCOMM channels. All other bodies are discarded.
public sealed class TraceTransport
{
    private readonly ulong address;
    private readonly DateTimeOffset origin;
    private readonly TextWriter output;
    private int handle = -1, epochs;
    private BudsSession session;

    private sealed class Channel
    {
        public int Book, Peer, Id;
        public ushort Psm;
        public bool Basic = true;
    }

    private sealed class Request
    {
        public int Source;
        public ushort Psm;
    }

    private sealed class Fragment
    {
        public readonly byte[] Header = new byte[4];
        public int HeaderCount, Received;
        public bool IsSignal;
        public Channel Route;
        public byte[] Body;
    }

    // Key for a channel endpoint includes its owner. A CID alone is ambiguous.
    private readonly Dictionary<int, Channel> routes = new Dictionary<int, Channel>();
    private readonly Dictionary<int, Request> requests = new Dictionary<int, Request>();
    private readonly Fragment[] fragments = new Fragment[2]; // [0] from Buds, [1] from Book
    // Following a truncated PDU, continuation fragments belong to that discarded
    // PDU until another start arrives. They must not taint unrelated channels.
    private readonly bool[] discardTail = new bool[2];
    private int nextChannel, rx, tx, gaps, rfcomm, sdp, other, unmapped;

    public TraceTransport(ulong address, DateTimeOffset origin, TextWriter output)
    {
        if (address == 0 || address > 0xffffffffffffUL) throw new ArgumentOutOfRangeException("address");
        if (output == null) throw new ArgumentNullException("output");
        this.address = address;
        this.origin = origin;
        this.output = output;
    }

    private static int U16(byte[] b, int n) { return b[n] | (b[n + 1] << 8); }
    private static int Key(bool book, int id) { return (book ? 0x10000 : 0) | id; }
    private static bool Wanted(ushort psm) { return psm == 1 || psm == 3; }

    private void Mark(DateTimeOffset time, string text)
    {
        output.WriteLine("{0}s  {1}", (time - origin).TotalSeconds.ToString("F3", CultureInfo.InvariantCulture), text);
    }

    private void End()
    {
        if (session == null) return;
        if (fragments[0] != null || fragments[1] != null) gaps++;
        session.Finish();
        output.WriteLine("Link coverage: inbound ACL records {0}, outbound {1}; complete RFCOMM SDUs {2}, SDP SDUs {3}; other mapped SDUs {4}, unmapped dynamic SDUs {5}, observable gaps {6}.",
            rx, tx, rfcomm, sdp, other, unmapped, gaps);
        routes.Clear();
        requests.Clear();
        fragments[0] = fragments[1] = null;
        discardTail[0] = discardTail[1] = false;
        handle = -1;
        session = null;
    }

    private void Start(DateTimeOffset time, int h)
    {
        End();
        rx = tx = gaps = rfcomm = sdp = other = unmapped = nextChannel = 0;
        epochs++;
        handle = h;
        session = new BudsSession(origin, output);
        Mark(time, "Target classic link established.");
    }

    private void LostEvent(DateTimeOffset time)
    {
        if (session == null) return;
        Mark(time, "Controller event gap or handle reassignment; end of attributed interval.");
        gaps++;
        End();
    }

    private void ControllerEvent(DateTimeOffset time, byte[] b)
    {
        if (b == null || b.Length < 2 || b[1] != b.Length - 2) { LostEvent(time); return; }
        if (b[0] == 3 && b.Length == 13 && b[2] == 0)
        {
            int h = U16(b, 3);
            if (h >= 0xf00) return;
            ulong peer = 0;
            for (int i = 0; i < 6; i++) peer |= (ulong)b[5+i] << (8*i);
            if (b[11] == 1 && peer == address) Start(time, h);
            else if (h == handle) LostEvent(time);
            return;
        }
        if (handle < 0) return;
        if (b[0] == 5 && b.Length == 6 && b[2] == 0 && U16(b, 3) == handle)
        {
            Mark(time, "Target classic link disconnected.");
            End();
        }
        else if ((b[0] == 0x10 && b.Length == 3) ||
                 (b[0] == 0x0e && b.Length == 6 && U16(b, 3) == 0x0c03 && b[5] == 0))
            LostEvent(time);
        else if (b[0] == 0x2c && b.Length == 19 && b[2] == 0 && U16(b, 3) == handle)
            LostEvent(time);
        else if (b[0] == 0x3e && b.Length >= 6 && b[3] == 0 && U16(b, 4) == handle &&
                 (b[2] == 1 || b[2] == 10 || b[2] == 0x29 || b[2] == 0x19 || b[2] == 0x2a))
            LostEvent(time);
    }

    private void Remove(Channel channel)
    {
        routes.Remove(Key(true, channel.Book));
        routes.Remove(Key(false, channel.Peer));
        // In both directions this CID's pending SDU also belongs to its old incarnation.
        foreach (Fragment pending in fragments)
            if (pending != null && pending.Route == channel) { pending.Route = null; pending.Body = null; }
        if (Wanted(channel.Psm)) session.Close(channel.Id);
    }

    private void ForgetRoutes()
    {
        var seen = new HashSet<Channel>(routes.Values);
        foreach (Channel route in seen) Remove(route);
        requests.Clear();
    }

    private void InvalidateFragment(bool fromBook, Fragment f)
    {
        if (f == null || f.HeaderCount != 4 || f.IsSignal) ForgetRoutes();
        else if (f.Route != null && Wanted(f.Route.Psm)) session.Close(f.Route.Id);
        fragments[fromBook ? 1 : 0] = null;
        discardTail[fromBook ? 1 : 0] = true;
        gaps++;
    }

    private void Rebind(bool ownerBook, int cid)
    {
        Channel channel;
        if (routes.TryGetValue(Key(ownerBook, cid), out channel)) Remove(channel);
    }

    private void Signal(bool fromBook, byte[] b)
    {
        for (int i = 0; i < b.Length;)
        {
            if (b.Length - i < 4) { gaps++; ForgetRoutes(); return; }
            int code = b[i], ident = b[i+1], len = U16(b, i+2);
            i += 4;
            if (len > b.Length-i || ident == 0) { gaps++; ForgetRoutes(); return; }
            int requestKey = Key(fromBook, ident);
            if (code == 2 && len == 4)
            {
                ushort psm = (ushort)U16(b, i);
                int src = U16(b, i+2);
                if (src >= 0x40 && (psm & 0x101) == 1)
                {
                    Rebind(fromBook, src);
                    foreach (int k in new List<int>(requests.Keys))
                        if ((k >> 16) == (requestKey >> 16) && requests[k].Source == src)
                            requests.Remove(k);
                    requests[requestKey] = new Request { Psm = psm, Source = src };
                }
                else requests.Remove(requestKey);
            }
            else if (code == 3 && len == 8)
            {
                int dst = U16(b,i), src = U16(b,i+2), result = U16(b,i+4);
                int req = Key(!fromBook, ident);
                Request originator;
                bool matched = requests.TryGetValue(req, out originator);
                if (result != 1) requests.Remove(req); // pending result may be followed by success
                if (result == 0 && src >= 0x40 && dst >= 0x40 && U16(b,i+6) == 0)
                {
                    Rebind(fromBook, dst);
                    Rebind(!fromBook, src);
                    if (matched && originator.Source == src)
                    {
                        Channel channel = new Channel { Psm = originator.Psm, Id = ++nextChannel,
                            Book = fromBook ? dst : src, Peer = fromBook ? src : dst };
                        routes.Add(Key(true,channel.Book), channel);
                        routes.Add(Key(false,channel.Peer), channel);
                    }
                }
            }
            else if (code == 1) requests.Remove(Key(!fromBook, ident)); // command rejected
            else if ((code == 6 || code == 7) && len == 4)
            {
                // Both the request and the response carry the requester's DCID, SCID.
                bool requesterBook = code == 6 ? fromBook : !fromBook;
                int dst = U16(b,i), src = U16(b,i+2);
                Channel channel;
                if (routes.TryGetValue(Key(requesterBook,src), out channel) &&
                    (requesterBook ? channel.Peer : channel.Book) == dst) Remove(channel);
            }
            else if ((code == 4 && len >= 4) || (code == 5 && len >= 6))
            {
                Channel channel;
                // Configuration Req DCID / Rsp SCID both identify the receiver's endpoint.
                if (routes.TryGetValue(Key(!fromBook,U16(b,i)), out channel) && Wanted(channel.Psm))
                {
                    bool basic = U16(b,i+2) == 0;
                    int pos = i + (code == 4 ? 4 : 6), end = i + len;
                    while (basic && pos < end)
                    {
                        if (end - pos < 2 || b[pos+1] > end - pos - 2) { basic = false; break; }
                        if ((b[pos] & 0x7f) == 4 && (b[pos+1] < 1 || b[pos+2] != 0)) basic = false;
                        pos += 2 + b[pos+1];
                    }
                    if (!basic && channel.Basic)
                    {
                        channel.Basic = false;
                        session.Close(channel.Id);
                        gaps++;
                    }
                }
            }
            i += len;
        }
    }

    private void Bind(Fragment f, bool fromBook)
    {
        int cid = U16(f.Header,2);
        f.IsSignal = cid == 1;
        routes.TryGetValue(Key(!fromBook,cid), out f.Route);
        if (f.IsSignal || (f.Route != null && f.Route.Basic && Wanted(f.Route.Psm)))
            f.Body = new byte[U16(f.Header,0)];
    }

    private void Acl(DateTimeOffset time, bool fromBook, byte[] raw)
    {
        if (session == null) return;
        int dir = fromBook ? 1 : 0;
        if (raw == null || raw.Length < 2)
        {
            InvalidateFragment(fromBook, null);
            return;
        }
        int tag = U16(raw,0);
        if ((tag & 0xfff) != handle || (tag & 0xc000) != 0) return;
        if (fromBook) tx++; else rx++;
        int pb = (tag >> 12) & 3;
        Fragment f = fragments[dir];
        if (pb == 3) { InvalidateFragment(fromBook, null); return; } // reserved
        if (pb == 1 && discardTail[dir]) return;
        if (pb == 0 || pb == 2)
        {
            if (f != null) InvalidateFragment(fromBook, f);
            discardTail[dir] = false;
            f = fragments[dir] = new Fragment();
        }
        if (f == null) { InvalidateFragment(fromBook, null); return; }
        int pos = 4;
        int available = Math.Max(0,raw.Length-pos);
        int bytes = Math.Min(4-f.HeaderCount, available);
        if (bytes != 0)
        {
            Buffer.BlockCopy(raw,pos,f.Header,f.HeaderCount,bytes);
            f.HeaderCount += bytes;
            pos += bytes;
            if (f.HeaderCount == 4) Bind(f,fromBook);
        }
        if (raw.Length < 4 || U16(raw,2) != raw.Length-4)
        {
            InvalidateFragment(fromBook,f);
            return;
        }
        if (f.HeaderCount < 4) return;
        int length = U16(f.Header,0);
        if (raw.Length - pos > length - f.Received) { InvalidateFragment(fromBook,f); return; }
        if (f.Body != null) Buffer.BlockCopy(raw,pos,f.Body,f.Received,raw.Length-pos);
        f.Received += raw.Length-pos;
        if (f.Received != length) return;
        fragments[dir] = null;
        if (f.IsSignal) Signal(fromBook,f.Body);
        else if (f.Route != null && f.Body != null && f.Route.Basic)
        {
            if (f.Route.Psm == 3) rfcomm++; else sdp++;
            session.L2cap(time,fromBook,f.Route.Psm,f.Route.Id,f.Body);
        }
        else if (f.Route != null) other++;
        else if (U16(f.Header,2) >= 0x40) unmapped++;
    }

    public void Observe(DateTimeOffset time, int bipType, byte[] packet)
    {
        if (bipType == 1 && handle >= 0 && packet != null && packet.Length == 6 &&
            U16(packet,0) == 0x0406 && packet[2] == 3 && U16(packet,3) == handle)
            Mark(time, "Book requested disconnect of the target classic link.");
        else if (bipType == 2) ControllerEvent(time,packet);
        else if (bipType == 3 || bipType == 4) Acl(time,bipType == 4,packet);
    }

    public void Finish()
    {
        End();
        output.WriteLine("Attributable classic connection intervals: " + epochs + ".");
    }
}
