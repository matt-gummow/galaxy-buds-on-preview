using System;
using System.Linq;

public static class ControllerTest
{
    private static byte[] Open(int handle, bool target)
    {
        return new byte[]{3,11,0,(byte)handle,0,(byte)(target?6:7),5,4,3,2,1,1,0};
    }
    private static byte[] Close(int handle) { return new byte[]{5,4,0,(byte)handle,0,19}; }
    public static int Main()
    {
        var origin = DateTimeOffset.UtcNow;
        var test = new OverlapHciTimeline(0x010203040506UL, origin);
        test.Event(origin.AddSeconds(-1), Open(1,true));
        test.Event(origin, Close(1));
        test.Event(origin.AddSeconds(1), Open(2,false));
        test.Event(origin.AddSeconds(2), Open(1,true));
        test.Event(origin.AddSeconds(3), Close(2));
        test.Event(origin.AddSeconds(4), Close(1));
        test.Event(origin.AddSeconds(5), Open(1,true));
        test.Event(origin.AddSeconds(6), Open(1,false));
        test.Event(origin.AddSeconds(7), Close(1));
        test.Event(origin.AddSeconds(8), Open(1,true));
        test.Event(origin.AddSeconds(9), new byte[]{5,4});
        test.Event(origin.AddSeconds(10), Close(1));
        string result = string.Join("\n", test.Finish(true));
        if (!result.Contains("t=2.000s  Book HCI: target classic ACL connected.") ||
            !result.Contains("t=4.000s  Book HCI: target classic ACL disconnected.") ||
            !result.Contains("t=6.000s  Book HCI: controller coverage interrupted") ||
            !result.Contains("t=9.000s  Book HCI: controller coverage interrupted") ||
            result.Contains("t=7.000") || result.Contains("t=10.000") || result.Contains("010203040506") ||
            OverlapHci.DecodePacket("garbage") != null || !new byte[]{3,11}.SequenceEqual(OverlapHci.DecodePacket("03 0b")))
                throw new Exception("Book HCI attribution or redaction check failed.");
        return 0;
    }
}
