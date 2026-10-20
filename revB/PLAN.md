# Pocket Link rev B — under ₹500 a board, and what comes after

Written 2026-10-20 from the rev A files, the PCB Power quote (INQ649465) and JLCPCB's published
assembly fees. Prices marked ≈ are LCSC/JLC list prices as last seen and must be re-checked in the
quote tool before ordering; the structure of the cost is what matters here.

## 1. Why rev A costs ₹3,750 and rev B can cost ₹300

Rev A's price is not its parts (≈ ₹185). It is:

| Cost driver in rev A | What it costs | Rev B change |
|---|---|---|
| 4-layer 0.8 mm ENIG board, needed only for the 0.5 mm-pitch board-edge plug | ₹1,161/board at 6 | **2-layer 1.0 mm HASL**: the plug moves onto a cable |
| Board-edge plug hand-soldered after SMT | labour + a failure point | **Pre-molded USB-C pigtail on a 6-pin JST-SH**: machine-placed, no hand soldering |
| Turnkey sourcing with MOQ packs and "independent supplier" markups | ₹1,492/board | **JLC basic parts** (no loading fee) or a consigned LCSC basket |
| Six boards carrying the whole NRE | ₹19,048 / 6 | **Batches of 100**: NRE becomes ₹2/board |
| A rigid 36 mm dongle that breaks ports | returns | Pod on the back of the phone, lead into the port |

## 2. Rev B: the pod

Same proven circuit as rev A (RP2040, 2 MB QSPI flash, 12 MHz crystal, AP2112K LDO, USBLC6 ESD),
same firmware, same USB identity. What changes is mechanical and manufacturing:

- **Board:** 2-layer, 1.0 mm, HASL, about 30 × 16 mm. The RP2040's QFN-56 and 0.4 mm pitch are fine on
  two layers (the Pico is two layers); the ground pad gets its vias; USB D+/D− run as a short pair.
- **Connector:** a 6-pin JST-SH 1.0 mm (SMD, horizontal) carrying VBUS, GND, D+, D−, CC (Rd lives on the
  board), shield. The pigtail is a bought part: USB-C male plug, over-molded, 60–80 mm of 28 AWG 5-core
  cable, JST-SH on the other end. One bought part replaces one hand-soldered part.
- **Shell:** 36 × 20 × 7 mm two-part shell with a cable exit and strain relief; a 3M VHB pad on the back
  for the phone or its case. 3D-printed (MJF nylon) for the first batches; a steel mould only above ~1,000.
- **Status:** the rev A green LED stays; a light pipe to the shell top.
- **Test:** every pod is plugged into a PC once (`tools/link_pc_test.py status` + loopback); that step also
  flashes the firmware, so JLC never has to program anything.

### Cost model, 100 pods

| Item | ≈ USD | ≈ INR | Notes |
|---|---|---|---|
| RP2040 + W25Q16 + crystal + LDO + ESD + passives + LED | 1.27 | 107 | rev A BOM less the plug |
| JST-SH 6-pin SMD | 0.05 | 4 | |
| USB-C pigtail, over-molded, JST-SH end | 0.35 | 30 | custom cable assembly, MOQ 100–500 |
| PCB, 2-layer, 100 pcs panelised | 0.25 | 21 | |
| JLC economic assembly: ≈130 joints × $0.0016 + setup $8.21 + stencil $1.53 + extended-part loading ≈ $15, spread over 100 | 0.46 | 39 | fees from JLC's published schedule |
| Shell, MJF nylon, two parts | 1.00 | 84 | drops to ≈ $0.25 with a mould |
| VHB pad, light pipe, cable tie | 0.10 | 8 | |
| Shipping + customs, spread | 0.40 | 34 | |
| **Total** | **≈ 3.9** | **≈ ₹330** | under ₹500 with margin for price checks |

At 1,000 pods (mould, bigger panels, one shipment): ≈ $2.5 ≈ ₹210.

### The same pod on CH32X035 (rev B′, later)

CH32X035 (WCH, RISC-V, USB FS device, 62 KB flash, no external flash or crystal, USB-PD PHY on chip,
QFN-20/TSSOP-20). Parts fall to ≈ $0.55, the board to two dozen placements, the pod to ≈ ₹270 at 100
and ≈ ₹160 at 1,000. The price of admission is a firmware port (USB audio class + vendor bulk on WCH's
USB stack, C, a few weeks) and a new bring-up on real phones. Do it when the order is 1,000, and do it
for rev C's charge-through, where the PD PHY is the whole point.

## 3. Rev C: charge-through ("Link Dock")

The desk phone that answers all day must charge while the pod is in. Add a USB-C **receptacle** to the
pod: the charger plugs into the pod, the pod into the phone. Electrically the pod stays the USB device
for data and becomes the **power source** for the phone, which is a USB-PD power-role swap (what desk
docks do). The CH32X035 runs the PD negotiation and the audio/data device from one chip; a 5 V/3 A
path, a load switch, and the PD firmware are the additions. Same shell plus one connector.

## 4. Other designs worth building

**Link Snap (carry, ₹+120).** Keep the pod, but put a magnetic breakaway USB-C pair between the lead and
the phone: the small nub stays in the port flush with the phone, the lead ends in the magnetic plug.
A snag pulls the magnet apart instead of the port; charging works through the same nub with a matching
tip. These are a commodity (24-pin, USB 2.0 data rated); the pod does not change.

**Link Air (no port at all, ₹600–800).** An ESP32 (classic Bluetooth + BLE) module presents itself to the
phone as a **Bluetooth hands-free headset**; the phone routes call audio to it like any headset. The module
Opus-encodes the audio and sends it to the Pocket app over BLE (≈ 24 kb/s each way) and plays the bot's
reply into the headset channel. No USB port used, the phone charges freely, battery for a day, and it is the
first Pocket Link that could work with an **iPhone** (iOS allows a companion app over BLE while the phone
treats the module as a headset). ESP-IDF ships the HFP client profile; the risk is audio quality through
HFP's narrowband/mSBC codec and the app's background BLE budget. The same module can skip the phone and
stream to the relay over Wi-Fi where there is Wi-Fi, which is the bridge box the Voice screen already pairs.

**Link Zero (no hardware, inbound only).** Forward busy/unanswered calls from the SIM to a cloud number the
bot answers (Twilio today; an Indian cloud-telephony number later): `**67*number#` and `**61*number#`
on most Indian networks. Callers still dial the person's number; the hardware cost is zero; outbound
still needs a Link. This belongs on the site as the free way in.

**Link DIY (zero manufacturing).** Publish the firmware `.uf2` for any RP2040 board. A Waveshare
RP2040-Zero (≈ ₹250 in India) plus a USB-C OTG cable is a working Pocket Link for makers, counsellors'
IT friends and reviewers; every DIY unit is a test on a phone we do not own.

**Link Cable (rev C in a cable).** Once rev C's PD pass-through works, the whole pod can live in the
over-mold of a 1 m USB-C-to-USB-C cable: the phone end holds the board, the other end goes to the charger.
Nothing to stick on, nothing to carry; it is the user's charging cable. Needs the mould.

## 5. Order of work

1. Ship rev A with a 10 cm USB-C extension (this week).
2. Rev B pod on RP2040: board from `design.py` (two layers, JST-SH), pigtail quote (MOQ 100), MJF shell;
   100 pods ≈ ₹33,000 landed.
3. Link Zero on the site now (it is software).
4. Link Snap as a variant of rev B (a different pigtail, nothing else).
5. CH32X035 port when the order is 1,000; rev C and Link Cable on it.
6. Link Air as a separate product once rev B sells, because it opens the iPhone.
