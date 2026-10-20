# Pocket Link — firmware, PC test tool and Android test app

| Folder | What |
|---|---|
| `pocket-link-fw/` | RP2040 firmware (Rust). Prebuilt: **`pocket-link-fw.uf2`** |
| `pocket-link-fw/PROTOCOL.md` | USB interfaces and the app ⇄ adapter data protocol |
| `tools/link_pc_test.py` | Bench test from a Linux PC: status, two-way audio loopback (pass/fail), bootloader |
| `android-test/` | Android test app. Prebuilt: **`PocketLinkTest.apk`** |
| `hosttest/` | Host-side checks: USB descriptor dump + validator, resampler frequency response |

Status (2026-10-08): **works end to end on a real call** with a Waveshare RP2040-Zero on a Motorola Edge 60
(Android 16, MediaTek). An allowed caller is auto-answered, call audio is routed to the adapter in both directions,
and the bot holds a conversation (replies start ~1.5 s after the caller stops; the caller reported very good quality).
PC loopback passes in both directions. Pocket Link boards are next.

Lessons from bring-up:
* The headphones **must be stereo**. A mono USB output makes Android 16's mixer abort audioserver
  (`HAL channel mask 0x1 not supported for mixed output`), the headset never becomes available and the call stays
  on the earpiece. The firmware advertises 48 kHz stereo and averages L/R; the mic stays mono.
* Android's USB permission dialog appears on every plug-in for this test app. The real app should use a
  `USB_DEVICE_ATTACHED` intent filter with a device filter so the user can tick "always".

## 1. Flash the adapter (or an RP2040-Zero / Pico)

1. Hold **BOOT** while plugging it into the PC. On a blank Pocket Link board this happens automatically. The
   **RPI-RP2** drive appears.
2. Copy `pocket-link-fw.uf2` onto it. The board reboots as **"Pocket Link"**.
3. Later updates: `python3 tools/link_pc_test.py bootloader`, then copy the new `.uf2`.

On a Pico the green LED is solid when connected and blinks while call audio flows. The RP2040-Zero has no plain LED,
so use the status command instead.

## 2. Test on the Linux PC (no phone)

```sh
pip install pyusb numpy
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="0666"' | \
  sudo tee /etc/udev/rules.d/60-pocket-link.rules && sudo udevadm control --reload
aplay -l | grep -i pocket          # should list the "Pocket Link" USB audio card
python3 tools/link_pc_test.py status
python3 tools/link_pc_test.py loopback   # expect: LOOPBACK PASS
```

`loopback` plays 1 kHz into the adapter's "headphones" and checks it arrives on the data channel.
Then it sends 600 Hz on the data channel and checks it comes out of the adapter's "microphone".

## 3. Test on the phone

1. Install `android-test/PocketLinkTest.apk` on the Motorola (`adb install PocketLinkTest.apk`). It is signed with a
   test key; Android will warn that it's built for an older Android version. Accept.
2. On the PC, start the voice engine exactly as for the Bluetooth test
   (`node infra/bridge/local_agent.mjs /private/config.json`).
3. The phone's USB-C port is now taken by the adapter, so connect ADB over Wi-Fi (Developer options → Wireless
   debugging → `adb pair` / `adb connect`), then run `adb reverse tcp:8793 tcp:8793`.
   This makes `ws://127.0.0.1:8793/audio` on the phone reach the PC.
4. Open **Pocket Link Test**. Enter the token from the `bridge-token` file and the allowed caller number. Leave
   auto-answer on and press **Start**. Grant the Phone / Call log permissions.
5. Plug the adapter into the phone and allow USB access. The log shows "Pocket Link opened".
6. Call from the allowed number. The app answers, Android routes the call to the adapter
   ("call audio routed: YES"), and the bot talks.

Notes
* WhatsApp: tick "Also bridge calls I answer myself", answer manually, and the bridge starts. There is no WhatsApp
  auto-answer.
* While the adapter is plugged in, the phone's own earpiece and mic are not used for calls. That is expected.
* If "call audio routed" stays "no" during a call, pick the headset in the dialer's audio-route menu once. Then report
  the phone model: that's a routing quirk to handle in the app.

## Building from source

Firmware (any OS with Rust):
```sh
rustup target add thumbv6m-none-eabi     # rust-toolchain.toml also requests it
cd pocket-link-fw && cargo build --release --target thumbv6m-none-eabi
python3 tools/elf2uf2.py target/thumbv6m-none-eabi/release/pocket-link-fw pocket-link-fw.uf2
```
* Dependencies are pinned in `Cargo.lock`.
* `third_party/usbd-audio` is a patched copy: it writes UAC 1.0 9-byte endpoint descriptors (see `PATCHES.md`).

Android app (no Gradle; Debian/Ubuntu packages `android-sdk android-sdk-platform-23 dalvik-exchange apksigner`):
```sh
cd android-test && ./build_apk.sh
```
* The app compiles against API 23 and reaches newer APIs through reflection: answering calls, hanging up, picking the
  call audio route, notification channels.
* It targets API 28. For the real Pocket app this logic should move into a native module in `apps/mobile`.

Host checks (Rust on the PC):
```sh
cd hosttest && cargo run --release && python3 check_descriptors.py   # expect DESCRIPTORS OK
```

## Known gaps / next steps
* First run on hardware: confirm Android enumerates it as a USB headset, the app can claim the data interface during
  a call (the key unknown), and check end-to-end latency.
* USB ID `1209:0001` is the pid.codes test PID. Register a real one before shipping.
* No volume control (UAC feature unit) yet. Android uses fixed gain, which is fine for a bot.
* Serial number is fixed (`PL-REVA`). Read the flash unique ID for per-unit serials later.
