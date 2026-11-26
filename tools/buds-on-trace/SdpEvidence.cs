using System;
using System.Collections.Generic;

// Passive SDP bindings are scoped to this peer and connection epoch. Only complete,
// single-response attributes are used. Fragmented SDP responses are deliberately skipped.
public sealed class SdpEvidence
{
    private const string Smep = "Samsung SMEP";
    private const string Spp = "Samsung SPP";
    private const string Unknown = "unconfirmed";
    private static readonly string SmepUuid = "F8-62-06-74-A1-ED-41-AB-A8-B9-DE-9A-D6-55-72-9D";
    private static readonly string SppUuid = "2E-73-A4-AD-33-2D-41-FC-90-E2-16-BE-F0-65-23-F2";
    private readonly Dictionary<long, Request> pending = new Dictionary<long, Request>();
    private readonly string[,] services = new string[2,31];

    private struct Request { public int Transaction, Expected, Maximum; }
    private struct Element
    {
        public int Type, Begin, End;
        public int Length { get { return End - Begin; } }
    }
    private static int U16(byte[] data, int at) { return (data[at] << 8) | data[at + 1]; }

    private static bool Next(byte[] data, ref int pos, int end, out Element item)
    {
        item = new Element();
        if (pos >= end) return false;
        int descriptor = data[pos++], type = descriptor >> 3, size = descriptor & 7;
        if (type > 8 || (type == 0 && size != 0) || ((type == 1 || type == 2) && size > 4) ||
            (type == 3 && size != 1 && size != 2 && size != 4) ||
            (type == 5 && size != 0) || ((type == 4 || type >= 6) && size < 5)) return false;
        int length = type == 0 ? 0 : 1 << size;
        if (size >= 5)
        {
            int width = 1 << (size - 5);
            if (width > end - pos) return false;
            length = 0;
            for (int i = 0; i < width; ++i)
            {
                // A valid SDP PDU cannot contain an element larger than 65535 bytes.
                if (length > 255) return false;
                length = (length << 8) | data[pos++];
            }
        }
        if (length > end - pos) return false;
        item.Type = type;
        item.Begin = pos;
        pos += length;
        item.End = pos;
        return true;
    }

    private static bool IsBluetoothUuid(byte[] d, Element e, int uuid)
    {
        if (e.Type != 3) return false;
        if (e.Length == 2) return U16(d, e.Begin) == uuid;
        if (e.Length != 4 && e.Length != 16) return false;
        if (U16(d, e.Begin) != 0 || U16(d, e.Begin + 2) != uuid) return false;
        return e.Length == 4 || BitConverter.ToString(d, e.Begin + 4, 12) == "00-00-10-00-80-00-00-80-5F-9B-34-FB";
    }

    private static bool HasRequestedAttributes(byte[] data, Element attributes)
    {
        if (attributes.Type != 6) return false;
        bool classes = false, protocol = false;
        int pos = attributes.Begin;
        while (pos < attributes.End)
        {
            Element id;
            if (!Next(data, ref pos, attributes.End, out id) || id.Type != 1 ||
                (id.Length != 2 && id.Length != 4)) return false;
            int first = U16(data, id.Begin);
            int last = id.Length == 2 ? first : U16(data, id.Begin + 2);
            if (last < first) return false;
            classes |= first <= 1 && last >= 1;
            protocol |= first <= 4 && last >= 4;
        }
        return classes && protocol;
    }

    private static bool InitialRequest(byte[] data, out int maximum)
    {
        maximum = 0;
        int pos = 5;
        Element sequence;
        if (data[0] == 4) pos += 4; // ServiceRecordHandle.
        else
        {
            if (!Next(data, ref pos, data.Length, out sequence) || sequence.Type != 6) return false;
            int i = sequence.Begin, count = 0;
            while (i < sequence.End)
            {
                Element uuid;
                if (!Next(data, ref i, sequence.End, out uuid) || uuid.Type != 3 || ++count > 12) return false;
            }
            if (count == 0) return false;
        }
        if (data.Length - pos < 3) return false;
        maximum = U16(data, pos);
        pos += 2;
        return maximum >= 7 && Next(data, ref pos, data.Length, out sequence) &&
            HasRequestedAttributes(data, sequence) && pos + 1 == data.Length && data[pos] == 0;
    }

    private static bool Classes(byte[] data, Element classes, out string service)
    {
        service = Unknown;
        if (classes.Type != 6 || classes.Length == 0) return false;
        int pos = classes.Begin;
        bool smep = false, spp = false;
        while (pos < classes.End)
        {
            Element uuid;
            if (!Next(data, ref pos, classes.End, out uuid) || uuid.Type != 3) return false;
            if (uuid.Length != 16) continue;
            string value = BitConverter.ToString(data, uuid.Begin, uuid.Length);
            smep |= value == SmepUuid;
            spp |= value == SppUuid;
        }
        if (smep != spp) service = smep ? Smep : Spp;
        return true;
    }

    private static bool Channel(byte[] data, Element protocols, out int channel)
    {
        channel = 0;
        if (protocols.Type != 6) return false;
        int pos = protocols.Begin, index = 0;
        bool l2cap = false;
        while (pos < protocols.End)
        {
            Element descriptor, uuid, param;
            if (!Next(data, ref pos, protocols.End, out descriptor) || descriptor.Type != 6) return false;
            int p = descriptor.Begin;
            if (!Next(data, ref p, descriptor.End, out uuid) || uuid.Type != 3) return false;
            if (index == 0 && IsBluetoothUuid(data, uuid, 0x100))
            {
                l2cap = p == descriptor.End;
                if (!l2cap && Next(data, ref p, descriptor.End, out param))
                    l2cap = p == descriptor.End && param.Type == 1 && param.Length == 2 && U16(data, param.Begin) == 3;
            }
            if (index == 1 && l2cap && IsBluetoothUuid(data, uuid, 3) &&
                Next(data, ref p, descriptor.End, out param) && param.Type == 1 &&
                param.Length == 1 && p == descriptor.End && data[param.Begin] >= 1 && data[param.Begin] <= 30)
                channel = data[param.Begin];
            while (p < descriptor.End)
                if (!Next(data, ref p, descriptor.End, out param)) return false;
            index++;
        }
        return true;
    }

    private static bool ParseRecord(byte[] d, Element record, List<KeyValuePair<int,string>> found)
    {
        if (record.Type != 6) return false;
        int pos = record.Begin, previous = -1, channel = 0;
        string service = null;
        while (pos < record.End)
        {
            Element key, value;
            if (!Next(d, ref pos, record.End, out key) || key.Type != 1 || key.Length != 2 ||
                !Next(d, ref pos, record.End, out value)) return false;
            int id = U16(d, key.Begin);
            if (id <= previous) return false;
            previous = id;
            if (id == 1 && !Classes(d, value, out service)) return false;
            if (id == 4 && !Channel(d, value, out channel)) return false;
        }
        if (service != null && channel != 0) found.Add(new KeyValuePair<int,string>(channel,service));
        return true;
    }

    public void Accept(DateTimeOffset time, bool fromBook, int channelId, byte[] pdu)
    {
        if (pdu == null || pdu.Length < 5 || U16(pdu, 3) != pdu.Length - 5) { Close(channelId); return; }
        long key = ((long)channelId << 1) | (fromBook ? 1L : 0L);
        int id = pdu[0], transaction = U16(pdu, 1), maximum;
        if (id == 2 || id == 4 || id == 6)
        {
            pending.Remove(key);
            if ((id == 4 || id == 6) && pending.Count < 64 && InitialRequest(pdu, out maximum))
                pending[key] = new Request { Transaction = transaction, Expected = id + 1, Maximum = maximum };
            return;
        }
        Request req;
        key ^= 1L;
        if (!pending.TryGetValue(key, out req)) return;
        pending.Remove(key);
        if (req.Transaction != transaction || req.Expected != id || pdu.Length < 8) return;
        int bytes = U16(pdu, 5), pos = 7;
        if (bytes > req.Maximum || pos + bytes + 1 != pdu.Length || pdu[pdu.Length - 1] != 0) return;
        Element records;
        if (!Next(pdu, ref pos, pdu.Length - 1, out records) || records.Type != 6 || pos != pdu.Length - 1) return;
        var found = new List<KeyValuePair<int,string>>();
        if (id == 5)
        {
            if (!ParseRecord(pdu, records, found)) return;
        }
        else
        {
            int p = records.Begin;
            while (p < records.End)
            {
                Element record;
                if (!Next(pdu, ref p, records.End, out record) || !ParseRecord(pdu, record, found)) return;
            }
        }
        foreach (var binding in found)
        {
            string old = services[fromBook ? 1 : 0, binding.Key];
            services[fromBook ? 1 : 0, binding.Key] = old == null || old == binding.Value ? binding.Value : Unknown;
        }
    }

    public void Close(int channelId)
    {
        long key = ((long)channelId) << 1;
        pending.Remove(key);
        pending.Remove(key | 1L);
    }

    public string Service(bool serverIsBook, int serverChannel)
    {
        if (serverChannel < 1 || serverChannel > 30) return Unknown;
        return services[serverIsBook ? 1 : 0, serverChannel] ?? Unknown;
    }
}
