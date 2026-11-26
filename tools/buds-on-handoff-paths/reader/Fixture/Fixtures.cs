using System.Runtime.InteropServices;

namespace Windows.Devices.Bluetooth.Advertisement
{
    // Inert type names simulate the contracts referenced by a managed Windows package.
    public class BluetoothLEAdvertisementWatcher { public virtual void Start() { } public virtual void Stop() { } }
    public class BluetoothLEAdvertisementPublisher { public virtual void Start() { } }
}

namespace TestInputs
{
    using Windows.Devices.Bluetooth.Advertisement;
    internal static class BudsAutoSwitch
    {
        public static async Task OnRequestAsync(BluetoothLEAdvertisementWatcher watcher)
        {
            await Task.Yield();
            Shared<int>.DoWork(watcher);
        }
        // A reference inside an accessor is not automatically a switch entry point.
        public static BluetoothLEAdvertisementPublisher UnrelatedProperty
        {
            get { var p = new BluetoothLEAdvertisementPublisher(); p.Start(); return p; }
        }
    }

    internal static class Shared<T>
    {
        public static void DoWork(BluetoothLEAdvertisementWatcher watcher)
        {
            watcher.Start();
            Native.Formatter();
            DataSink<string>("SM-U600");
        }
        public static void DataSink<U>(U value) { GC.KeepAlive(value); DeviceInfo.GetMdeVersion(); }
    }

    internal static class DeviceInfo
    {
        public static void GetMdeVersion() { }
    }

    internal static class Native
    {
        [DllImport("DllBudsMsgFmt.dll", EntryPoint = "FixtureOnly")] public static extern void Formatter();
    }

    internal static class TransferPreferences
    {
        public static int BudsAutoSwitch
        {
            get { Action callback = OnNotification; GC.KeepAlive(callback); return 0; }
        }
        private static void OnNotification() { new BluetoothLEAdvertisementWatcher().Stop(); }
    }

    internal static class Unrelated
    {
        public static void OtherModel(BluetoothLEAdvertisementPublisher publisher)
        {
            publisher.Start();
            GC.KeepAlive("Galaxy Buds On");
        }
        public static void DecoyStrings()
        {
            GC.KeepAlive("BluetoothLEAdvertisementPublisher");
            GC.KeepAlive("MDE_VERSION_suffix");
        }
    }
}
