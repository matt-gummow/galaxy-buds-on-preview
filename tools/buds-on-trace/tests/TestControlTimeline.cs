using System;
using System.IO;
using System.Linq;

public static class TestControlTimeline
{
    private static byte[] Cat(params byte[][] parts) { return parts.SelectMany(part => part).ToArray(); }
    private static byte[] W(int n) { return new byte[] { (byte)n, (byte)(n >> 8) }; }
    private static byte[] Frame(bool alternate, byte id, params byte[] data)
    {
        var body = Cat(new byte[] { id }, data);
        int crc = 0;
        foreach (byte value in body)
        {
            crc ^= value << 8;
            for (int i = 0; i < 8; i++) crc = ((crc << 1) ^ ((crc & 0x8000) == 0 ? 0 : 0x1021)) & 65535;
        }
        return Cat(new byte[] { alternate ? (byte)252 : (byte)253 }, W(body.Length+2),
            body,W(crc),new byte[] { alternate ? (byte)204 : (byte)221 });
    }

    private static byte[] Serial(byte[] chunk)
    {
        int fcs = 255;
        foreach (byte value in new byte[] { 11, 239 })
        {
            fcs ^= value;
            for (int i=0; i<8; i++) fcs = (fcs >> 1) ^ ((fcs & 1) != 0 ? 224 : 0);
        }
        return Cat(new byte[]{11,239,(byte)(1+2*chunk.Length)},chunk,new byte[]{(byte)(255-fcs)});
    }

    private static byte[] Acl(int handle, int cid, byte[] payload)
    {
        byte[] sdu = Cat(W(payload.Length),W(cid),payload);
        return Cat(W(0x2000|handle),W(sdu.Length),sdu);
    }

    private static int Occurrences(string s, string word)
    {
        return s.Split(new[] { word }, StringSplitOptions.None).Length-1;
    }

    public static int Main()
    {
        var output = new StringWriter();
        var t = new TraceTransport(0x112233445566UL, new DateTimeOffset(2000,1,1,0,0,0,TimeSpan.Zero), output);
        DateTimeOffset time = new DateTimeOffset(2000,1,1,0,0,0,TimeSpan.Zero);
        Action<int,byte[]> feed = delegate(int type, byte[] b) {
            time = time.AddSeconds(1); t.Observe(time,type,b);
        };
        feed(2,new byte[]{3,11,0,1,0,0x66,0x55,0x44,0x33,0x22,0x11,1,0});
        feed(4,Acl(1,1,new byte[]{2,7,4,0,3,0,64,0}));
        feed(3,Acl(1,1,new byte[]{3,7,8,0,65,0,64,0,0,0,0,0}));
        byte[] sharedFormat = Frame(false,32,1,1);
        // Split the frame across serial packets on the same link.
        feed(4,Acl(1,65,Serial(sharedFormat.Take(3).ToArray())));
        feed(4,Acl(1,65,Serial(sharedFormat.Skip(3).ToArray())));
        feed(3,Acl(1,64,Serial(Frame(false,118,0,1,0,0,0,0,0,0))));
        feed(3,Acl(1,64,Serial(Frame(false,66,32,0))));
        // Wrong handle, wrong direction, malformed CRC, mismatched shape and generic nested property.
        feed(4,Acl(2,65,Serial(sharedFormat)));
        feed(3,Acl(1,64,Serial(sharedFormat)));
        var bad = (byte[])sharedFormat.Clone(); bad[bad.Length-2] ^= 1;
        feed(4,Acl(1,65,Serial(bad)));
        feed(4,Acl(1,65,Serial(Frame(false,32,7,1))));
        feed(4,Acl(1,65,Serial(Frame(true,1,0x43,0,0,0,0))));
        feed(1,new byte[]{6,4,3,1,0,19});
        feed(2,new byte[]{5,4,0,1,0,22});
        feed(4,Acl(1,65,Serial(sharedFormat))); // after disconnect
        t.Finish();
        string s = output.ToString();
        if (Occurrences(s,"requested state on")!=1 || Occurrences(s,"device state multiple")!=1 ||
            Occurrences(s,"Buds sent a generic acknowledgement")!=1 || !s.Contains("MDE version writes = 0") ||
            !s.Contains("other Book SMEP property writes = 1") || !s.Contains("Book requested disconnect") ||
            s.Contains("112233445566"))
            throw new Exception("Attribution, timeline classification, or privacy check failed.");
        // Synthetic property: recognizer emits category only and suppresses uninterpreted tail data.
        var w = new StringWriter();
        var c = new ObservedSettings(time,w);
        byte[] sample = new byte[]{0x43,4,3,8,0,0,11,0xff,0x4d,0x41,0x52,0x4b};
        c.Frame(time,true,1,2,true,1,false,sample,"Samsung SMEP");
        c.Frame(time,false,1,2,true,1,false,sample,"Samsung SMEP");
        c.Frame(time,true,1,2,true,1,false,sample,"Samsung SPP");
        c.Frame(time,true,1,2,false,32,false,new byte[]{1,0},"unconfirmed");
        c.Frame(time,false,1,2,true,1,false,new byte[]{69,2,5,76,11,0,0,0,0,0,0},"Samsung SMEP");
        c.Finish();
        string details=w.ToString();
        if (Occurrences(details,"Book sent a property matching")!=1 || !details.Contains("MDE notifications = 1")
            || !details.Contains("requested state off") || details.Contains("MARK"))
            throw new Exception("Version negotiation and status-only fixture check failed.");
        Console.WriteLine("Offline controller, RFCOMM, setting, and redaction checks passed.");
        return 0;
    }
}
