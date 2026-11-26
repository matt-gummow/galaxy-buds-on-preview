using System;
using System.Collections.Generic;
using System.IO;

// One instance per identified BR/EDR ACL link. Input PDUs were already
// reassembled and attributed by direction and negotiated L2CAP channel.
public sealed class BudsSession
{
    private sealed class StreamState
    {
        public readonly List<byte> Bytes = new List<byte>();
        public readonly HashSet<int> Fragments = new HashSet<int>();
    }

    private sealed class Mux
    {
        public readonly Dictionary<int, StreamState> Streams = new Dictionary<int, StreamState>();
        public bool? PendingOpener;
        public bool? Initiator;
    }

    private readonly Dictionary<int, Mux> muxes = new Dictionary<int, Mux>();
    private readonly SdpEvidence sdp = new SdpEvidence();
    private readonly ObservedSettings settings;
    private readonly TextWriter output;
    private int uiFrames, sppFrames, smepFrames, fragmented, malformed;

    public BudsSession(DateTimeOffset origin, TextWriter output)
    {
        this.output = output;
        settings = new ObservedSettings(origin, output);
    }

    private static byte FrameCheck(byte[] data, int length)
    {
        int crc = 255;
        for (int i = 0; i < length; i++)
        {
            crc ^= data[i];
            for (int j = 0; j < 8; j++)
                crc = (crc & 1) != 0 ? (crc >> 1) ^ 224 : crc >> 1;
        }
        return (byte)(255 - crc);
    }

    private static ushort Crc(List<byte> bytes, int start, int end)
    {
        int crc = 0;
        for (int i = start; i < end; i++)
        {
            crc ^= bytes[i] << 8;
            for (int bit = 0; bit < 8; bit++)
                crc = ((crc & 0x8000) != 0 ? (crc << 1) ^ 0x1021 : crc << 1) & 0xffff;
        }
        return (ushort)crc;
    }

    private void Data(DateTimeOffset time, bool fromBook, int channelId, Mux mux, int dlci,
                      byte[] data, int offset, int length)
    {
        int key = dlci * 2 + (fromBook ? 1 : 0);
        StreamState stream;
        if (!mux.Streams.TryGetValue(key, out stream))
        {
            stream = new StreamState();
            mux.Streams.Add(key, stream);
        }
        var bytes = stream.Bytes;
        for (int i = 0; i < length; i++) bytes.Add(data[offset + i]);

        // Consume complete frames and retain at most one incomplete SPP frame.
        // Embedded markers in a complete, verified frame never start another one.
        int pos = 0;
        while (pos < bytes.Count)
        {
            bool alternative = bytes[pos] == 0xfc;
            if (!alternative && bytes[pos] != 0xfd)
            {
                settings.Interrupt(time, channelId, dlci);
                pos++;
                continue;
            }
            if (bytes.Count - pos < 3) break;
            int header = bytes[pos + 1] | (bytes[pos + 2] << 8);
            int body = header & 0x3ff; // message id, payload, CRC16
            if (body < 3 || (header & ~0x33ff) != 0)
            {
                settings.Interrupt(time, channelId, dlci);
                pos++;
                continue;
            }
            int size = body + 4;
            if (bytes.Count - pos < size) break;
            int check = pos + size - 3;
            if (bytes[check + 2] != (alternative ? 0xcc : 0xdd) ||
                Crc(bytes, pos + 3, check) != (bytes[check] | (bytes[check + 1] << 8)))
            {
                settings.Interrupt(time, channelId, dlci);
                pos++;
                continue;
            }
            if (alternative) smepFrames++; else sppFrames++;
            int id = bytes[pos + 3];
            bool wireTypeBit = (header & 0x1000) != 0;
            int messageKey = id | (alternative ? 256 : 0) | (wireTypeBit ? 512 : 0);
            if ((header & 0x2000) != 0)
            {
                settings.Interrupt(time, channelId, dlci);
                stream.Fragments.Add(messageKey);
                fragmented++;
            }
            else if (stream.Fragments.Remove(messageKey))
            {
                settings.Interrupt(time, channelId, dlci);
                fragmented++; // Complete logical message would require preceding fragments.
            }
            else
            {
                int server = dlci >> 1;
                string service = "unconfirmed";
                // DLCI direction 0 names a server on the multiplexer's responder.
                // The SABM/UA handshake on DLCI 0 establishes who initiated.
                if (mux.Initiator.HasValue)
                {
                    bool serverIsBook = (dlci & 1) != 0 ? mux.Initiator.Value : !mux.Initiator.Value;
                    service = sdp.Service(serverIsBook, server);
                }
                StreamState opposite;
                bool overlap = stream.Fragments.Count != 0 || (mux.Streams.TryGetValue(key ^ 1, out opposite) &&
                    (opposite.Bytes.Count != 0 || opposite.Fragments.Count != 0));
                settings.Frame(time, fromBook, channelId, dlci, alternative, id, wireTypeBit,
                    bytes.GetRange(pos + 4, body - 3).ToArray(), service, overlap);
            }
            pos += size;
        }
        if (pos != 0) bytes.RemoveRange(0, pos);
    }

    private void FlushDlci(int channelId, Mux mux, int dlci)
    {
        settings.Reset(channelId, dlci);
        if (dlci == 0)
        {
            mux.Streams.Clear();
            mux.PendingOpener = null;
            mux.Initiator = null;
        }
        else
        {
            mux.Streams.Remove(dlci * 2);
            mux.Streams.Remove(dlci * 2 + 1);
        }
    }

    public void L2cap(DateTimeOffset time, bool fromBook, ushort psm, int channelId, byte[] payload)
    {
        if (payload == null) return;
        if (psm == 1) { sdp.Accept(time, fromBook, channelId, payload); return; }
        if (psm != 3) return;
        Mux mux;
        if (!muxes.TryGetValue(channelId, out mux))
        {
            mux = new Mux();
            muxes.Add(channelId, mux);
        }
        if (payload.Length < 4 || (payload[0] & 1) == 0)
        {
            malformed++;
            FlushDlci(channelId, mux, 0);
            return;
        }
        int dlci = payload[0] >> 2;
        int control = payload[1] & ~0x10;
        // SABM, UA, DISC and DM have no information field; their FCS covers
        // address, control and length. Their P/F bit is separate from the opcode.
        if (control == 0x2f || control == 0x63 || control == 0x43 || control == 0x0f)
        {
            if (payload.Length != 4 || payload[2] != 1 || FrameCheck(payload, 3) != payload[3])
            {
                malformed++;
                FlushDlci(channelId, mux, 0); // Address is not trusted after a header/FCS error.
                return;
            }
            if (control == 0x2f)
            {
                FlushDlci(channelId, mux, dlci);
                if (dlci == 0 && (payload[1] & 0x10) != 0 && (payload[0] & 2) != 0)
                    mux.PendingOpener = fromBook;
            }
            else if (control == 0x63 && dlci == 0 && mux.PendingOpener.HasValue &&
                     mux.PendingOpener.Value != fromBook && (payload[1] & 0x10) != 0 && (payload[0] & 2) != 0)
            {
                mux.Initiator = mux.PendingOpener;
                mux.PendingOpener = null;
            }
            else if (control == 0x63 || control == 0x43 || control == 0x0f)
                FlushDlci(channelId, mux, dlci);
            return;
        }
        if (control != 0xef || dlci == 0) return;
        if (FrameCheck(payload, 2) != payload[payload.Length - 1])
        {
            malformed++;
            FlushDlci(channelId, mux, 0);
            return;
        }
        int offset = 3;
        int length = payload[2] >> 1;
        if ((payload[2] & 1) == 0)
        {
            if (payload.Length < 5) { malformed++; FlushDlci(channelId, mux, dlci); return; }
            length |= payload[offset++] << 7;
        }
        int extra = payload.Length - (offset + length + 1);
        if (extra != 0 && (extra != 1 || (payload[1] & 0x10) == 0))
        {
            malformed++;
            FlushDlci(channelId, mux, dlci);
            return;
        }
        uiFrames++;
        if (length != 0) Data(time, fromBook, channelId, mux, dlci, payload, offset + extra, length);
    }

    public void Close(int channelId)
    {
        settings.Reset(channelId, 0);
        muxes.Remove(channelId);
        sdp.Close(channelId);
    }

    public void Finish()
    {
        output.WriteLine("RFCOMM data frames = {0}. Checksum-verified Samsung-format frames: regular {1}, alternative {2}.",
                         uiFrames, sppFrames, smepFrames);
        if (fragmented != 0 || malformed != 0)
            output.WriteLine("Skipped application fragments or tails = {0}. Malformed RFCOMM frames = {1}.", fragmented, malformed);
        settings.Finish();
        muxes.Clear();
    }
}
