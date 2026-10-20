package com.pocket.linktest;

import android.hardware.usb.UsbConstants;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbDeviceConnection;
import android.hardware.usb.UsbEndpoint;
import android.hardware.usb.UsbInterface;
import android.hardware.usb.UsbManager;

/**
 * Talks to the Pocket Link vendor data interface (class FF/50/01) while Android's audio
 * stack uses the adapter's USB-headset interfaces. Protocol: see firmware PROTOCOL.md.
 */
public final class UsbLink {
    public static final int VID = 0x1209;
    public static final int PID = 0x0001;
    static final int MAGIC = 0x50, T_PCM = 1, T_STATUS = 2, T_CTRL = 3;
    public static final int CTRL_FLUSH = 1, CTRL_BOOTLOADER = 2, CTRL_STATUS = 3;

    public interface Listener {
        /** Caller audio, 16 kHz mono S16LE. */
        void onCallerPcm(byte[] buf, int off, int len);
        void onStatus(int flags, int fwMajor, int fwMinor, int agentBuf, int callerBuf, long underflows, long overflows);
        void onLinkClosed(String why);
    }

    private final UsbDeviceConnection conn;
    private final UsbInterface intf;
    private final UsbEndpoint epIn, epOut;
    private volatile boolean running = true;
    private final Object writeLock = new Object();

    private UsbLink(UsbDeviceConnection c, UsbInterface i, UsbEndpoint in, UsbEndpoint out) {
        conn = c;
        intf = i;
        epIn = in;
        epOut = out;
    }

    public static UsbDevice find(UsbManager um) {
        for (UsbDevice d : um.getDeviceList().values()) {
            if (d.getVendorId() == VID && d.getProductId() == PID) return d;
        }
        return null;
    }

    /** Opens and claims the data interface. Caller must already hold USB permission. */
    public static UsbLink open(UsbManager um, UsbDevice dev, final Listener l) {
        UsbInterface data = null;
        for (int i = 0; i < dev.getInterfaceCount(); i++) {
            UsbInterface it = dev.getInterface(i);
            if (it.getInterfaceClass() == 0xFF && it.getInterfaceSubclass() == 0x50) data = it;
        }
        if (data == null) throw new IllegalStateException("data interface not found (old firmware?)");
        UsbEndpoint in = null, out = null;
        for (int i = 0; i < data.getEndpointCount(); i++) {
            UsbEndpoint e = data.getEndpoint(i);
            if (e.getType() != UsbConstants.USB_ENDPOINT_XFER_BULK) continue;
            if (e.getDirection() == UsbConstants.USB_DIR_IN) in = e;
            else out = e;
        }
        UsbDeviceConnection c = um.openDevice(dev);
        if (c == null) throw new IllegalStateException("openDevice failed (permission?)");
        if (!c.claimInterface(data, true)) {
            c.close();
            throw new IllegalStateException("claimInterface failed");
        }
        final UsbLink link = new UsbLink(c, data, in, out);
        Thread t = new Thread(new Runnable() {
            @Override
            public void run() {
                link.readLoop(l);
            }
        }, "link-read");
        t.setPriority(Thread.MAX_PRIORITY);
        t.start();
        link.control(CTRL_STATUS);
        return link;
    }

    private void readLoop(Listener l) {
        byte[] buf = new byte[1024];
        int errors = 0;
        String why = "closed";
        while (running) {
            int n = conn.bulkTransfer(epIn, buf, buf.length, 50);
            if (n < 0) {
                // -1 is also returned on a plain timeout; only give up on persistent failure
                if (++errors > 400 && conn.getRawDescriptors() == null) {
                    why = "device gone";
                    break;
                }
                continue;
            }
            errors = 0;
            int i = 0;
            while (i + 4 <= n && (buf[i] & 0xFF) == MAGIC) {
                int t = buf[i + 1] & 0xFF;
                int len = buf[i + 2] & 0xFF;
                int p = i + 4;
                if (p + len > n) break;
                if (t == T_PCM) {
                    l.onCallerPcm(buf, p, len);
                } else if (t == T_STATUS && len >= 16) {
                    l.onStatus(buf[p] & 0xFF, buf[p + 1] & 0xFF, buf[p + 2] & 0xFF, u16(buf, p + 4), u16(buf, p + 6),
                            u32(buf, p + 8), u32(buf, p + 12));
                }
                i = p + len;
            }
        }
        running = false;
        l.onLinkClosed(why);
    }

    private static int u16(byte[] b, int o) {
        return (b[o] & 0xFF) | ((b[o + 1] & 0xFF) << 8);
    }

    private static long u32(byte[] b, int o) {
        return (b[o] & 0xFFL) | ((b[o + 1] & 0xFFL) << 8) | ((b[o + 2] & 0xFFL) << 16) | ((b[o + 3] & 0xFFL) << 24);
    }

    /** Send agent audio (16 kHz mono S16LE). Packs 60-byte payloads into 64-byte packets. */
    public boolean sendPcm(byte[] pcm, int off, int len) {
        len &= ~1;
        int pkts = (len + 59) / 60;
        byte[] out = new byte[pkts * 4 + len];
        int o = 0;
        for (int k = 0; k < len; k += 60) {
            int c = Math.min(60, len - k);
            out[o] = (byte) MAGIC;
            out[o + 1] = (byte) T_PCM;
            out[o + 2] = (byte) c;
            out[o + 3] = 0;
            System.arraycopy(pcm, off + k, out, o + 4, c);
            o += 4 + c;
        }
        synchronized (writeLock) {
            return conn.bulkTransfer(epOut, out, o, 200) == o;
        }
    }

    public boolean control(int cmd) {
        byte[] p = {(byte) MAGIC, (byte) T_CTRL, 1, 0, (byte) cmd};
        synchronized (writeLock) {
            return conn.bulkTransfer(epOut, p, p.length, 200) == p.length;
        }
    }

    public void close() {
        running = false;
        try {
            conn.releaseInterface(intf);
        } catch (Exception ignored) {
        }
        conn.close();
    }

    public boolean isOpen() {
        return running;
    }
}
