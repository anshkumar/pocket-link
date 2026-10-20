"""Parse and sanity-check the USB descriptors the firmware produces (dumped by the host test)."""
import struct, sys
d = open('device.bin', 'rb').read()
c = open('config.bin', 'rb').read()
ok = True
def fail(m):
    global ok; ok = False; print('FAIL:', m)
assert d[0] == 18 and d[1] == 1
bcd, cls, sub, proto, mps, vid, pid = struct.unpack('<HBBBBHH', d[2:12])
print(f'device: USB {bcd:04x} class {cls:02x}/{sub:02x}/{proto:02x} ep0 {mps} vid:pid {vid:04x}:{pid:04x} configs {d[17]}')
if (cls, sub, proto) != (0xEF, 0x02, 0x01): fail('composite device must be EF/02/01 for IAD')
total = struct.unpack('<H', c[2:4])[0]
if total != len(c): fail(f'wTotalLength {total} != {len(c)}')
print(f'config: total {total}, interfaces {c[4]}, attr {c[7]:02x}, maxpower {c[8]*2} mA')
i = 0; ifaces = set(); terminals = []; eps = []; cur = None
while i < len(c):
    L, T = c[i], c[i + 1]
    if L == 0 or i + L > len(c): fail(f'bad descriptor length at {i}'); break
    b = c[i:i + L]
    if T == 0x0B: print(f'  IAD first={b[2]} count={b[3]} class {b[4]:02x}/{b[5]:02x}')
    elif T == 0x04:
        cur = (b[2], b[3]); ifaces.add(b[2])
        print(f'  IF {b[2]} alt {b[3]} eps {b[4]} class {b[5]:02x}/{b[6]:02x}/{b[7]:02x}')
    elif T == 0x24:
        sub = b[2]
        if cur and cur[0] == 0 or (cur and b[2] in (2, 3) and L >= 9 and cur[1] == 0):
            if sub == 2:  # input terminal
                tt = struct.unpack('<H', b[4:6])[0]; terminals.append(('IT', b[3], tt)); print(f'    input terminal id {b[3]} type {tt:04x} ch {b[7]}')
            elif sub == 3:
                tt = struct.unpack('<H', b[4:6])[0]; terminals.append(('OT', b[3], tt)); print(f'    output terminal id {b[3]} type {tt:04x} src {b[7]}')
            elif sub == 1: print(f'    AC header bcdADC {struct.unpack("<H", b[3:5])[0]:04x} total {struct.unpack("<H", b[5:7])[0]} streams {b[7]} -> {list(b[8:])}')
        if cur and cur[0] != 0 and sub == 2 and L >= 8 and b[3] == 1:
            ch, ss, bits, nf = b[4], b[5], b[6], b[7]
            rates = [int.from_bytes(b[8 + 3 * k:11 + 3 * k], 'little') for k in range(nf)]
            print(f'    format: {ch} ch, {ss} B/sample, {bits} bit, rates {rates}')
    elif T == 0x05:
        addr, attr, mps, iv = b[2], b[3], struct.unpack('<H', b[4:6])[0], b[6]
        kinds = {1: 'iso', 2: 'bulk', 3: 'int'}
        sync = {0: 'none', 1: 'async', 2: 'adaptive', 3: 'sync'}[(attr >> 2) & 3]
        eps.append((cur, addr, attr & 3, mps))
        print(f'    EP {addr:02x} {kinds.get(attr & 3)} sync={sync} mps {mps} interval {iv} (len {L})')
        if (attr & 3) == 1 and L != 9: fail('UAC1 isochronous endpoint descriptor must be 9 bytes')
    i += L
# checks
tts = {t for _, _, t in terminals}
if 0x0201 not in tts: fail('no microphone input terminal')
if not (tts & {0x0302, 0x0402}): fail('no headphones/headset output terminal')
iso = [e for e in eps if e[2] == 1]
if len(iso) != 2: fail('expected 2 isochronous endpoints')
for e in iso:
    if e[3] < 96: fail(f'iso mps {e[3]} too small for 48 kHz 16-bit')
bulk = [e for e in eps if e[2] == 2]
if len(bulk) != 2: fail('expected 2 bulk endpoints')
if any(e[0][1] != 0 for e in bulk): fail('bulk endpoints should be on alt 0 of the vendor interface')
print('Android: input-headset (mic) =', 0x0201 in tts, ' output-headset (headphones) =', bool(tts & {0x0302, 0x0402}))
print('DESCRIPTORS', 'OK' if ok else 'FAILED')
sys.exit(0 if ok else 1)
