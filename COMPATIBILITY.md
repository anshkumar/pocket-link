# Phone compatibility

Pocket Link needs a phone that (1) routes call audio to a USB headset and (2) lets an app claim the
second USB interface while the system holds the audio one. Most Android 10+ phones do both; a few route
calls only to the earpiece, and some OEM dialers ignore USB headsets on cellular calls. Add a row for
every phone you try, including the ones that fail: a failure with a reason is the most useful row.

| Phone | Android | SoC | Board | Calls routed | App data channel | Notes | Date |
|---|---|---|---|---|---|---|---|
| Motorola edge 60 | 16 | MediaTek | RP2040-Zero, rev A firmware | ✓ both ways | ✓ | Mono headphones crashed audioserver on this phone; stereo output fixed it. Auto-answer, bot reply ~1–1.9 s. | 2026-10-08 |
| OnePlus Nord N6x (rooted) | 15 | — | — | n/a | n/a | Uses root mode (Magisk call-audio module), not the adapter. | 2026-10 |

How to test on a new phone, in order: `link_pc_test.py loopback` passes on a PC → the phone's USB settings
show "Pocket Link" when plugged in → a call to the phone switches audio to the headset (the earpiece goes
silent) → the Pocket app's Pocket Link card says "Connected · firmware …" → a bot answers a call from an
allowed number. Report the step that fails and the Android version, OEM skin and SoC.
