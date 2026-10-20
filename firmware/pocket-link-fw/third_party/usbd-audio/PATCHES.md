Vendored from crates.io usbd-audio 0.4.0 (MIT). Changes for Pocket Link:
- Isochronous endpoint descriptors are written in the 9-byte UAC 1.0 form (bRefresh, bSynchAddress)
  instead of the 7-byte form (strict hosts, e.g. Windows and some Android kernels, reject 7 bytes).
