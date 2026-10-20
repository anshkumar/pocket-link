#!/usr/bin/env python3
"""Pocket Link bench test from a Linux PC (no phone needed).

The PC plays the role of the phone: ALSA sees the adapter as a USB sound card, and this
script talks to the vendor data interface with pyusb, as the Pocket app would.

  pip install pyusb numpy        # and: sudo apt install alsa-utils
  # allow non-root access once:
  echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="0666"' | \
      sudo tee /etc/udev/rules.d/60-pocket-link.rules && sudo udevadm control --reload

  python3 link_pc_test.py status            # print device status packets
  python3 link_pc_test.py loopback          # full two-direction audio test (pass/fail)
  python3 link_pc_test.py bootloader        # reboot adapter into UF2 mode for a firmware update
"""
import struct
import subprocess
import sys
import threading
import time

import numpy as np
import usb.core
import usb.util

VID, PID = 0x1209, 0x0001
MAGIC, T_PCM, T_STATUS, T_CTRL = 0x50, 0x01, 0x02, 0x03


def open_link():
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        sys.exit('Pocket Link not found (is it plugged in and flashed?)')
    cfg = dev.get_active_configuration()
    intf = usb.util.find_descriptor(cfg, bInterfaceClass=0xFF, bInterfaceSubClass=0x50)
    if dev.is_kernel_driver_active(intf.bInterfaceNumber):
        dev.detach_kernel_driver(intf.bInterfaceNumber)
    usb.util.claim_interface(dev, intf.bInterfaceNumber)
    ep_in = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
    ep_out = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
    return dev, ep_in, ep_out


def parse(buf):
    i = 0
    while i + 4 <= len(buf) and buf[i] == MAGIC:
        t, n = buf[i + 1], buf[i + 2]
        yield t, bytes(buf[i + 4:i + 4 + n])
        i += 4 + n


def send_pcm(ep_out, pcm16k: bytes):
    pkts = bytearray()
    for k in range(0, len(pcm16k), 60):
        chunk = pcm16k[k:k + 60]
        pkts += bytes([MAGIC, T_PCM, len(chunk), 0]) + chunk
    # pack whole 64-byte-aligned packets into one transfer
    ep_out.write(bytes(pkts), timeout=1000)


def card_name():
    out = subprocess.run(['aplay', '-l'], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if 'Pocket Link' in line or 'Pocket' in line:
            return 'hw:' + line.split(':')[0].split()[-1] + ',0'
    sys.exit('ALSA card for Pocket Link not found (aplay -l)')


def tone(freq, secs, rate, amp=8000):
    t = np.arange(int(secs * rate)) / rate
    return (amp * np.sin(2 * np.pi * freq * t)).astype('<i2')


def dominant(x, rate):
    x = x.astype(float) - np.mean(x)
    if len(x) < rate // 10 or np.max(np.abs(x)) < 200:
        return 0.0, 0.0
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    f = np.argmax(spec) * rate / len(x)
    return f, float(np.sqrt(np.mean(x ** 2)))


def cmd_status():
    dev, ep_in, _ = open_link()
    end = time.time() + 5
    while time.time() < end:
        try:
            buf = ep_in.read(1024, timeout=600)
        except usb.core.USBTimeoutError:
            continue
        for t, p in parse(buf):
            if t == T_STATUS:
                flags, ma, mi, _, mf, sf, mu, so = struct.unpack('<BBBBHHII', p)
                print(f'fw {ma}.{mi} configured={flags & 1} phone->dev={flags >> 1 & 1} dev->phone={flags >> 2 & 1} '
                      f'playing={flags >> 3 & 1} agent_buf={mf} caller_buf={sf} underflows={mu} overflows={so}')


def cmd_loopback():
    dev, ep_in, ep_out = open_link()
    hw = card_name()
    print('ALSA device', hw)
    got = bytearray()
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                buf = ep_in.read(1024, timeout=100)
            except usb.core.USBTimeoutError:
                continue
            except usb.core.USBError:
                return  # the device was released at exit
            for t, p in parse(buf):
                if t == T_PCM:
                    got.extend(p)
    th = threading.Thread(target=reader, daemon=True)
    th.start()

    # 1) "caller" direction: PC plays 1 kHz at 48 kHz stereo into the headset, expect 1 kHz at 16 kHz on the data channel
    # The headphones are stereo (Android rejects a mono USB output); the device averages L and R.
    play = subprocess.Popen(['aplay', '-q', '-D', hw, '-f', 'S16_LE', '-r', '48000', '-c', '2', '-t', 'raw'],
                            stdin=subprocess.PIPE)
    play.communicate(np.repeat(tone(1000, 2.0, 48000), 2).tobytes())
    time.sleep(0.3)
    f1, r1 = dominant(np.frombuffer(bytes(got[3200:]), '<i2'), 16000)
    print(f'caller path : expected 1000 Hz, got {f1:.0f} Hz, rms {r1:.0f}')

    # 2) "agent" direction: send 600 Hz at 16 kHz on the data channel, record the headset mic at 48 kHz
    rec = subprocess.Popen(['arecord', '-q', '-D', hw, '-f', 'S16_LE', '-r', '48000', '-c', '1', '-t', 'raw',
                            '-d', '3'], stdout=subprocess.PIPE)
    time.sleep(0.3)
    sig = tone(600, 2.0, 16000).tobytes()
    for k in range(0, len(sig), 640):          # paced at real time, 20 ms chunks
        send_pcm(ep_out, sig[k:k + 640])
        time.sleep(0.02)
    out, _ = rec.communicate()
    f2, r2 = dominant(np.frombuffer(out, '<i2')[24000:], 48000)
    print(f'agent path  : expected  600 Hz, got {f2:.0f} Hz, rms {r2:.0f}')
    stop.set()
    ok = abs(f1 - 1000) < 30 and abs(f2 - 600) < 30
    print('LOOPBACK', 'PASS' if ok else 'FAIL')
    sys.exit(0 if ok else 1)


def cmd_bootloader():
    dev, _, ep_out = open_link()
    try:
        ep_out.write(bytes([MAGIC, T_CTRL, 1, 0, 0x02]), timeout=500)
    except usb.core.USBError:
        pass
    print('Adapter rebooting into the RPI-RP2 drive; copy the new .uf2 onto it.')


if __name__ == '__main__':
    {'status': cmd_status, 'loopback': cmd_loopback, 'bootloader': cmd_bootloader}.get(
        sys.argv[1] if len(sys.argv) > 1 else 'status', cmd_status)()
