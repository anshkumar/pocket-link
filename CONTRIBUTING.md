# Contributing

- **Phone reports** go in `COMPATIBILITY.md`: one row per phone, with the step that failed if it failed.
- **Firmware**: `cd firmware/pocket-link-fw && cargo build --release`; the `.uf2` is produced by
  `tools/elf2uf2.py`. Keep the USB descriptors in `PROTOCOL.md` in step with the code, because the Pocket
  app is written against that document. A change to the protocol needs a version bump in the STATUS packet.
- **Hardware**: `revA/source/design.py` generates the schematic and the PCB; edit the generator, not the
  KiCad files, and re-run the verification in `revA/docs/verification.txt`.
- **Licences**: hardware contributions are CERN-OHL-P-2.0, everything else Apache-2.0. By sending a change
  you agree to those terms for it.
- Please do not send keys, tokens or recordings in issues. A call transcript with the numbers removed is fine.
