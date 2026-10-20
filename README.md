# Pocket Link

A small USB-C adapter that lets a [Pocket](https://pocketide.com) bot hear and speak on an Android
phone's own calls, and (firmware 0.2) tap and type on the phone for it. The phone sees a USB headset, so Android routes the call's audio to it; a second
channel on the same plug carries that audio to the Pocket app, which streams it to the voice engine over
the phone's own internet. No Bluetooth, no Wi-Fi, no battery, nothing stored on the device.

**This is open hardware.** The board, the firmware, the USB protocol and the test tools are here so that
anyone can see exactly what the thing plugged into their phone does, build one, or make it work on a
phone we have not tried.

```
caller ⇄ phone (cellular / WhatsApp call)
           │  Android routes call audio to the "USB headset"
           ▼
   USB-C ⇄ Pocket Link (RP2040)
           │  interface 1–2: USB Audio (UAC 1.0) headset, mic in / headphones out
           │  interface 3:   vendor bulk data channel
           │  interface 4:   HID touch screen + keyboard (firmware 0.2): the app's taps and keystrokes
           ▼
   Pocket app (USB host API) ⇄ WebSocket ⇄ voice engine
```

| Folder | What |
|---|---|
| `revA/` | The first board: KiCad project, Gerbers, BOM, CPL, STEP, schematic PDF, and `source/design.py`, the generator that is the single source of truth. 31 × 16 mm, 4-layer, board-edge USB-C plug. Proven on real calls (Motorola edge 60, Android 16) on 2026-10-08. |
| `revB/` | The next board: the same circuit as a pod on the back of the phone with a short lead, two layers, under ₹500 to build. Plan and cost model; files follow. |
| `firmware/pocket-link-fw/` | RP2040 firmware (Rust): composite USB headset + data channel + HID touch screen/keyboard, 48 kHz ⇄ 16 kHz resampling, the data protocol. Prebuilt `pocket-link-fw.uf2`. |
| `firmware/pocket-link-fw/PROTOCOL.md` | USB descriptors and the app ⇄ adapter packet protocol. The contract the Pocket app implements. |
| `firmware/tools/` | `link_pc_test.py`: status, two-way loopback test and bootloader entry from a Linux PC. `link_input_bench.py`: tap, swipe and type on the phone through the adapter, over adb. |
| `firmware/hosttest/` | USB descriptor dump and validator; resampler frequency response. |
| `firmware/android-test/` | A bare Android test app (Java, no Gradle) that talks to the adapter and a local voice engine. Useful for bring-up on a new phone. |
| `COMPATIBILITY.md` | Which phones work. Please add yours. |

## Build one (DIY)

You do not need our board. Any RP2040 board works for a first test:

1. Hold BOOT and plug a Raspberry Pi Pico or Waveshare RP2040-Zero into a PC; copy `firmware/pocket-link-fw/pocket-link-fw.uf2` onto the `RPI-RP2` drive.
2. Run `python3 firmware/tools/link_pc_test.py status` (needs `pyusb numpy` and the udev rule in `firmware/README.md`). `loopback` must pass both ways.
3. Connect the board to the phone with a USB-C OTG cable, install the Pocket app, open **Account → Voice → Pocket Link**, and set it up. The app recognises the device by its USB identity.

A Pico on an OTG cable is a working Pocket Link. It is also a lever on your phone's port; the pod in `revB/` exists because of that.

## Licences

- Hardware (`revA/`, `revB/`): **CERN-OHL-P-2.0** (`LICENSE-HARDWARE.txt`). Permissive: build it, sell it, change it, keep the notice.
- Firmware, tools and the test app (`firmware/`): **Apache-2.0** (`LICENSE`). `third_party/usbd-audio` is MIT OR Apache-2.0 by its author, with our patches listed in its `PATCHES.md`.
- "Pocket" and "Pocket Link" are names of Pocket; a clone of the design is welcome, a clone of the name is not.

## USB identity

Rev A ships with the pid.codes **test** ID `1209:0001`. Before a public batch we apply for a real PID at
[pid.codes](https://pid.codes), which allocates them to open-source hardware; `PID-REQUEST.md` is the
application. Until then, anything you build with this firmware carries the test ID, which must not be sold.

## Contributing

Phone reports (`COMPATIBILITY.md`), firmware fixes and alternative boards are all welcome; see
`CONTRIBUTING.md`. Bring-up lessons so far: the headphones stream **must be stereo** (a mono USB output
makes Android 16's mixer abort audioserver), and the app should claim the device through a
`USB_DEVICE_ATTACHED` intent filter so Android offers "always" on the permission prompt.
