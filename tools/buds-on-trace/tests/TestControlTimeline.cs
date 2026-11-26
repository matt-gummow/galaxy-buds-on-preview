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

    private static byte[] Hex(string words)
    {
        return words.Split(' ').Select(word => Convert.ToByte(word, 16)).ToArray();
    }

    private static byte[] Control(byte address, byte control)
    {
        byte[] data = { address, control, 1, 0 };
        int fcs = 255;
        for (int i = 0; i < 3; i++)
        {
            fcs ^= data[i];
            for (int bit = 0; bit < 8; bit++) fcs = (fcs >> 1) ^ ((fcs & 1) != 0 ? 224 : 0);
        }
        data[3] = (byte)(255 - fcs);
        return data;
    }

    private static void CheckVersionTimeline(DateTimeOffset origin)
    {
        var output = new StringWriter();
        var session = new BudsSession(origin, output);
        DateTimeOffset now = origin;
        Action<bool,int,byte[]> rfcomm = delegate(bool fromBook, int channel, byte[] data) {
            now = now.AddMilliseconds(100);
            session.L2cap(now, fromBook, 3, channel, data);
        };
        // Synthetic attribute discovery binds RFCOMM server 1 on the peer to Samsung SMEP.
        session.L2cap(now, true, 1, 9, Hex("04 00 01 00 0e 00 00 01 22 ff ff 35 05 0a 00 00 ff ff 00"));
        session.L2cap(now, false, 1, 9, Hex("05 00 01 00 2c 00 29 35 27 09 00 01 35 11 1c f8 62 06 74 a1 ed 41 ab a8 b9 de 9a d6 55 72 9d 09 00 04 35 0c 35 03 19 01 00 35 05 19 00 03 08 01 00"));
        Action<int> open = delegate(int channel) {
            rfcomm(true, channel, Control(3, 0x3f));
            rfcomm(false, channel, Control(3, 0x73));
        };
        open(1);
        open(2);
        byte[] shortRequest = Frame(true, 1, Hex("43 04 03 04 00 00 0b 7b"));
        byte[] extendedRequest = Frame(true, 1, Hex("43 04 03 08 00 00 0b 66 4d 41 52 4b"));
        byte[] notification = Frame(true, 1, Hex("45 02 05 4c 0b 66 66 7b 66 66 66"));
        Action<int,byte[]> write = (channel, bytes) => rfcomm(true, channel, Serial(bytes));
        Action<string> notify = delegate(string expected) {
            int before = output.GetStringBuilder().Length;
            rfcomm(false, 1, Serial(notification));
            string line = output.ToString().Substring(before);
            if (!line.Contains(expected)) throw new Exception("Expected " + expected + ", got " + line);
        };
        const string equal = "captured version fields are equal";
        const string different = "captured version fields differ";
        const string unknown = "version-field comparison inconclusive";
        write(1, shortRequest);
        notify(equal);
        notify(unknown); // a second notification cannot reuse the request
        write(1, extendedRequest);
        notify(different); // unrelated notification bytes match the request value
        write(2, shortRequest);
        notify(unknown);
        write(1, shortRequest);
        write(1, shortRequest);
        notify(unknown);
        now = now.AddSeconds(6);
        write(1, shortRequest);
        write(1, Frame(true, 1, 0x43)); // intervening ambiguous outbound frame
        notify(unknown);
        now = now.AddSeconds(6);
        write(1, shortRequest);
        now = now.AddSeconds(6);
        notify(unknown);
        write(1, shortRequest);
        open(1); // a fresh RFCOMM handshake
        notify(unknown);
        write(1, shortRequest);
        rfcomm(false, 1, Control(11, 0x53)); // disconnect the individual DLCI
        notify(unknown);
        write(1, shortRequest);
        byte[] corrupt = (byte[])shortRequest.Clone();
        corrupt[corrupt.Length - 2] ^= 1;
        write(1, corrupt);
        notify(unknown);
        now = now.AddSeconds(6);
        write(1, shortRequest);
        session.Close(1); // dropped L2CAP channel or transport gap
        open(1);
        notify(unknown);
        // A partially observed inbound frame began before the write.
        rfcomm(false, 1, Serial(notification.Take(4).ToArray()));
        write(1, shortRequest);
        rfcomm(false, 1, Serial(notification.Skip(4).ToArray()));
        now = now.AddSeconds(6);
        write(1, shortRequest);
        now = now.AddSeconds(-2);
        notify(unknown);
        string details = output.ToString();
        if (Occurrences(details, equal) != 1 || Occurrences(details, different) != 1 ||
            Occurrences(details, unknown) != 11 || !details.Contains("extended layout") ||
            !details.Contains("version-only layout") || details.Contains("MARK"))
            throw new Exception("Confirmed version shape, comparison, or redaction check failed.");

        output = new StringWriter();
        var parser = new ObservedSettings(origin, output);
        byte[] plain = Hex("43 04 03 04 00 00 0b 7b");
        byte[] report = Hex("45 02 05 4c 0b 00 00 7b 00 00 00");
        parser.Frame(origin, true, 4, 2, true, 1, false, plain, "unconfirmed");
        parser.Frame(origin, false, 4, 2, true, 1, false, report, "unconfirmed");
        if (output.ToString().Contains("comparison") || output.ToString().Contains("layout"))
            throw new Exception("Unattributed traffic produced version details.");
        parser.Frame(origin, true, 4, 2, true, 1, false, plain, "Samsung SMEP");
        parser.Frame(origin, false, 4, 4, true, 1, false, report, "Samsung SMEP");
        if (!output.ToString().Contains(unknown) || output.ToString().Contains(equal))
            throw new Exception("Comparison crossed a DLCI boundary.");
    }

    private static void CheckHandoffEvidence(DateTimeOffset origin)
    {
        byte[] vendor = Hex("fc 05 10 01 71 01 79 1c cc");
        byte[] regular = Hex("fe 04 00 71 01 49 2b ee");
        byte[] regularOn = Frame(false, 0x71, 1);
        var report = new StringWriter();
        var s = new BudsSession(origin, report);
        Action<bool,byte[]> feed = (book, bytes) => s.L2cap(origin, book, 3, 4, Serial(bytes));
        feed(true, vendor); // exact match, but SDP did not establish the service
        feed(true, regular);
        feed(false, vendor);
        feed(false, regular);
        byte[] changed = (byte[])vendor.Clone();
        changed[2] = 0; // other vendor reference; excluded from the legacy flag-set count
        feed(true, changed);
        changed = (byte[])regular.Clone();
        changed[2] = 16;
        feed(true, changed);
        changed = (byte[])regular.Clone();
        changed[5] ^= 1;
        feed(true, changed);
        changed = (byte[])regular.Clone();
        changed[changed.Length-1] = 0xdd;
        feed(true, changed);
        changed = (byte[])vendor.Clone();
        changed[2] |= 32;
        feed(true, changed);
        feed(true, vendor); // tail of a logical fragment
        feed(true, Frame(true, 1, 0x71, 1, 2));
        feed(true, Frame(false, 0x71, 2));
        feed(true, Frame(false, 0x72, 1));

        string[] uuids = {
            "f8 62 06 74 a1 ed 41 ab a8 b9 de 9a d6 55 72 9d",
            "2e 73 a4 ad 33 2d 41 fc 90 e2 16 be f0 65 23 f2"
        };
        foreach (string uuid in uuids)
        {
            s.Finish();
            s = new BudsSession(origin, report);
            s.L2cap(origin, true, 1, 9, Hex("04 00 01 00 0e 00 00 01 22 ff ff 35 05 0a 00 00 ff ff 00"));
            s.L2cap(origin, false, 1, 9, Hex("05 00 01 00 2c 00 29 35 27 09 00 01 35 11 1c " +
                uuid + " 09 00 04 35 0c 35 03 19 01 00 35 05 19 00 03 08 01 00"));
            s.L2cap(origin, true, 3, 4, Control(3, 0x3f));
            s.L2cap(origin, false, 3, 4, Control(3, 0x73));
            // Split across captured serial packets. Only the matching service counts.
            feed(true, vendor.Take(5).ToArray());
            feed(true, vendor.Skip(5).ToArray());
            feed(true, regular.Take(2).ToArray());
            feed(true, regular.Skip(2).ToArray());
            feed(true, regularOn);
            byte[] fields = new byte[17];
            fields[0] = 1;
            fields[1] = 2;
            feed(true, Frame(false, 0x73, fields));
            fields[1] = 1;
            byte[] announced = Frame(false, 0x73, fields);
            announced[0] = 0xfe;
            announced[announced.Length - 1] = 0xee;
            feed(true, announced);
            feed(false, announced);
            fields[16] = 1;
            feed(true, Frame(false, 0x73, fields));
            fields[16] = 0;
            fields[1] = 3;
            feed(true, Frame(false, 0x73, fields));
        }
        s.Finish();
        string text = report.ToString();
        if (!text.Contains("vendor 0, regular 0. Matching shapes on an unconfirmed service: 2.") ||
            !text.Contains("vendor 1, regular 0. Matching shapes on an unconfirmed service: 0.") ||
            !text.Contains("vendor 0, regular 2. Matching shapes on an unconfirmed service: 0.") ||
            Occurrences(text, "matching the vendor computer") != 2 || Occurrences(text, "matching the regular computer") != 3 ||
            Occurrences(text, "matching the host transport announcement shape") != 2 ||
            !text.Contains("announcement shapes (context only) = 2."))
            throw new Exception("Handoff framing, confidence, direction or transport context regression: " + text);
        report = new StringWriter();
        s = new BudsSession(origin, report);
        feed(true, Frame(false, 0x73, new byte[17]));
        feed(true, Frame(false, 0x72, 1));
        s.Finish();
        if (!report.ToString().Contains("Neither reference handoff request shape was observed"))
            throw new Exception("Missing handoff coverage caveat.");
    }

    private static void BindService(BudsSession session, DateTimeOffset time, string serviceUuid)
    {
        session.L2cap(time, true, 1, 9, Hex("04 00 01 00 0e 00 00 01 22 ff ff 35 05 0a 00 00 ff ff 00"));
        session.L2cap(time, false, 1, 9, Hex("05 00 01 00 2c 00 29 35 27 09 00 01 35 11 1c "
            + serviceUuid + " 09 00 04 35 0c 35 03 19 01 00 35 05 19 00 03 08 01 00"));
        session.L2cap(time, true, 3, 4, Control(3, 0x3f));
        session.L2cap(time, false, 3, 4, Control(3, 0x73));
    }

    private static void CheckVendorReplay(DateTimeOffset origin)
    {
        // Source fixtures: galaxy-continuity-mac 13f0a528 BudsProtocol.takeAudio and
        // SamsungMdePacket.swift at budsClient 75ff3428. The body's CRC excludes header flags.
        byte[] request = Hex("fc 05 00 01 71 01 79 1c cc");
        if (!request.SequenceEqual(Frame(true, 1, 0x71, 1)))
            throw new Exception("Vendor clear-flag fixture and reconstructed frame differ.");
        byte[] settingsSamsung = Hex("01 01 04 00 01 75 00 2a 41 0c 00 00 00 00 00 00 00");
        byte[] settingsApple = Hex("01 01 04 00 01 4c 00 00 00 00 00 00 00 00 00 00 00");
        byte[] state = new byte[18];
        state[0] = 11;
        state[7] = 1;
        // Fields beyond the three classified values may contain private information.
        Array.Copy(Hex("4d 41 52 4b"), 0, state, 10, 4);
        byte[] tlv = Cat(Hex("02 05 12"), state);
        byte[] notify = Frame(true, 1, Cat(new byte[] { 0x45 }, tlv));

        string[] bindings = { "Samsung SMEP", "unconfirmed", "Samsung SPP" };
        foreach (string binding in bindings)
        {
            var output = new StringWriter();
            var session = new BudsSession(origin, output);
            if (binding != "unconfirmed")
                BindService(session, origin, binding == "Samsung SMEP" ?
                    "f8 62 06 74 a1 ed 41 ab a8 b9 de 9a d6 55 72 9d" :
                    "2e 73 a4 ad 33 2d 41 fc 90 e2 16 be f0 65 23 f2");
            Action<bool,byte[]> feed = (book, bytes) => session.L2cap(origin, book, 3, 4, Serial(bytes));

            feed(true, request.Take(5).ToArray());
            feed(true, request.Skip(5).ToArray());
            feed(true, Hex("fc 05 10 01 71 01 79 1c cc"));
            feed(false, request);
            feed(true, Frame(true, 1, 0x71, 2));
            feed(true, Frame(true, 1, 0x71, 1, 0));
            byte[] corrupt = (byte[])request.Clone();
            corrupt[corrupt.Length-2] ^= 1;
            feed(true, corrupt);
            byte[] fragment = (byte[])request.Clone();
            fragment[2] |= 32;
            feed(true, fragment);
            feed(true, request); // tail of the marked fragment must not match
            foreach (byte[] settings in new[] { settingsApple, settingsSamsung })
            {
                byte[] encoded = Frame(true, 1, Cat(new byte[] { 0x73 }, settings));
                feed(true, encoded);
                feed(false, encoded);
                encoded[2] |= 16; // different reference shape
                feed(true, encoded);
                byte[] changed = (byte[])settings.Clone();
                changed[16] = 19;
                feed(true, Frame(true, 1, Cat(new byte[] { 0x73 }, changed)));
            }
            feed(false, notify);
            feed(true, notify);
            byte[] inboundBroken = (byte[])notify.Clone();
            inboundBroken[inboundBroken.Length-2] ^= 4;
            feed(false, inboundBroken);
            session.Finish();

            string text = output.ToString();
            int known = binding == "Samsung SMEP" ? 1 : 0;
            int unbound = binding == "unconfirmed" ? 1 : 0;
            string counters = "SDP-matched " + known + ", unconfirmed service " + unbound + ".";
            if (!text.Contains("Clear-flag vendor computer handoff requests: " + counters) ||
                !text.Contains("Reference stream-state reports: " + counters) ||
                !text.Contains("Vendor computer settings info (context only): SDP-matched " + 2*known + ", unconfirmed service " + 2*unbound + ".") ||
                Occurrences(text, "Book sent a frame matching the clear-flag vendor computer handoff request") != known+unbound ||
                Occurrences(text, "Book sent a frame matching the vendor computer") != known+unbound ||
                Occurrences(text, "Book sent a frame matching vendor computer settings info") != 2*(known+unbound) ||
                Occurrences(text, "Buds sent a frame matching a reference stream-state layout") != known+unbound ||
                text.Contains("MARK"))
                throw new Exception("Vendor replay attribution, classification, or privacy regression for " + binding + ": " + text);
        }

        // Full TLV validation, including records after a matched one.
        string readState = ObservedStreamState.Describe(Cat(Hex("44 00 00"), tlv));
        if (ObservedStreamState.Describe(Cat(Hex("45"), tlv, tlv)) == null || readState == null ||
            !readState.Contains("foreground, stream flags A2DP"))
            throw new Exception("Notify/read response framing or duplicate semantics failed.");
        byte[] background = (byte[])tlv.Clone();
        background[3 + 1] = 1;
        background[3 + 2] = 132;
        background[3 + 7] = 2;
        string stateText = ObservedStreamState.Describe(Cat(Hex("45"), background));
        if (stateText == null || !stateText.Contains("background, stream flags HFP") ||
            !stateText.Contains("background-stream rejection indicated") || stateText.Contains("MARK"))
            throw new Exception("Known background call stream or private-field handling failed.");
        byte[] invalidState = (byte[])tlv.Clone(); invalidState[4] = 3;
        byte[] mismatched = (byte[])tlv.Clone(); mismatched[0] = 3;
        byte[] wrongOpcode = (byte[])tlv.Clone(); wrongOpcode[3] = 12;
        foreach (var bad in new[] {
            Cat(Hex("45"), tlv, Hex("01")), Cat(Hex("45"), tlv, Hex("03 04 07 00")),
            Cat(Hex("44"), tlv), Cat(Hex("45"), invalidState), Cat(Hex("45"), tlv, background),
            Cat(Hex("45"), mismatched), Cat(Hex("45"), wrongOpcode), Cat(Hex("45 02 05 01 0b"), tlv),
            Cat(Hex("45"), tlv.Take(tlv.Length-1).ToArray()), Cat(Hex("43"), tlv)
        })
            if (ObservedStreamState.Describe(bad) != null)
                throw new Exception("Unusable status record produced a state.");
    }

    private static void CheckFrameInventory(DateTimeOffset origin)
    {
        var output = new StringWriter();
        var inventory = new ObservedFrameInventory(origin, output);
        // Only the known inner command or outer ID may be reported for a vendor envelope.
        inventory.Frame(origin, true, true, 1, false, Hex("71 01"), "Samsung SMEP");
        inventory.Frame(origin, false, true, 1, false, Hex("9b 4d 41 52 4b"), "unconfirmed");
        inventory.Frame(origin, false, true, 2, true, Hex("4d 41 52 4b"), "Samsung SMEP");
        inventory.Frame(origin, true, false, 0x71, false, Hex("01"), "Samsung SMEP");
        for (int i = 0; i < 65; i++)
            inventory.Frame(origin, false, true, 1, true, Hex("45 4d 41 52 4b"), "unconfirmed");
        inventory.Summary();
        string result = output.ToString();
        if (Occurrences(result, "Frame | ") != 64 ||
            !result.Contains("Book to Buds | Samsung SMEP (SDP confirmed) | vendor | command 0x71 | data length 1 | wire type bit clear") ||
            !result.Contains("outer ID 0x02") ||
            !result.Contains("shown = 64 | omitted by limit = 3 | excluded by service or command = 2") ||
            result.Contains("MARK") || result.Contains("0x4D") || result.Contains("0x9B"))
            throw new Exception("Inventory cap, attribution, or private-data redaction regression: " + result);

        output = new StringWriter();
        inventory = new ObservedFrameInventory(origin, output);
        inventory.Frame(origin, false, true, 1, true, Hex("42 71 00"), "Samsung SMEP");
        inventory.Frame(origin, false, true, 1, true, Hex("42 73 9b"), "Samsung SMEP");
        inventory.Frame(origin, true, true, 1, true, Hex("42 71 00"), "Samsung SMEP");
        inventory.Frame(origin, false, true, 1, true, Hex("42 71"), "Samsung SMEP");
        inventory.Frame(origin, false, true, 1, true, Hex("42 71 00"), "unconfirmed");
        inventory.Frame(origin, false, true, 1, true, Hex("42 9b 00"), "Samsung SMEP");
        inventory.Frame(origin, true, true, 1, false, Hex("71 01"), "Samsung SMEP");
        inventory.Frame(origin, true, true, 1, false, Hex("71 01"), "unconfirmed");
        result = output.ToString();
        if (Occurrences(result, "acknowledgement references") != 2 ||
            !result.Contains("references 0x71 | result byte zero (meaning unverified)") ||
            !result.Contains("references 0x73 | result byte nonzero (meaning unverified)") ||
            Occurrences(result, "0x71 reference shape computer-class") != 1 || result.Contains("0x9B"))
            throw new Exception("Acknowledgement or request class exposed an unconfirmed field: " + result);
    }

    public static int Main()
    {
        AudioEvidenceTest.Run();
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
        CheckVersionTimeline(time);
        CheckHandoffEvidence(time);
        CheckVendorReplay(time);
        CheckFrameInventory(time);
        Console.WriteLine("Offline controller, RFCOMM, setting, and redaction checks passed.");
        return 0;
    }
}
