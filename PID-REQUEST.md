# pid.codes request

pid.codes allocates USB product IDs under vendor ID `0x1209` to open-source hardware. The request is a
pull request against `pidcodes/pidcodes.github.com` adding two files. Eligibility (met by this
repository): public source with modifiable PCB design files and firmware, both under recognised
open licences, with the licence files present.

1. `org/pocket/index.md`

```
---
layout: org
title: Pocket
site: https://pocketide.com/
---
Pocket makes AI teammates that work from a phone. Pocket Link is its open USB-C adapter that lets a bot
hear and speak on an Android phone's own calls.
```

2. `1209/C417/index.md` (`0xC417` was unused on https://pid.codes/1209/ on 2026-10-20; re-check before sending):

```
---
layout: pid
title: Pocket Link
owner: pocket
license: CERN-OHL-P-2.0 (hardware), Apache-2.0 (firmware)
site: https://pocketide.com/pocket-link
source: https://github.com/anshkumar/pocket-link
---
USB-C adapter for Android phones: a USB Audio Class 1.0 headset (mic in, stereo headphones out) plus a
vendor bulk data channel, on an RP2040. The phone routes call audio to the headset interfaces; the Pocket
app claims the data interface and carries the audio to and from a voice agent. Firmware in Rust.
```

After allocation: change the PID in the firmware's USB descriptor and in `firmware/pocket-link-fw/PROTOCOL.md`
(which still says the test ID `1209:0001`) in the same commit, and rebuild the `.uf2`.

Submitted 2026-10-20 as https://github.com/pidcodes/pidcodes.github.com/pull/1326 (from the fork anshkumar/pidcodes.github.com, two commits on master).
