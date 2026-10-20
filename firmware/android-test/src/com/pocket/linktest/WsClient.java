package com.pocket.linktest;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URI;
import java.nio.charset.Charset;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Locale;

import javax.net.ssl.SSLSocketFactory;

/**
 * Minimal RFC 6455 WebSocket client (ws:// and wss://), enough for the Pocket voice engine:
 * binary PCM frames both ways, JSON text events from the server, ping/pong and close.
 */
public final class WsClient {
    public interface Listener {
        void onBinary(byte[] data);
        void onText(String text);
        void onClosed(String reason);
    }

    private static final Charset UTF8 = Charset.forName("UTF-8");
    private final Socket socket;
    private final InputStream in;
    private final OutputStream out;
    private final SecureRandom rnd = new SecureRandom();
    private volatile boolean closed;

    private WsClient(Socket s) throws IOException {
        socket = s;
        in = s.getInputStream();
        out = s.getOutputStream();
    }

    public static WsClient connect(String url, String bearerToken, final Listener listener) throws IOException {
        URI u = URI.create(url);
        boolean tls = "wss".equalsIgnoreCase(u.getScheme());
        int port = u.getPort() > 0 ? u.getPort() : (tls ? 443 : 80);
        Socket s = tls ? SSLSocketFactory.getDefault().createSocket() : new Socket();
        s.connect(new InetSocketAddress(u.getHost(), port), 5000);
        s.setTcpNoDelay(true);
        final WsClient c = new WsClient(s);
        byte[] keyRaw = new byte[16];
        c.rnd.nextBytes(keyRaw);
        String key = android.util.Base64.encodeToString(keyRaw, android.util.Base64.NO_WRAP);
        String path = (u.getRawPath() == null || u.getRawPath().isEmpty()) ? "/" : u.getRawPath();
        if (u.getRawQuery() != null) path += "?" + u.getRawQuery();
        StringBuilder req = new StringBuilder();
        req.append("GET ").append(path).append(" HTTP/1.1\r\n");
        req.append("Host: ").append(u.getHost()).append(':').append(port).append("\r\n");
        req.append("Upgrade: websocket\r\nConnection: Upgrade\r\n");
        req.append("Sec-WebSocket-Key: ").append(key).append("\r\n");
        req.append("Sec-WebSocket-Version: 13\r\n");
        if (bearerToken != null && !bearerToken.isEmpty()) {
            req.append("Authorization: Bearer ").append(bearerToken).append("\r\n");
        }
        req.append("\r\n");
        c.out.write(req.toString().getBytes(UTF8));
        c.out.flush();
        String status = c.readLine();
        if (status == null || !status.contains(" 101")) {
            s.close();
            throw new IOException("WebSocket handshake failed: " + status);
        }
        String accept = null;
        String line;
        while ((line = c.readLine()) != null && !line.isEmpty()) {
            int i = line.indexOf(':');
            if (i > 0 && line.substring(0, i).trim().toLowerCase(Locale.US).equals("sec-websocket-accept")) {
                accept = line.substring(i + 1).trim();
            }
        }
        try {
            MessageDigest sha = MessageDigest.getInstance("SHA-1");
            byte[] d = sha.digest((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").getBytes(UTF8));
            String want = android.util.Base64.encodeToString(d, android.util.Base64.NO_WRAP);
            if (!want.equals(accept)) {
                s.close();
                throw new IOException("Bad Sec-WebSocket-Accept");
            }
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IOException(e);
        }
        Thread t = new Thread(new Runnable() {
            @Override
            public void run() {
                c.readLoop(listener);
            }
        }, "ws-read");
        t.setDaemon(true);
        t.start();
        return c;
    }

    private String readLine() throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        int ch;
        while ((ch = in.read()) != -1) {
            if (ch == '\n') break;
            if (ch != '\r') b.write(ch);
        }
        if (ch == -1 && b.size() == 0) return null;
        return new String(b.toByteArray(), UTF8);
    }

    private void readFully(byte[] b, int off, int len) throws IOException {
        while (len > 0) {
            int n = in.read(b, off, len);
            if (n < 0) throw new IOException("EOF");
            off += n;
            len -= n;
        }
    }

    private void readLoop(Listener l) {
        String reason = "closed";
        ByteArrayOutputStream msg = new ByteArrayOutputStream();
        int msgOp = 0;
        try {
            byte[] h = new byte[2];
            while (!closed) {
                readFully(h, 0, 2);
                boolean fin = (h[0] & 0x80) != 0;
                int op = h[0] & 0x0F;
                long len = h[1] & 0x7F;
                if (len == 126) {
                    byte[] e = new byte[2];
                    readFully(e, 0, 2);
                    len = ((e[0] & 0xFF) << 8) | (e[1] & 0xFF);
                } else if (len == 127) {
                    byte[] e = new byte[8];
                    readFully(e, 0, 8);
                    len = 0;
                    for (int i = 0; i < 8; i++) len = (len << 8) | (e[i] & 0xFF);
                }
                if (len > 4 * 1024 * 1024) throw new IOException("frame too large");
                byte[] p = new byte[(int) len];
                readFully(p, 0, p.length);
                if (op == 0x8) {
                    reason = "server closed";
                    break;
                } else if (op == 0x9) {
                    send(0xA, p);
                    continue;
                } else if (op == 0xA) {
                    continue;
                }
                if (op != 0) {
                    msgOp = op;
                    msg.reset();
                }
                msg.write(p, 0, p.length);
                if (fin) {
                    byte[] m = msg.toByteArray();
                    msg.reset();
                    if (msgOp == 0x2) l.onBinary(m);
                    else if (msgOp == 0x1) l.onText(new String(m, UTF8));
                }
            }
        } catch (IOException e) {
            reason = closed ? "closed" : ("error: " + e.getMessage());
        }
        close();
        l.onClosed(reason);
    }

    public void sendBinary(byte[] data) throws IOException {
        send(0x2, data);
    }

    public void sendText(String s) throws IOException {
        send(0x1, s.getBytes(UTF8));
    }

    private synchronized void send(int op, byte[] p) throws IOException {
        if (closed) throw new IOException("closed");
        ByteArrayOutputStream f = new ByteArrayOutputStream(p.length + 14);
        f.write(0x80 | op);
        if (p.length < 126) {
            f.write(0x80 | p.length);
        } else if (p.length < 65536) {
            f.write(0x80 | 126);
            f.write(p.length >> 8);
            f.write(p.length);
        } else {
            f.write(0x80 | 127);
            for (int i = 7; i >= 0; i--) f.write((int) ((long) p.length >> (8 * i)));
        }
        byte[] mask = new byte[4];
        rnd.nextBytes(mask);
        f.write(mask, 0, 4);
        byte[] m = new byte[p.length];
        for (int i = 0; i < p.length; i++) m[i] = (byte) (p[i] ^ mask[i & 3]);
        f.write(m, 0, m.length);
        out.write(f.toByteArray());
        out.flush();
    }

    public void close() {
        if (closed) return;
        try {
            send(0x8, new byte[0]);
        } catch (IOException ignored) {
        }
        closed = true;
        try {
            socket.close();
        } catch (IOException ignored) {
        }
    }

    public boolean isOpen() {
        return !closed;
    }
}
