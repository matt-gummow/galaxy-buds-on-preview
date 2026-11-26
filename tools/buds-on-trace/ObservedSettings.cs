using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;

// Classifies complete, CRC-checked observations on an attributed classic link.
// The same message number can mean different things on different models.
public sealed class ObservedSettings
{
    private readonly DateTimeOffset origin;
    private readonly TextWriter output;
    private readonly ObservedFrameInventory inventory;
    private int direct, version, status, versionReports, otherPropertyWrites, related, acknowledgements, omitted;
    private int vendorHandoff, standardHandoff, unboundHandoff, announcements;
    private int clearHandoff, unboundClearHandoff, vendorSetup, unboundSetup, streamStates, unboundStreamStates;
    private readonly int[] shown = new int[13];
    private const int MaxEvidenceLines = 48;
    private static readonly TimeSpan ComparisonWindow = TimeSpan.FromSeconds(5);

    private sealed class VersionWrite
    {
        public DateTimeOffset Time;
        // Null while multiple or interrupted observations make a comparison ambiguous.
        public byte? Version;
    }

    private readonly Dictionary<Tuple<int, int>, VersionWrite> writes =
        new Dictionary<Tuple<int, int>, VersionWrite>();

    public ObservedSettings(DateTimeOffset origin, TextWriter output)
    {
        this.origin = origin;
        this.output = output;
        inventory = new ObservedFrameInventory(origin, output);
    }

    private void Record(int category, DateTimeOffset time, string evidence, string service)
    {
        if (shown[category]++ >= MaxEvidenceLines) { omitted++; return; }
        string binding = service == "Samsung SMEP" || service == "Samsung SPP"
            ? "SDP matched " + service : "Samsung framing matched; service UUID unconfirmed";
        output.WriteLine("{0}s  {1} ({2}).",
            (time-origin).TotalSeconds.ToString("F3", CultureInfo.InvariantCulture), evidence, binding);
    }

    public void Reset(int channelId, int dlci)
    {
        if (dlci != 0) { writes.Remove(Tuple.Create(channelId, dlci)); return; }
        foreach (var key in new List<Tuple<int, int>>(writes.Keys))
            if (key.Item1 == channelId) writes.Remove(key);
    }

    public void Interrupt(DateTimeOffset time, int channelId, int dlci)
    {
        if (writes.Count == 0) return;
        var key = Tuple.Create(channelId, dlci);
        VersionWrite write;
        if (writes.TryGetValue(key, out write))
        {
            if (time - write.Time > ComparisonWindow) { writes.Remove(key); return; }
            write.Version = null;
            if (time > write.Time) write.Time = time;
        }
    }

    private void Remember(DateTimeOffset time, int channelId, int dlci, byte versionField, bool overlap)
    {
        var key = Tuple.Create(channelId, dlci);
        VersionWrite previous;
        if (writes.TryGetValue(key, out previous) && time - previous.Time <= ComparisonWindow)
            Interrupt(time, channelId, dlci);
        else
            writes[key] = new VersionWrite { Time = time, Version = overlap ? (byte?)null : versionField };
    }

    private string Compare(DateTimeOffset time, int channelId, int dlci, byte versionField)
    {
        var key = Tuple.Create(channelId, dlci);
        VersionWrite write;
        if (writes.TryGetValue(key, out write))
        {
            TimeSpan elapsed = time - write.Time;
            if (elapsed < TimeSpan.Zero) Interrupt(time, channelId, dlci);
            else if (elapsed > ComparisonWindow) writes.Remove(key);
            else if (write.Version.HasValue)
            {
                writes.Remove(key);
                return write.Version.Value == versionField ? ", captured version fields are equal"
                                                         : ", captured version fields differ";
            }
        }
        return ", version-field comparison inconclusive";
    }

    // Match the two computer metadata layouts published by alephscalioni/budsClient
    // (75ff342, SamsungMdePacket.swift) and Clascheurduturfu/galaxy-continuity-mac
    // (13f0a52, BudsProtocol.swift). These fixtures classify saved data only.
    private static string ComputerSettingsReference(byte[] payload)
    {
        if (payload.Length != 18 || payload[0] != 0x73 || payload[1] != 1 || payload[2] != 1 ||
            payload[3] != 4 || payload[4] != 0 || payload[5] != 1 || payload[7] != 0) return null;
        for (int i = 11; i < payload.Length; i++)
            if (payload[i] != 0) return null;
        if (payload[6] == 0x75 && payload[8] == 0x2A && payload[9] == 0x41 && payload[10] == 0x0C)
            return "Samsung reference";
        if (payload[6] == 0x4C && payload[8] == 0 && payload[9] == 0 && payload[10] == 0)
            return "Apple reference";
        return null;
    }

    // The older vendor fixture in hoshsadiq/buds4-pro-poc (be75d18) sets the
    // wire type bit; the two Mac references clear it. Neither bit establishes
    // host direction. The caller obtains direction independently from HCI.
    private void ObserveHandoff(DateTimeOffset time, bool alternative, int id, bool wireTypeBit,
                                byte[] payload, string service)
    {
        string expectedService = alternative ? "Samsung SMEP" : "Samsung SPP";
        if (service != expectedService && service != "unconfirmed") return;

        if (alternative && id == 1 && wireTypeBit && payload.Length == 2 &&
            payload[0] == 0x71 && payload[1] == 1)
        {
            if (service == expectedService) vendorHandoff++; else unboundHandoff++;
            Record(7, time, "Book sent a frame matching the vendor computer audio-handoff request shape (wire flag set)", service);
        }
        else if (alternative && id == 1 && !wireTypeBit)
        {
            if (payload.Length == 2 && payload[0] == 0x71 && payload[1] == 1)
            {
                if (service == expectedService) clearHandoff++; else unboundClearHandoff++;
                Record(10, time, "Book sent a frame matching the clear-flag vendor computer handoff request", service);
            }
            else
            {
                string reference = ComputerSettingsReference(payload);
                if (reference != null)
                {
                    if (service == expectedService) vendorSetup++; else unboundSetup++;
                    Record(11, time, "Book sent a frame matching vendor computer settings info (" + reference + ")", service);
                }
            }
        }
        else if (!alternative && id == 0x71 && !wireTypeBit && payload.Length == 1 && payload[0] == 1)
        {
            if (service == expectedService) standardHandoff++; else unboundHandoff++;
            Record(8, time, "Book sent a frame matching the regular computer audio-handoff request shape", service);
        }
        else if (!alternative && id == 0x73 && !wireTypeBit && payload.Length == 17 &&
                 payload[0] == 1 && (payload[1] == 1 || payload[1] == 2))
        {
            for (int i = 2; i < payload.Length; i++)
                if (payload[i] != 0) return;
            announcements++;
            Record(9, time, "Book sent a frame matching the host transport announcement shape (" +
                (payload[1] == 1 ? "Bluetooth" : "LE Audio") + ")", service);
        }
    }

    public void Frame(DateTimeOffset time, bool fromBook, int channelId, int dlci,
        bool alternative, int messageId, bool response, byte[] payload, string service, bool overlap = false,
        bool handoffOnly = false)
    {
        inventory.Frame(time, fromBook, alternative, messageId, response, payload, service, handoffOnly);
        bool confirmed = service == "Samsung SMEP";
        if (!confirmed || overlap) Interrupt(time, channelId, dlci);
        bool propertyWrite = alternative && messageId == 1 && payload != null && payload.Length >= 1 &&
                             payload[0] == 0x43;
        if (fromBook && !propertyWrite) Interrupt(time, channelId, dlci);
        if (payload == null) return;
        if (fromBook) ObserveHandoff(time, alternative, messageId, response, payload, service);
        if (handoffOnly) return;
        if (alternative)
        {
            if (service == "Samsung SPP" || messageId != 1 || payload.Length < 1) return;
            if (!fromBook && !overlap && (confirmed || service == "unconfirmed"))
            {
                string state = ObservedStreamState.Describe(payload);
                if (state != null)
                {
                    if (confirmed) streamStates++; else unboundStreamStates++;
                    Record(12, time, "Buds sent a frame matching a reference stream-state layout; " + state, service);
                }
            }
            if (fromBook && payload[0] == 0x43)
            {
                if (payload.Length >= 8 && payload[1] == 4 && payload[2] == 3 &&
                    payload[3] == payload.Length - 4 && payload[4] == 0 && payload[5] == 0 &&
                    payload[6] == 0x0b)
                {
                    version++;
                    string detail = "";
                    if (confirmed)
                    {
                        detail = payload[3] == 4 ? ", version-only layout" : ", extended layout";
                        Remember(time, channelId, dlci, payload[7], overlap);
                    }
                    Record(0, time, "Book sent a property matching the upstream MDE host-version format" + detail, service);
                }
                else
                {
                    otherPropertyWrites++;
                    Interrupt(time, channelId, dlci);
                }
            }
            else if (!fromBook && payload.Length >= 11 && payload[0] == 0x45 && payload[1] == 2 &&
                     payload[2] == 5 && payload[3] == 0x4c && payload[4] == 0x0b)
            {
                versionReports++;
                string detail = confirmed ? Compare(time, channelId, dlci, payload[7]) +
                    " (historical byte comparison; echo semantics unverified)" : "";
                Record(1, time, "Buds sent a notification matching the MDE property header" + detail, service);
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
        output.WriteLine("Original Book audio-handoff request shapes on SDP-matched services: vendor {0}, regular {1}. Matching shapes on an unconfirmed service: {2}.",
            vendorHandoff, standardHandoff, unboundHandoff);
        output.WriteLine("Clear-flag vendor computer handoff requests: SDP-matched {0}, unconfirmed service {1}.",
            clearHandoff, unboundClearHandoff);
        output.WriteLine("Host transport announcement shapes (context only) = {0}.", announcements);
        output.WriteLine("Vendor computer settings info (context only): SDP-matched {0}, unconfirmed service {1}.",
            vendorSetup, unboundSetup);
        output.WriteLine("Reference stream-state reports: SDP-matched {0}, unconfirmed service {1}.",
            streamStates, unboundStreamStates);
        output.WriteLine("Direction comes from the captured HCI records. The wire flag distinguishes frame layouts. Settings info and reported stream state are context only.");
        if (vendorHandoff + standardHandoff + unboundHandoff + clearHandoff + unboundClearHandoff == 0)
            output.WriteLine("Neither reference handoff request shape was observed in the original two-format check; the clear-flag vendor check also found none. Incomplete capture, other formats, or other transports can hide a handoff.");
        else
            output.WriteLine("A request-shape match identifies a Book transmission. Its effect on Buds On, audio movement, and simultaneous phone connectivity remain unverified by that frame.");
        output.WriteLine("Book multipoint-setting format matches = {0}; MDE version writes = {1}; separate seamless-setting matches = {2}.",
            direct, version, related);
        output.WriteLine("Buds status reports = {0}; MDE notifications = {1}; other Book SMEP property writes = {2}.",
            status, versionReports, otherPropertyWrites);
        output.WriteLine("Generic acknowledgements referencing the candidate message ID = {0}.", acknowledgements);
        if (direct != 0) output.WriteLine("On other models the same message ID also names a debug setting. A shape match does not establish its meaning on Buds On.");
        if (omitted != 0)
            output.WriteLine("Additional repeated observations omitted from timeline = " + omitted + ".");
        if (versionReports != 0 && version != 0)
            output.WriteLine("The historical comparison uses candidate bytes in a preceding write and a notification on the same confirmed SMEP channel within five seconds. The notification's compared byte has no verified version meaning on this model.");
        inventory.Summary();
        writes.Clear();
    }
}

