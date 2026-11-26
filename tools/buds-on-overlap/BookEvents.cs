using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;

namespace BudsOverlap
{
    public sealed class BookEvent
    {
        public DateTime Utc { get; private set; }
        public string Kind { get; private set; }
        public string State { get; private set; }
        internal BookEvent(DateTime utc, string kind, byte state)
        {
            Utc = utc;
            Kind = kind;
            State = state != 0 ? "Connected" : "Disconnected";
        }
    }

    public static class BookEvents
    {
        // bthdef.h: GUID_BLUETOOTH_HCI_EVENT / GUID_BLUETOOTH_L2CAP_EVENT.
        internal static readonly Guid Hci = new Guid("fc240062-1541-49be-b463-84c4dcd7bf7f");
        internal static readonly Guid L2cap = new Guid("7eae4030-b709-4aa8-ac55-e953829c9daa");
        private static readonly object Gate = new object();
        private static readonly Queue<BookEvent> Events = new Queue<BookEvent>();
        private static volatile bool monitoring;
        private static IntPtr radio, registration;
        private static readonly NotifyCallback Callback = Receive;
        private const int DeviceHandleFilter = 1, DeviceCustomEvent = 6;

        // CM_NOTIFY_FILTER's union can also hold WCHAR InstanceId[MAX_DEVICE_ID_LEN=200].
        [StructLayout(LayoutKind.Explicit, Size = 416)]
        private struct Filter
        {
            [FieldOffset(0)] public uint Size;
            [FieldOffset(8)] public int Type;
            [FieldOffset(16)] public IntPtr Target;
        }

        [UnmanagedFunctionPointer(CallingConvention.Winapi)]
        private delegate uint NotifyCallback(IntPtr token, IntPtr context, int action, IntPtr data, uint size);

        [DllImport("bthprops.cpl", ExactSpelling = true, SetLastError = true)]
        private static extern IntPtr BluetoothFindFirstRadio(ref uint size, out IntPtr handle);
        [DllImport("bthprops.cpl", ExactSpelling = true, SetLastError = true)]
        private static extern int BluetoothFindNextRadio(IntPtr find, out IntPtr handle);
        [DllImport("bthprops.cpl", ExactSpelling = true)]
        private static extern int BluetoothFindRadioClose(IntPtr find);
        [DllImport("kernel32.dll", ExactSpelling = true)]
        private static extern int CloseHandle(IntPtr handle);
        [DllImport("cfgmgr32.dll", ExactSpelling = true)]
        private static extern uint CM_Register_Notification(ref Filter filter, IntPtr context,
            NotifyCallback callback, out IntPtr token);
        [DllImport("cfgmgr32.dll", ExactSpelling = true)]
        private static extern uint CM_Unregister_Notification(IntPtr token);

        private static IntPtr OpenSingleRadio()
        {
            uint size = 4;
            IntPtr first;
            IntPtr find = BluetoothFindFirstRadio(ref size, out first);
            if (find == IntPtr.Zero) return IntPtr.Zero;
            try
            {
                IntPtr second;
                if (BluetoothFindNextRadio(find, out second) == 0)
                {
                    if (Marshal.GetLastWin32Error() == 259) return first;
                }
                else CloseHandle(second);
                CloseHandle(first);
                return IntPtr.Zero;
            }
            finally { BluetoothFindRadioClose(find); }
        }

        public static string Status { get { return monitoring ? "Monitoring" : "Unavailable"; } }
        public static void Start()
        {
            if (registration != IntPtr.Zero) return;
            try
            {
                radio = OpenSingleRadio();
                if (radio == IntPtr.Zero) return;
                var filter = new Filter { Size = (uint)Marshal.SizeOf(typeof(Filter)), Type = DeviceHandleFilter, Target = radio };
                monitoring = true;
                if (CM_Register_Notification(ref filter, IntPtr.Zero, Callback, out registration) == 0) return;
                registration = IntPtr.Zero;
            }
            catch (DllNotFoundException) { }
            catch (EntryPointNotFoundException) { }
            monitoring = false;
            ReleaseRadio();
        }

        private static void ReleaseRadio()
        {
            IntPtr handle = Interlocked.Exchange(ref radio, IntPtr.Zero);
            if (handle != IntPtr.Zero) CloseHandle(handle);
        }

        // Decode only the two fixed Bluetooth notifications on the pinned target. No payload
        // or identifier is ever queued. Time is OS callback delivery, not a hardware timestamp.
        internal static BookEvent Parse(DateTime utc, ulong target, IntPtr record, uint size)
        {
            // CM_NOTIFY_EVENT_DATA device-handle header: type, reserved, GUID, name offset, data size.
            const int body = 32;
            if (target == 0 || record == IntPtr.Zero || size < body || Marshal.ReadInt32(record) != DeviceHandleFilter)
                return null;
            int len = Marshal.ReadInt32(record, 28);
            if (len < 10 || (uint)len > size - body || unchecked((ulong)Marshal.ReadInt64(record, body)) != target)
                return null;
            Guid guid = (Guid)Marshal.PtrToStructure(IntPtr.Add(record, 8), typeof(Guid));
            if (guid == Hci)
            {
                byte type = Marshal.ReadByte(record, body + 8);
                // Windows bthdef.h HCI_CONNECTION_TYPE values, distinct from wire link types.
                if (type == 1 || type == 2)
                    return new BookEvent(utc, type == 1 ? "Classic" : "CallAudio", Marshal.ReadByte(record, body + 9));
            }
            else if (guid == L2cap && len >= 12 && Marshal.ReadInt16(record, body + 8) == 0x19)
                return new BookEvent(utc, "MediaChannel", Marshal.ReadByte(record, body + 10));
            return null;
        }

        private static uint Receive(IntPtr token, IntPtr context, int action, IntPtr data, uint size)
        {
            if (action == 2 || action == 4 || action == 5) // query-remove, removal pending/complete
            {
                monitoring = false;
                ReleaseRadio();
                return 0;
            }
            if (action != DeviceCustomEvent || !monitoring) return 0;
            DateTime now = DateTime.UtcNow;
            BookTarget selected = BookCache.Target;
            if (selected == null) return 0;
            BookEvent observed = Parse(now, selected.Number, data, size);
            if (observed != null)
            {
                lock (Gate) Events.Enqueue(observed);
            }
            return 0;
        }

        public static BookEvent[] Drain()
        {
            lock (Gate)
            {
                var result = Events.ToArray();
                Events.Clear();
                return result;
            }
        }

        public static void Stop()
        {
            monitoring = false;
            // Never unregister from inside the callback. This call waits for in-flight callbacks.
            if (registration != IntPtr.Zero)
            {
                CM_Unregister_Notification(registration);
                registration = IntPtr.Zero;
            }
            ReleaseRadio();
            lock (Gate) Events.Clear();
            BookCache.Clear();
        }
    }
}
