using System;
using System.Globalization;
using System.IO;

// Classifies complete, CRC-checked observations on an attributed classic link.
// The same message number can mean different things on different models.
public sealed class ObservedSettings
{
    private readonly DateTimeOffset origin;
    private readonly TextWriter output;
    private int direct, version, status, versionReports, otherPropertyWrites, related, acknowledgements, omitted;
    private readonly int[] shown = new int[8];
    private const int MaxEvidenceLines = 48;

    public ObservedSettings(DateTimeOffset origin, TextWriter output)
    {
        this.origin = origin;
        this.output = output;
    }

    private void Record(int category, DateTimeOffset time, string evidence, string service)
    {
        if (shown[category]++ >= MaxEvidenceLines) { omitted++; return; }
        string binding = service == "Samsung SMEP" || service == "Samsung SPP"
            ? "SDP matched " + service : "Samsung framing matched; service UUID unconfirmed";
        output.WriteLine("{0}s  {1} ({2}).",
            (time-origin).TotalSeconds.ToString("F3", CultureInfo.InvariantCulture), evidence, binding);
    }

    public void Frame(DateTimeOffset time, bool fromBook, int channelId, int dlci,
        bool alternative, int messageId, bool response, byte[] payload, string service)
    {
        if (payload == null) return;
        if (alternative)
        {
            if (service == "Samsung SPP" || messageId != 1 || payload.Length < 1) return;
            // Recognize the property envelope and its declared extent. Do not
            // retain or report host version values, account fields or trailing data.
            if (fromBook && payload[0] == 0x43)
            {
                if (payload.Length >= 8 && payload[1] == 4 && payload[2] == 3 &&
                    payload[3] == payload.Length - 4 && payload[4] == 0 && payload[5] == 0 &&
                    payload[6] == 0x0b)
                {
                    version++;
                    Record(0, time, "Book sent a property matching the upstream MDE host-version format", service);
                }
                else otherPropertyWrites++;
            }
            else if (!fromBook && payload.Length >= 11 && payload[0] == 0x45 && payload[1] == 2 &&
                     payload[2] == 5 && payload[3] == 0x4c && payload[4] == 0x0b)
            {
                versionReports++;
                Record(1, time, "Buds sent a notification matching the upstream MDE host-version format", service);
            }
            return;
        }
        if (service == "Samsung SMEP") return;
        if (fromBook && messageId == 0x20 && payload.Length == 2 && payload[0] == 1 && payload[1] <= 1)
        {
            direct++;
            Record(2, time, "Book sent the format Samsung's shared app calls SET_MULTIPOINT_STATUS, requested state " +
                (payload[1] == 1 ? "on" : "off"), service);
        }
        else if (!fromBook && messageId == 0x20 && payload.Length == 3 && payload[0] <= 1 && payload[2] <= 1)
        {
            status++;
            Record(3, time, "Buds reported the shared app's multipoint status format, reported state " +
                (payload[2] == 1 ? "on" : "off"), service);
        }
        else if (!fromBook && messageId == 0x76 && payload.Length == 8 && payload[1] <= 1 && payload[2] <= 1)
        {
            status++;
            Record(4, time, "Buds sent MULTIPOINT_INFO: support flag " + (payload[1] == 1 ? "yes" : "no") +
                ", device state " + (payload[2] == 1 ? "one" : "multiple"), service);
        }
        else if (!fromBook && messageId == 0x42 && payload.Length > 0 && payload[0] == 0x20)
        {
            acknowledgements++;
            Record(6, time, "Buds sent a generic acknowledgement referencing the candidate message ID; meaning unverified", service);
        }
        else if (fromBook && messageId == 0xaf && payload.Length == 1 && payload[0] <= 1)
        {
            related++;
            Record(5, time, "Book sent a frame matching the separate seamless-connection setting", service);
        }
    }

    public void Finish()
    {
        output.WriteLine("Book multipoint-setting format matches = {0}; MDE version writes = {1}; separate seamless-setting matches = {2}.",
            direct, version, related);
        output.WriteLine("Buds status reports = {0}; MDE notifications = {1}; other Book SMEP property writes = {2}.",
            status, versionReports, otherPropertyWrites);
        output.WriteLine("Generic acknowledgements referencing the candidate message ID = {0}.", acknowledgements);
        if (direct != 0) output.WriteLine("On other models the same message ID also names a debug setting. A shape match does not establish its meaning on Buds On.");
        if (omitted != 0)
            output.WriteLine("Additional repeated observations omitted from timeline = " + omitted + ".");
    }
}
