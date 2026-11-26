using System;
using System.Globalization;
using System.IO;

// BudsSession calls this only for complete frames with a verified CRC on the
// attributed classic link. The direction comes from HCI, independent of the
// Samsung header's wire type bit. No payload bytes are printed as data.
public sealed class ObservedFrameInventory
{
    private const int RowLimit = 64;
    private readonly DateTimeOffset origin;
    private readonly TextWriter output;
    private int shown, omitted, excluded;

    public ObservedFrameInventory(DateTimeOffset origin, TextWriter output)
    {
        this.origin = origin;
        this.output = output;
    }

    private static bool KnownCommand(int command)
    {
        switch (command)
        {
            case 0x20: case 0x42: case 0x43: case 0x44: case 0x45:
            case 0x71: case 0x73: case 0x76: case 0xAF:
                return true;
            default:
                return false;
        }
    }

    private static string RecognizedShape(int command, byte[] payload, int offset, bool fromBook, bool alternative)
    {
        int length = payload.Length - offset;
        if (command == 0x71)
        {
            string shape = "other";
            if (length == 0) shape = "empty";
            else if (length == 1 && payload[offset] == 1) shape = "computer-class";
            else if (length == 1 && payload[offset] == 2) shape = "mobile-class";
            return " | 0x71 reference shape " + shape;
        }
        if (alternative && !fromBook && command == 0x42 && length == 2)
        {
            int referenced = payload[offset];
            if (referenced == 0x71 || referenced == 0x73 || referenced == 0x43 || referenced == 0x44)
                return " | acknowledgement references 0x" + referenced.ToString("X2", CultureInfo.InvariantCulture) +
                    " | result byte " + (payload[offset + 1] == 0 ? "zero" : "nonzero") + " (meaning unverified)";
        }
        return "";
    }

    public void Frame(DateTimeOffset time, bool fromBook, bool alternative, int id,
                      bool wireTypeBit, byte[] payload, string service, bool handoffOnly = false)
    {
        string expectedService = alternative ? "Samsung SMEP" : "Samsung SPP";
        bool confirmed = service == expectedService;
        if (payload == null || id < 0 || id > 255 || (!confirmed && service != "unconfirmed"))
        {
            excluded++;
            return;
        }

        // The outer vendor message ID 1 carries an inner command byte. For all
        // other outer IDs the first payload byte has unspecified meaning.
        bool hasInner = alternative && id == 1 && payload.Length != 0;
        bool hasCommand = !alternative || hasInner;
        int number = hasInner ? payload[0] : id;
        if (!confirmed && (!hasCommand || !KnownCommand(number)))
        {
            excluded++;
            return;
        }
        if (shown == RowLimit)
        {
            omitted++;
            return;
        }

        shown++;
        output.WriteLine("{0}s  Frame | {1} | {2} | {3} | {4} 0x{5:X2} | data length {6} | wire type bit {7}{8}",
            (time - origin).TotalSeconds.ToString("F3", CultureInfo.InvariantCulture),
            fromBook ? "Book to Buds" : "Buds to Book",
            confirmed ? expectedService + " (SDP confirmed)" : "service unconfirmed",
            alternative ? "vendor" : (handoffOnly ? "regular FE" : "regular FD"),
            hasCommand ? "command" : "outer ID", number,
            hasInner ? payload.Length - 1 : payload.Length,
            wireTypeBit ? "set" : "clear",
            confirmed && hasCommand ? RecognizedShape(number, payload, hasInner ? 1 : 0, fromBook, alternative) : "");
    }

    public void Summary()
    {
        output.WriteLine("Frame inventory | shown = {0} | omitted by limit = {1} | excluded by service or command = {2}",
            shown, omitted, excluded);
    }
}
