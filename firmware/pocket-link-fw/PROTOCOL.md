# Pocket Link — USB interface and data protocol (v1)

## USB identity

| Field | Value |
|---|---|
| VID:PID | `1209:0001` (pid.codes **test** ID; register a real PID before shipping) |
| Manufacturer / Product | `Pocket` / `Pocket Link` |
| Device class | `EF/02/01` (composite with IAD) |
| Power | bus-powered, 100 mA declared, about 25 mA actual |

## Interfaces

| # | What | Details |
|---|---|---|
| 0 | Audio Control (UAC 1.0) | Input terminal 1 = **Microphone (0x0201)**, output terminal 6 = **Headphones (0x0302)**. Android classifies the device as a USB headset |
| 1 | Audio Streaming, device → phone ("microphone") | alt 1: iso IN EP 0x81, async, 48 kHz, mono, S16LE, 96 B/ms. Carries the **agent's voice** into the call |
| 2 | Audio Streaming, phone → device ("headphones") | alt 1: iso OUT EP 0x01, adaptive, 48 kHz, **stereo**, S16LE (L and R averaged to mono). Carries the **caller's voice**. Must be stereo: Android 16's mixer aborts audioserver on a mono USB output ("HAL channel mask 0x1 not supported for mixed output") |
| 3 | Vendor data, class `FF/50/01` | bulk IN EP 0x82 and bulk OUT EP 0x02, 64-byte packets. Claimed by the Pocket app |
| 4 | HID (firmware 0.2+) | interrupt IN EP 0x83, 1 ms. Report ID 1 touch screen, 2 keyboard, 3 consumer control. The phone takes it as a touch screen on its own display plus a keyboard; the app feeds it (see `0x04 HID` below). Android hides the on-screen keyboard while a USB keyboard is attached (Settings → Physical keyboard → "Use on-screen keyboard" brings it back) |

The device has no physical microphone or speaker. It loops audio between interfaces 1/2 and interface 3,
resampling 48 kHz ↔ 16 kHz with a 48-tap low-pass FIR (flat to 6 kHz, ≥ 70 dB rejection above 10 kHz).

## Data-channel packets (interface 3)

Every packet is `[0x50, type, len, seq] + payload` with `len ≤ 60`. A USB transfer may hold several
packets back to back, so parse them in sequence using `len`.

| type | Direction | Payload |
|---|---|---|
| `0x01` PCM | device → app | caller audio, 16 kHz mono S16LE, normally 30 samples (60 B) per packet. Only sent while the phone is playing call audio into the headset (interface 2 alt 1) |
| `0x01` PCM | app → device | agent audio, 16 kHz mono S16LE, even length ≤ 60 B. Buffered up to 200 ms. Playback starts once 20 ms is buffered; on underflow the device sends silence and re-buffers |
| `0x02` STATUS | device → app | every 500 ms, or on request. 16 bytes: `flags, fw_major, fw_minor, 0, mic_fill u16, spk_fill u16, mic_underflows u32, spk_overflows u32` (all LE). `flags`: bit0 USB configured, bit1 phone→device audio active (call audio routed to the headset), bit2 device→phone audio active, bit3 agent audio currently playing |
| `0x03` CTRL | app → device | 1 byte: `0x01` flush agent audio (barge-in / "clear"), `0x02` reboot into the USB bootloader (firmware update), `0x03` send status now |

| `0x04` HID | app → device | one finished HID report, 1–16 bytes, report ID first. Queued (16 deep) and sent on the HID interrupt endpoint in order. Touch: `[1, tip \| inRange<<1, contactId, x u16, y u16, contactCount]` with x/y 0..32767 across the display in its current rotation (one finger: contactId 0, contactCount 1; lift = same report with tip 0). The descriptor carries Contact ID and Contact Count so the kernel's hid-multitouch driver takes it and marks it a direct touch screen; the generic HID driver would make Android treat it as a pointer. Keyboard: `[2, modifiers, 0, key1..key6]` (boot layout, HID usage codes). Consumer: `[3, usage u16]`, e.g. 0x0223 AC Home → Android HOME, 0x0224 AC Back → BACK, 0x01A2 → recents. The device never composes input itself; the Pocket app sequences down/move/up and press/release (`LinkInput.kt`) |

`seq` is an 8-bit counter on device → app packets. Gaps show dropped packets.

**Packing rule (app → device):** the device parses each 64-byte USB packet on its own. When you send several
packets in one bulk transfer, every packet except the last must be exactly 64 bytes (4-byte header + 60-byte payload).
For example, a 20 ms chunk of 640 B goes out as 10 × [hdr + 60 B] + [hdr + 40 B].

## Timing

* Caller audio: about 1 packet per 1.9 ms (16 000 samples/s ÷ 30). The app should read with a buffer of 512–1024 bytes and a
  20–50 ms timeout.
* Agent audio: the app should write in 20 ms chunks (640 B → 11 packets). The device trims its buffer to 200 ms, so a
  burst of TTS audio must be paced by the app at real time, not dumped all at once.
* Added latency: about 20 ms device buffering + 1 ms USB frames + the app's WebSocket path.
