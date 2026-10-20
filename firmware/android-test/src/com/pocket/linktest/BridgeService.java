package com.pocket.linktest;

import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbManager;
import android.media.AudioDeviceInfo;
import android.media.AudioManager;
import android.os.IBinder;
import android.os.PowerManager;
import android.telephony.TelephonyManager;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.lang.reflect.Method;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * Bench-test bridge: Pocket Link adapter <-> Pocket voice engine WebSocket.
 *
 * Incoming call from the allowed number -> answer (Telecom API) -> Android routes call audio to the
 * adapter (USB headset) -> caller PCM arrives on the adapter data channel -> WebSocket (640-byte,
 * 20 ms, 16 kHz frames, same protocol as infra/bridge/pipewire_bridge.py) -> agent PCM comes back
 * -> paced at real time into the adapter -> caller hears the agent.
 */
public class BridgeService extends Service {
    public interface Ui {
        void log(String line);
        void status(String line);
    }

    public static volatile Ui ui;
    public static volatile boolean running;
    static final String ACTION_USB_PERMISSION = "com.pocket.linktest.USB_PERMISSION";
    private static final int FRAME = 640; // 20 ms @ 16 kHz mono S16LE

    private UsbManager usb;
    private UsbLink link;
    private volatile WsClient ws;
    private volatile boolean inCall, ownCall, sessionUp;
    private String url, token, allowed;
    private boolean autoAnswer, bridgeAll;
    private final ByteArrayOutputStream upAcc = new ByteArrayOutputStream();
    private final LinkedBlockingQueue<byte[]> upQueue = new LinkedBlockingQueue<byte[]>(500);
    private final Object agentLock = new Object();
    private byte[] agentBuf = new byte[16000 * 2 * 30];
    private int agentLen;
    private Thread pacer, sender;
    private PowerManager.WakeLock wake;
    private long upFrames, downFrames;

    static void post(String s) {
        String line = new SimpleDateFormat("HH:mm:ss", Locale.US).format(new Date()) + "  " + s;
        android.util.Log.i("PocketLink", s);
        Ui u = ui;
        if (u != null) u.log(line);
    }

    // ------------------------------------------------------------------ lifecycle
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        SharedPreferences p = getSharedPreferences("cfg", MODE_PRIVATE);
        url = p.getString("url", "ws://127.0.0.1:8793/audio");
        token = p.getString("token", "");
        allowed = digits(p.getString("allowed", ""));
        autoAnswer = p.getBoolean("autoAnswer", true);
        bridgeAll = p.getBoolean("bridgeAll", false);
        if (!running) {
            running = true;
            startForeground(1, notification("Waiting for Pocket Link and calls"));
            usb = (UsbManager) getSystemService(Context.USB_SERVICE);
            IntentFilter f = new IntentFilter(TelephonyManager.ACTION_PHONE_STATE_CHANGED);
            f.addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED);
            f.addAction(UsbManager.ACTION_USB_DEVICE_DETACHED);
            f.addAction(ACTION_USB_PERMISSION);
            registerReceiver(receiver, f);
            wake = ((PowerManager) getSystemService(POWER_SERVICE)).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "pocket:link");
            post("Service started. Engine " + url + (allowed.isEmpty() ? "" : ", allowed caller …" + tail(allowed)));
        }
        tryOpenLink();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        stopSession("service stopped");
        try {
            unregisterReceiver(receiver);
        } catch (Exception ignored) {
        }
        if (link != null) link.close();
        link = null;
        post("Service stopped");
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private Notification notification(String text) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        Notification.Builder b = new Notification.Builder(this);
        try { // API 26+: notification channel (compiled against API 23, so via reflection)
            Class<?> nc = Class.forName("android.app.NotificationChannel");
            Object ch = nc.getConstructor(String.class, CharSequence.class, int.class).newInstance("link", "Pocket Link", 2);
            NotificationManager.class.getMethod("createNotificationChannel", nc).invoke(nm, ch);
            Notification.Builder.class.getMethod("setChannelId", String.class).invoke(b, "link");
        } catch (Exception ignored) {
        }
        PendingIntent pi = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_IMMUTABLE);
        return b.setContentTitle("Pocket Link test").setContentText(text)
                .setSmallIcon(android.R.drawable.stat_sys_phone_call).setContentIntent(pi).setOngoing(true).build();
    }

    // ------------------------------------------------------------------ USB
    private void tryOpenLink() {
        if (link != null && link.isOpen()) return;
        UsbDevice d = UsbLink.find(usb);
        if (d == null) {
            post("Pocket Link not connected");
            return;
        }
        if (!usb.hasPermission(d)) {
            post("Requesting USB permission for Pocket Link");
            Intent i = new Intent(ACTION_USB_PERMISSION).setPackage(getPackageName());
            usb.requestPermission(d, PendingIntent.getBroadcast(this, 0, i, 0x02000000 /* FLAG_MUTABLE */));
            return;
        }
        try {
            link = UsbLink.open(usb, d, linkListener);
            post("Pocket Link opened (data channel claimed)");
            if (inCall && (ownCall || bridgeAll)) startSession();
        } catch (Exception e) {
            post("Open failed: " + e.getMessage());
        }
    }

    private final UsbLink.Listener linkListener = new UsbLink.Listener() {
        private long lastStatus;
        private long lastStatusLog;

        @Override
        public void onCallerPcm(byte[] buf, int off, int len) {
            if (!sessionUp) return;
            upAcc.write(buf, off, len);
            if (upAcc.size() >= FRAME) {
                byte[] all = upAcc.toByteArray();
                int whole = all.length - all.length % FRAME;
                for (int k = 0; k < whole; k += FRAME) {
                    byte[] fr = new byte[FRAME];
                    System.arraycopy(all, k, fr, 0, FRAME);
                    upQueue.offer(fr);
                }
                upAcc.reset();
                upAcc.write(all, whole, all.length - whole);
            }
        }

        @Override
        public void onStatus(int flags, int ma, int mi, int agentBufN, int callerBufN, long under, long over) {
            long now = System.currentTimeMillis();
            if (sessionUp && now - lastStatusLog >= 2000) {
                // Logged during calls: flags bit1 = phone plays into the headset, bit2 = phone records the
                // headset mic (the call's uplink), bit3 = agent audio queued on the adapter.
                lastStatusLog = now;
                android.util.Log.i("PocketLink", String.format(Locale.US,
                        "status flags=0x%x spk=%s mic=%s playing=%s agentBuf=%d callerBuf=%d under=%d over=%d sent=%d recv=%d",
                        flags, (flags & 2) != 0, (flags & 4) != 0, (flags & 8) != 0, agentBufN, callerBufN, under, over, upFrames, downFrames));
            }
            if (now - lastStatus < 900) return;
            lastStatus = now;
            Ui u = ui;
            if (u != null) {
                u.status(String.format(Locale.US,
                        "Adapter fw %d.%d | call audio routed: %s | agent audio: %s | buffers agent %d / caller %d | "
                                + "underflows %d overflows %d | sent %d recv %d frames",
                        ma, mi, (flags & 2) != 0 ? "YES" : "no", (flags & 8) != 0 ? "playing" : "idle",
                        agentBufN, callerBufN, under, over, upFrames, downFrames));
            }
        }

        @Override
        public void onLinkClosed(String why) {
            post("Pocket Link closed: " + why);
            stopSession("adapter removed");
        }
    };

    // ------------------------------------------------------------------ calls
    private final BroadcastReceiver receiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context c, Intent i) {
            String a = i.getAction();
            if (UsbManager.ACTION_USB_DEVICE_ATTACHED.equals(a) || ACTION_USB_PERMISSION.equals(a)) {
                tryOpenLink();
            } else if (UsbManager.ACTION_USB_DEVICE_DETACHED.equals(a)) {
                if (link != null) link.close();
                link = null;
                stopSession("adapter unplugged");
                post("Pocket Link unplugged");
            } else if (TelephonyManager.ACTION_PHONE_STATE_CHANGED.equals(a)) {
                onPhoneState(i.getStringExtra(TelephonyManager.EXTRA_STATE),
                        i.getStringExtra(TelephonyManager.EXTRA_INCOMING_NUMBER));
            }
        }
    };

    private void onPhoneState(String state, String number) {
        if (TelephonyManager.EXTRA_STATE_RINGING.equals(state)) {
            if (number == null) return; // the broadcast arrives twice; only one carries the number
            String n = digits(number);
            boolean ok = !allowed.isEmpty() && n.length() >= 10 && allowed.endsWith(n.substring(n.length() - 10));
            post("Incoming call from …" + tail(n) + (ok ? " (allowed)" : " (not allowed, ignoring)"));
            if (ok && autoAnswer) {
                if (link == null || !link.isOpen()) {
                    post("Not answering: Pocket Link is not connected");
                    return;
                }
                ownCall = true;
                answerCall();
            }
        } else if (TelephonyManager.EXTRA_STATE_OFFHOOK.equals(state)) {
            inCall = true;
            post("Call active");
            if (ownCall || bridgeAll) startSession();
        } else if (TelephonyManager.EXTRA_STATE_IDLE.equals(state)) {
            if (inCall) post("Call ended");
            inCall = false;
            ownCall = false;
            stopSession("call ended");
        }
    }

    private void answerCall() {
        try {
            Object tm = getSystemService("telecom");
            tm.getClass().getMethod("acceptRingingCall").invoke(tm);
            post("Answered (TelecomManager.acceptRingingCall)");
        } catch (Exception e) {
            post("Answer failed (grant 'Phone' permission?): " + e);
        }
    }

    private void endCall() {
        try {
            Object tm = getSystemService("telecom");
            Object r = tm.getClass().getMethod("endCall").invoke(tm);
            post("Hang up requested: " + r);
        } catch (Exception e) {
            post("Hang up failed: " + e);
        }
    }

    /** Prefer the adapter for call audio (API 31+ setCommunicationDevice; older: Android picks USB headsets itself). */
    private void routeToAdapter(boolean on) {
        AudioManager am = (AudioManager) getSystemService(AUDIO_SERVICE);
        try {
            if (!on) {
                AudioManager.class.getMethod("clearCommunicationDevice").invoke(am);
                return;
            }
            for (AudioDeviceInfo d : am.getDevices(AudioManager.GET_DEVICES_OUTPUTS)) {
                int t = d.getType();
                if (t == 22 /* TYPE_USB_HEADSET */ || t == AudioDeviceInfo.TYPE_USB_DEVICE) {
                    Method m = AudioManager.class.getMethod("setCommunicationDevice", AudioDeviceInfo.class);
                    post("Route call audio to " + d.getProductName() + " (type " + t + "): " + m.invoke(am, d));
                    return;
                }
            }
            post("Adapter not visible as an audio output yet");
        } catch (NoSuchMethodException e) {
            // Android < 12: USB headsets are selected automatically
        } catch (Exception e) {
            post("Routing call failed: " + e);
        }
    }

    // ------------------------------------------------------------------ session
    private synchronized void startSession() {
        if (sessionUp) return;
        if (link == null || !link.isOpen()) {
            post("Call active but Pocket Link is not open");
            return;
        }
        sessionUp = true;
        upFrames = downFrames = 0;
        upQueue.clear();
        upAcc.reset();
        synchronized (agentLock) {
            agentLen = 0;
        }
        link.control(UsbLink.CTRL_FLUSH);
        wake.acquire(30 * 60 * 1000L);
        routeToAdapter(true);
        sender = new Thread(new Runnable() {
            @Override
            public void run() {
                senderLoop();
            }
        }, "ws-send");
        pacer = new Thread(new Runnable() {
            @Override
            public void run() {
                pacerLoop();
            }
        }, "agent-pacer");
        pacer.setPriority(Thread.MAX_PRIORITY);
        sender.start();
        pacer.start();
        startForeground(1, notification("Bridging call to the voice agent"));
    }

    private synchronized void stopSession(String why) {
        if (!sessionUp) return;
        sessionUp = false;
        WsClient w = ws;
        ws = null;
        // close() sends a WebSocket close frame: network I/O, so never on the main thread (PHONE_STATE runs there).
        if (w != null) {
            final WsClient closing = w;
            new Thread(new Runnable() {
                @Override
                public void run() {
                    closing.close();
                }
            }, "ws-close").start();
        }
        if (sender != null) sender.interrupt();
        if (pacer != null) pacer.interrupt();
        routeToAdapter(false);
        if (wake != null && wake.isHeld()) wake.release();
        post("Session closed (" + why + "), sent " + upFrames + " / received " + downFrames + " frames");
        if (running) startForeground(1, notification("Waiting for Pocket Link and calls"));
    }

    private void senderLoop() {
        try {
            post("Connecting to voice engine " + url);
            ws = WsClient.connect(url, token, new WsClient.Listener() {
                @Override
                public void onBinary(byte[] data) {
                    synchronized (agentLock) {
                        int n = Math.min(data.length, agentBuf.length - agentLen);
                        System.arraycopy(data, 0, agentBuf, agentLen, n);
                        agentLen += n;
                    }
                }

                @Override
                public void onText(String text) {
                    try {
                        JSONObject o = new JSONObject(text);
                        String t = o.optString("type");
                        if ("clear".equals(t)) {
                            synchronized (agentLock) {
                                agentLen = 0;
                            }
                            UsbLink l = link;
                            if (l != null) l.control(UsbLink.CTRL_FLUSH);
                        } else if ("end".equals(t)) {
                            post("Agent ended the conversation");
                            if (ownCall) endCall();
                        } else if ("error".equals(t)) {
                            post("Agent error: " + o.optString("error"));
                        }
                    } catch (Exception ignored) {
                    }
                }

                @Override
                public void onClosed(String reason) {
                    post("Voice engine connection " + reason);
                }
            });
            post("Voice engine connected");
            while (sessionUp) {
                byte[] fr = upQueue.poll(200, TimeUnit.MILLISECONDS);
                WsClient w = ws;
                if (fr != null && w != null && w.isOpen()) {
                    w.sendBinary(fr);
                    upFrames++;
                }
            }
        } catch (InterruptedException ignored) {
        } catch (Exception e) {
            post("Voice engine error: " + e.getMessage());
        }
    }

    /** Feeds agent audio to the adapter at real time (20 ms per frame). */
    private void pacerLoop() {
        byte[] fr = new byte[FRAME];
        long next = System.nanoTime();
        try {
            while (sessionUp) {
                int n = 0;
                synchronized (agentLock) {
                    if (agentLen > 0) {
                        n = Math.min(FRAME, agentLen);
                        System.arraycopy(agentBuf, 0, fr, 0, n);
                        System.arraycopy(agentBuf, n, agentBuf, 0, agentLen - n);
                        agentLen -= n;
                    }
                }
                UsbLink l = link;
                if (n > 0 && l != null) {
                    l.sendPcm(fr, 0, n);
                    downFrames++;
                }
                next += 20_000_000L;
                long sleep = next - System.nanoTime();
                if (sleep > 0) Thread.sleep(sleep / 1_000_000L, (int) (sleep % 1_000_000L));
                else next = System.nanoTime();
            }
        } catch (InterruptedException ignored) {
        }
    }

    // ------------------------------------------------------------------ helpers
    static String digits(String s) {
        return s == null ? "" : s.replaceAll("\\D", "");
    }

    static String tail(String s) {
        return s.length() <= 4 ? s : s.substring(s.length() - 4);
    }
}
