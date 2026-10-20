# Pocket Link — rev A

A small USB-C dongle that plugs into the phone. The phone sees it as a **USB headset**,
so Android routes call audio to it. It also exposes a **data channel** that the Pocket app uses to stream
that audio to and from the voice agent over the phone's own internet.
There is no Bluetooth, no Wi-Fi and no battery.

Status: **design complete, DRC clean, not yet fabricated or tested.**

## Size and cost

* PCB **31 × 16 mm**, 0.8 mm thick. With the plug and a shell, about 36 × 18 × 6 mm.
* Parts: **≈ $2.20 (≈ ₹185) per adapter** at LCSC 100-pc prices.
  Prototype run of 5 assembled at JLCPCB is roughly $40–60 total (PCB + setup + parts + shipping).
  Check the real figure in the JLC quote.

## How it works

```
caller ⇄ phone (cellular / WhatsApp call)
           │  Android routes call audio to the "USB headset"
           ▼
   USB-C ⇄ Pocket Link (RP2040)
           │  interface 1: USB Audio (UAC) headset, 16 kHz mono speaker + mic
           │  interface 2: vendor bulk data
           ▼
   Pocket app (USB host API) ⇄ WebSocket ⇄ voice agent
```

The firmware is a TinyUSB composite device:
* Speaker stream (caller's voice) → forwarded to the app on the data interface.
* Data from the app (agent's voice) → played into the microphone stream, so the caller hears the agent.
* The app answers and hangs up calls itself (Android `ANSWER_PHONE_CALLS`). No ADB needed.

## Circuit (see `docs/Pocket-Link-revA-schematic.pdf`)

| Ref | Part | LCSC | Notes |
|---|---|---|---|
| J1 | Molex 105444-0001 USB-C **plug**, board-edge straddle | C134082 | Alt: SHOU HAN TYPE-C 24P GTJB. **Needs 0.8 mm PCB** |
| U1 | RP2040 | C2040 | USB 1.1 device. Support circuit per the RP2040 hardware design guide |
| U2 | W25Q16JVSNIQ 2 MB QSPI flash | C2456211 | Firmware |
| U3 | AP2112K-3.3 LDO | C51118 | Phone VBUS → 3.3 V, about 25 mA load |
| U4 | USBLC6-2SC6 | C7519 | ESD on D+/D− |
| Y1 | 12 MHz 3225 crystal + 2 × 33 pF, 1 kΩ on XOUT | C9002 | |
| R1 | 5.1 kΩ on CC | C25905 | Tells the phone a USB device is attached, so it supplies 5 V |
| D1 | Green status LED (GPIO25) | C72043 | |
| TP1–3 | Back-side pads: BOOT, GND, 3V3 | — | |

The SWD debug pins are not brought out. Firmware loads over USB, and debugging happens on any
RP2040 dev board running the same firmware.

## Board

* 4 layers, **0.8 mm**: L1 signal, L2 GND, L3 +3V3, L4 signal + GND pour.
* 0.1 mm min clearance and 0.127 mm min track. Both are within JLCPCB's standard 4-layer capability. The
  USB-C plug's 0.5 mm-pitch pads need this.
* 0.3 / 0.6 mm vias. 5 vias in the RP2040 ground pad.
* Verification (`docs/verification.txt`):
  * schematic and PCB both match `source/design.py` (21 nets, 34 parts)
  * KiCad DRC: **0 violations, 0 unconnected**
  * Gerbers re-read independently: 11 layers, outline 31 × 16 mm

## Ordering (JLCPCB)

1. Gerbers: `fab/Pocket-Link-revA-gerbers.zip`. Settings: 4 layers, **0.8 mm thickness**, JLC04081H-3313 stackup (or
   whatever JLC offers for 0.8 mm 4-layer), ENIG recommended for the fine-pitch plug and QFN.
2. Assembly (top side): `fab/BOM_JLCPCB.csv` + `fab/CPL_JLCPCB.csv`. **Check rotations in JLC's preview**,
   especially U1 pin 1, U2, U3, U4, Y1 and D1.
3. **The USB-C plug J1 is not in the JLC BOM or CPL.** It straddles the board edge with pads on both sides,
   so solder it after assembly (hand or hot-air), or ask JLC for manual soldering. Order C134082 along with the
   boards.
4. Small boards: ask JLC to panelize (e.g. 2 × 3) to stay above their minimum assembly size.

## First power-up

1. Plug into a Linux PC first (USB-C to USB-C cable, or a USB-A to USB-C female adapter). A blank board
   shows up as the **RPI-RP2** drive. Drag the firmware `.uf2` onto it.
2. `lsusb` / `aplay -l` should show a USB audio card plus the vendor interface. Run a PC loopback test.
3. Plug into the Motorola, install the Pocket test app, and call it from the allowed number.
4. To re-enter the bootloader later: short **BT** to **G** on the back while plugging in.

## Risks / next steps

| Risk | Plan |
|---|---|
| Whether the app can use the data interface while Android uses the audio part | First firmware test. Fallbacks need firmware changes only (e.g. a HID data channel) |
| Some phones need special USB audio formats (48 kHz) | Firmware offers 48 kHz too and resamples internally |
| Charging through the adapter (v2) | Needs a USB-PD pass-through controller and a female USB-C. Planned for rev B |
| Enclosure | A simple 2-part shell like a USB-C to 3.5 mm adapter, next step after the board fits |

## Files

* `kicad/`: KiCad 7 project with schematic, PCB and local footprints (QFN-56 with 0.3 mm vias)
* `fab/`: Gerbers + drill files, JLC BOM/CPL, full BOM with MPNs and cost, STEP 3D model
* `docs/`: schematic PDF, assembly + layer PDF, top/bottom previews, DRC report, verification results
* `source/`: Python generators. `design.py` is the single source of truth

## Cost reality check (PCB Power quote INQ649465, 7 Oct 2026, 6 boards)

| Line | Quote | Per board | Why |
|---|---|---|---|
| PCB fabrication (4-layer, 0.8 mm, ENIG, 2 panels of 3) | ₹6,966 | ₹1,161 | Panel NRE spread over 6 boards; a 2-layer board would roughly halve this |
| Assembly (30 SMD + 1 QFN, top side) | ₹3,132 | ₹522 | Reasonable for a tiny run |
| Component sourcing (turnkey) | ₹8,950 | ₹1,492 | The outlier. Parts are ≈ $2.20 (≈ ₹185) per board at LCSC; the quote carries minimum pack quantities (32 × 33 pF for 12 used), "independent supplier" markups on the RP2040, flash, crystal and passives (no warranty, 3–5 week lead), one part from Robu, and the LED was **not available and not priced** |
| Total before GST | ₹19,048 | ₹3,175 | ≈ ₹3,750 per adapter with GST, for six |

So the BOM is not the problem; the sourcing route and the batch size are. What to do:

1. **Consign the parts.** Order one LCSC/DigiKey basket yourself (10 sets ≈ ₹1,500 shipped, every part in stock, warranted) and give PCB Power assembly only. That alone cuts the per-board cost from ₹3,175 to about ₹1,900.
2. **Or order at JLCPCB** with the files in `fab/` (4-layer 0.8 mm ENIG, 5 boards + assembly ≈ $40–60 all in, plus Indian customs ≈ ₹1,000–1,500): roughly a quarter of the PCB Power price for the same six boards, because the parts come from their own LCSC shelf.
3. **Rev B goes to two layers** (the board-edge plug is the only reason for four) and a pre-molded cable-mount plug, which removes the one hand-soldered part. Fabrication then drops to the ₹300–500 per board range in tens, and under ₹100 in hundreds.
4. **Don't change the MCU for cost yet.** RP2040 + flash + crystal are ₹90 of the ₹185 parts; CH32X035 saves about ₹60 a board at the price of a firmware port. Worth it at a thousand units, and then for its on-chip USB-PD PHY (charge-through in rev C), not for the ₹60.

## Carrying it without breaking it (stopgap for rev A)

Rev A is a 36 mm rigid body hanging off the phone's USB-C receptacle: a 10 N snag at the tip is a 0.36 N·m moment on the port, enough to crack the plug or the phone's socket. Until rev B (pod on the back of the phone, 6–8 cm lead with strain relief), ship every rev A with a short **USB-C male-to-female extension (≈ 10 cm)**. USB audio and the vendor bulk channel pass through an extension; the dongle then hangs on a cable instead of a lever. Rev C adds a USB-C female for charge-through (PD power-role swap; CH32X035 has the PD PHY on chip).
