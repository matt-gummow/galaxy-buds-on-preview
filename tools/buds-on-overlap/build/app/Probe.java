package dev.budson.overlap.probe;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothA2dp;
import android.bluetooth.BluetoothHeadset;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;

/** Returns only the current connection states of the named, already bonded peer. */
public final class Probe extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        boolean audio = "dev.budson.overlap.probe.READ_AUDIO".equals(action);
        if (!isOrderedBroadcast() || (!audio && !"dev.budson.overlap.probe.READ".equals(action))) return;
        String peer = intent.getStringExtra("peer");
        String request = intent.getStringExtra("request");
        if (!BluetoothAdapter.checkBluetoothAddress(peer) || request == null ||
                !request.matches("[0-9a-f]{32}")) return;

        PendingResult pending = goAsync();
        BluetoothAdapter adapter = null;
        BluetoothDevice bonded = null;
        try {
            BluetoothManager manager = context.getSystemService(BluetoothManager.class);
            if (manager != null) adapter = manager.getAdapter();
            if (adapter != null && adapter.isEnabled()) {
                // The public API can associate a driver-provided address with a bonded peer.
                // Do not enumerate other devices or try establishing a Bluetooth connection.
                BluetoothDevice device = adapter.getRemoteDevice(peer);
                if (device.getBondState() == BluetoothDevice.BOND_BONDED) bonded = device;
            }
        } catch (RuntimeException unavailable) {
            bonded = null;
        }
        if (bonded == null) {
            complete(pending, request, audio, "unknown", "unknown", "unknown", "unknown");
            return;
        }
        new Snapshot(context.getApplicationContext(), adapter, bonded, pending, request, audio).start();
    }

    private static void complete(PendingResult pending, String request, boolean audio, String a2dp,
                                 String headset, String mediaPlaying, String callAudio) {
        if (audio) {
            pending.setResultData("BO2:" + request + ":" + a2dp + ":" + headset + ":" + mediaPlaying + ":" + callAudio);
        } else {
            pending.setResultData("BO1:" + request + ":" + a2dp + ":" + headset);
        }
        pending.finish();
    }

    private static final class Snapshot implements BluetoothProfile.ServiceListener {
        private final Handler main = new Handler(Looper.getMainLooper());
        private final Context context;
        private final BluetoothAdapter adapter;
        private final BluetoothDevice device;
        private final PendingResult pending;
        private final String request;
        private final boolean readAudio;
        private String mediaPlaying = "unknown", callAudio = "unknown";
        private String a2dp, headset;
        private boolean finished;
        private final Runnable deadline = new Runnable() {
            @Override public void run() { finish(); }
        };

        Snapshot(Context context, BluetoothAdapter adapter, BluetoothDevice device,
                 PendingResult pending, String request, boolean readAudio) {
            this.context = context;
            this.adapter = adapter;
            this.device = device;
            this.pending = pending;
            this.request = request;
            this.readAudio = readAudio;
        }

        void start() {
            main.postDelayed(deadline, 1800);
            open(BluetoothProfile.A2DP);
            open(BluetoothProfile.HEADSET);
        }

        private void open(int profile) {
            try {
                if (adapter.getProfileProxy(context, this, profile)) return;
            } catch (RuntimeException unavailable) {
                // Profile service is unavailable or the app lacks Nearby devices permission.
            }
            record(profile, "unknown");
        }

        @Override public void onServiceConnected(int profile, BluetoothProfile proxy) {
            String result = "unknown";
            try {
                if (!finished && adapter.isEnabled() && device.getBondState() == BluetoothDevice.BOND_BONDED) {
                    int state = proxy.getConnectionState(device);
                    if (state == BluetoothProfile.STATE_CONNECTED) {
                        result = "connected";
                        if (readAudio) readAudioState(profile, proxy);
                    }
                    if (state == BluetoothProfile.STATE_DISCONNECTED) result = "disconnected";
                }
            } catch (RuntimeException unavailable) {
                result = "unknown";
            } finally {
                try { adapter.closeProfileProxy(profile, proxy); }
                catch (RuntimeException unavailable) { /* Service already closed. */ }
            }
            record(profile, result);
        }

        private void readAudioState(int profile, BluetoothProfile proxy) {
            // A false audio result includes failure on some Android versions. Only a positive value confirms a route.
            try {
                if (profile == BluetoothProfile.A2DP && proxy instanceof BluetoothA2dp)
                    mediaPlaying = ((BluetoothA2dp) proxy).isA2dpPlaying(device) ? "yes" : "unconfirmed";
                if (profile == BluetoothProfile.HEADSET && proxy instanceof BluetoothHeadset)
                    callAudio = ((BluetoothHeadset) proxy).isAudioConnected(device) ? "yes" : "unconfirmed";
            } catch (RuntimeException unavailable) { /* Keep the successful profile query. */ }
        }

        @Override public void onServiceDisconnected(int profile) {
            record(profile, "unknown");
        }

        private void record(int profile, String value) {
            if (finished) return;
            if (profile == BluetoothProfile.A2DP && a2dp == null) a2dp = value;
            if (profile == BluetoothProfile.HEADSET && headset == null) headset = value;
            if (a2dp != null && headset != null) finish();
        }

        private void finish() {
            if (finished) return;
            finished = true;
            main.removeCallbacks(deadline);
            complete(pending, request, readAudio, a2dp == null ? "unknown" : a2dp,
                    headset == null ? "unknown" : headset, mediaPlaying, callAudio);
        }
    }
}

