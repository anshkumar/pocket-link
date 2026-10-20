#!/usr/bin/env python3
"""Convert the firmware ELF to a UF2 file for the RP2040 USB bootloader (drag-and-drop)."""
import struct, subprocess, sys, tempfile, os

FAMILY_RP2040 = 0xE48BFF56
FLASH_BASE = 0x10000000


def main(elf, out):
    with tempfile.TemporaryDirectory() as d:
        binf = os.path.join(d, 'fw.bin')
        subprocess.run(['arm-none-eabi-objcopy', '-O', 'binary', elf, binf], check=True)
        data = open(binf, 'rb').read()
    # objcopy -O binary starts at the lowest loadable address; make sure that is flash
    hdr = subprocess.run(['arm-none-eabi-objdump', '-h', elf], capture_output=True, text=True).stdout
    assert '.boot2' in hdr, 'boot2 section missing'
    data += b'\x00' * (-len(data) % 256)
    blocks = [data[i:i + 256] for i in range(0, len(data), 256)]
    with open(out, 'wb') as f:
        for n, blk in enumerate(blocks):
            f.write(struct.pack('<IIIIIIII', 0x0A324655, 0x9E5D5157, 0x00002000, FLASH_BASE + n * 256,
                                256, n, len(blocks), FAMILY_RP2040))
            f.write(blk + b'\x00' * (476 - len(blk)))
            f.write(struct.pack('<I', 0x0AB16F30))
    print(f'{out}: {len(blocks)} blocks, {len(data)} bytes')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
