# pid.codes request (draft)

pid.codes allocates USB PIDs under vendor ID `0x1209` to open-source hardware projects. The request is a
pull request against https://github.com/pid.codes/pid.codes adding a file, once this folder is published
at a public URL. Fill in the PID they assign and the repository link.

```
---
layout: pid
pid: 0x____          # assigned on allocation
vendor: "Pocket"
product: "Pocket Link"
description: "USB-C phone call adapter: UAC 1.0 headset plus a vendor bulk data channel, RP2040"
license: "Hardware CERN-OHL-P-2.0, firmware Apache-2.0"
owner: "Pocket"
site: "https://pocketide.com/pocket-link"
source: "https://github.com/<org>/pocket-link"
---
```

Checklist before sending: the public repository contains the board files, the firmware source and the
licences above; the firmware's `PROTOCOL.md` still says `1209:0001` and must be updated to the new PID in
the same change as the firmware descriptor.
