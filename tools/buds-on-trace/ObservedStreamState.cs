using System;
using System.Collections.Generic;

// Passive shape comparison against SamsungMdePacket.multipointStatus in
// alephscalioni/budsClient at 75ff3428. SM-U600 semantics remain unverified.
// BudsSession supplies only complete, sequence-zero vendor frames after validating their CRC.
// The direction/service gate is in ObservedSettings.
internal static class ObservedStreamState
{
    public static string Describe(byte[] payload)
    {
        if (payload == null || payload.Length == 0) return null;
        int offset;
        if (payload[0] == 0x45) offset = 1;
        else if (payload[0] == 0x44 && payload.Length >= 3) offset = 3;
        else return null;

        int state = -1, flags = 0, reason = 0;
        while (offset < payload.Length)
        {
            // Validate the whole list, even after finding a qualifying record.
            if (payload.Length - offset < 3) return null;
            int key = payload[offset] | (payload[offset + 1] << 8);
            int length = payload[offset + 2];
            offset += 3;
            if (length > payload.Length - offset) return null;

            if (key == 0x0502 && length == 0) return null;
            if (key == 0x0502 && payload[offset] == 0x0b)
            {
                if (length < 18 || payload[offset + 1] > 1) return null;
                int nextState = payload[offset + 1];
                int nextReason = payload[offset + 2];
                int nextFlags = payload[offset + 7];
                // Repeated records must agree on every field interpreted here.
                if (state >= 0 && (state != nextState || flags != nextFlags || reason != nextReason))
                    return null;
                state = nextState;
                flags = nextFlags;
                reason = nextReason;
            }
            offset += length;
        }
        if (state < 0) return null;

        var labels = new List<string>();
        if ((flags & 0x01) != 0) labels.Add("A2DP");
        if ((flags & 0x02) != 0) labels.Add("HFP");
        if ((flags & 0x04) != 0) labels.Add("CIS media");
        if ((flags & 0x08) != 0) labels.Add("BIS");
        if ((flags & 0x10) != 0) labels.Add("CIS call");
        if ((flags & 0x80) != 0) labels.Add("Auto Switch request flag");
        if ((flags & 0x60) != 0) labels.Add("unrecognized flag present");
        string names = labels.Count == 0 ? "none set" : String.Join(" + ", labels.ToArray());
        string detail = (state == 0 ? "foreground" : "background") + ", stream flags " + names;
        if (state == 1 && reason == 132) detail += ", background-stream rejection indicated";
        return detail;
    }
}
