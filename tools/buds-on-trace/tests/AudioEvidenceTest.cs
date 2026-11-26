using System;
using System.IO;

public static class AudioEvidenceTest
{
    private static byte[] Connection(int code, int status, int handle, bool target, int linkType)
    {
        var packet = new byte[code == 3 ? 13 : 19];
        packet[0] = (byte)code;
        packet[1] = (byte)(packet.Length - 2);
        packet[2] = (byte)status;
        packet[3] = (byte)handle;
        packet[4] = (byte)(handle >> 8);
        for (int i = 0; i < 6; i++) packet[5+i] = (byte)((target ? 0x112233445566UL : 0x112233445567UL) >> (8*i));
        packet[11] = (byte)linkType;
        return packet;
    }

    private static byte[] Signal(int handle, params byte[] command)
    {
        var packet = new byte[8 + command.Length];
        packet[0] = (byte)handle;
        packet[1] = (byte)(0x20 | (handle >> 8));
        packet[2] = (byte)(4 + command.Length);
        packet[4] = (byte)command.Length;
        packet[6] = 1;
        Array.Copy(command, 0, packet, 8, command.Length);
        return packet;
    }

    public static void Run()
    {
        var report = new StringWriter();
        var start = new DateTimeOffset(2000,1,1,0,0,0,TimeSpan.Zero);
        var trace = new TraceTransport(0x112233445566UL, start, report);
        int second = 0;
        Action<int,byte[]> feed = delegate(int kind, byte[] packet) {
            trace.Observe(start.AddSeconds(++second), kind, packet);
        };
        feed(2, Connection(0x2c,0,4,true,2));  // before the observed target ACL
        feed(2, Connection(3,0,1,true,1));
        feed(4, Signal(1, 2,7,4,0,0x19,0,64,0));
        feed(3, Signal(1, 3,7,8,0,65,0,64,0,0,0,0,0));
        feed(2, Connection(0x2c,0,4,true,2));
        feed(2, Connection(3,0,5,true,0));
        feed(2, Connection(0x2c,0,6,false,2));
        feed(2, Connection(0x2c,4,6,true,2));
        feed(2, Connection(3,0,6,true,2));    // reserved for classic Connection Complete
        feed(2, Connection(0x2c,0,6,true,1)); // reserved for Synchronous Connection Complete
        feed(2, Connection(0x2c,0,0xf00,true,2));
        feed(3, Signal(1, 3,8,8,0,66,0,67,0,0,0,0,0)); // no matching request
        feed(4, Signal(1, 2,9,4,0,0x19,0,68,0));
        feed(3, Signal(1, 3,9,8,0,0,0,68,0,2,0,0,0)); // rejected
        feed(4, Signal(2, 2,10,4,0,0x19,0,70,0));      // entirely different ACL
        feed(3, Signal(2, 3,10,8,0,71,0,70,0,0,0,0,0));
        feed(2, new byte[]{5,4,0,1,0,19});
        feed(2, Connection(0x2c,0,4,true,0)); // after disconnect
        feed(2, Connection(3,0,2,true,1));
        trace.Finish();
        string result = report.ToString();
        if (!result.Contains("4.000s  Book and Buds opened an AVDTP channel.") ||
            !result.Contains("5.000s  Book and Buds established a synchronous audio transport") ||
            !result.Contains("6.000s  Book and Buds established a synchronous audio transport") ||
            !result.Contains("AVDTP channel openings 1, SCO/eSCO connection completions 2.") ||
            !result.Contains("AVDTP channel openings 0, SCO/eSCO connection completions 0.") ||
            !result.Contains("No classic audio transport establishment observed in this interval (LE Audio outside scope).") ||
            result.Contains("112233445566"))
            throw new Exception("Classic audio establishment timing, attribution, or interval coverage failed.");
    }
}
