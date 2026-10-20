"""Pocket Link rev A -- USB-C phone adapter (USB headset + data channel), single source of truth.

The phone (USB host) sees a composite USB device:
  * USB Audio Class headset (16 kHz mono, speaker + microphone)  -> Android routes call audio here
  * vendor bulk / CDC data interface                             -> the Pocket app streams audio to/from the agent
No radio, no battery. Powered from the phone's VBUS.
"""
from collections import OrderedDict

PARTS = {
    'MCU':    ('MCU_RaspberryPi:RP2040', 'Pocket:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm_Vias0.3', 'RP2040',
               'RP2040', 'Raspberry Pi', 'C2040', 'Dual M0+ MCU, USB 1.1 device (UAC + vendor/CDC via TinyUSB)'),
    'FLASH':  ('Memory_Flash:W25Q32JVSS', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', 'W25Q16JVSNIQ',
               'W25Q16JVSNIQ', 'Winbond', 'C2456211', '16 Mbit QSPI flash (firmware)'),
    'PLUG':   ('Connector:USB_C_Plug_USB2.0', 'Connector_USB:USB_C_Plug_Molex_105444', 'USB-C plug',
               '105444-0001', 'Molex', 'C134082', 'USB-C plug, board-edge straddle mount (0.8 mm PCB). Alt: SHOU HAN TYPE-C 24P GTJB'),
    'LDO':    ('Regulator_Linear:AP2112K-3.3', 'Package_TO_SOT_SMD:SOT-23-5', 'AP2112K-3.3',
               'AP2112K-3.3TRG1', 'Diodes Inc', 'C51118', '3.3V 600mA LDO'),
    'ESD':    ('Power_Protection:USBLC6-2SC6', 'Package_TO_SOT_SMD:SOT-23-6', 'USBLC6-2SC6',
               'USBLC6-2SC6', 'ST', 'C7519', 'USB ESD array'),
    'XTAL12': ('Device:Crystal_GND24', 'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm', '12MHz',
               'X322512MSB4SI', 'YXC', 'C9002', '12 MHz 20 pF 3225'),
    'R27':    ('Device:R', 'Resistor_SMD:R_0402_1005Metric', '27R', '0402WGF270JTCE', 'UNI-ROYAL', 'C25100', 'USB series'),
    'R1K':    ('Device:R', 'Resistor_SMD:R_0402_1005Metric', '1k', '0402WGF1001TCE', 'UNI-ROYAL', 'C11702', ''),
    'R5K1':   ('Device:R', 'Resistor_SMD:R_0402_1005Metric', '5.1k', '0402WGF5101TCE', 'UNI-ROYAL', 'C25905', 'CC Rd (USB device)'),
    'C100N':  ('Device:C', 'Capacitor_SMD:C_0402_1005Metric', '100nF', 'CL05B104KO5NNNC', 'Samsung', 'C1525', ''),
    'C1U':    ('Device:C', 'Capacitor_SMD:C_0402_1005Metric', '1uF', 'CL05A105KA5NQNC', 'Samsung', 'C52923', ''),
    'C10U':   ('Device:C', 'Capacitor_SMD:C_0603_1608Metric', '10uF', 'CL10A106KP8NNNC', 'Samsung', 'C19702', ''),
    'C33P':   ('Device:C', 'Capacitor_SMD:C_0402_1005Metric', '33pF', '0402CG330J500NT', 'FH', 'C1562', 'crystal load'),
    'LEDG':   ('Device:LED', 'LED_SMD:LED_0603_1608Metric', 'GREEN', '19-217/GHC-YR1S2/3T', 'Everlight', 'C72043', 'status'),
    'TP':     ('Connector:TestPoint', 'TestPoint:TestPoint_Pad_D1.0mm', 'TP', '', '', '', 'test / programming pad'),
}


class Comp:
    def __init__(self, ref, part, pins, sheet, group=None, dnp=False, note='', side='F'):
        self.ref, self.part, self.pins, self.sheet = ref, part, pins, sheet
        self.group, self.dnp, self.note, self.side = group, dnp, note, side
        p = PARTS[part]
        self.lib_id, self.fp, self.value, self.mpn, self.mfr, self.lcsc, self.desc = p
        if dnp:
            self.lcsc = ''


COMPS = OrderedDict()


def add(ref, part, pins, sheet='link', **kw):
    assert ref not in COMPS, ref
    COMPS[ref] = Comp(ref, part, {str(k): v for k, v in pins.items()}, sheet, **kw)


G = 'GND'
# ---- USB-C plug (device / UFP side): Rd on CC, VCONN unused
add('J1', 'PLUG', {'A1': G, 'A12': G, 'B1': G, 'B12': G, 'S1': G,
                   'A4': 'VBUS', 'A9': 'VBUS', 'B4': 'VBUS', 'B9': 'VBUS',
                   'A5': 'CC', 'B5': None, 'A6': 'DP_C', 'A7': 'DM_C', 'A8': None, 'B8': None}, group='usb')
add('R1', 'R5K1', {1: 'CC', 2: G}, group='usb')
add('U4', 'ESD', {1: 'DM_C', 6: 'DM_C', 3: 'DP_C', 4: 'DP_C', 2: G, 5: 'VBUS'}, group='usb')
add('R2', 'R27', {1: 'DP_C', 2: 'USB_DP'}, group='usb')
add('R3', 'R27', {1: 'DM_C', 2: 'USB_DM'}, group='usb')
# ---- power
add('U3', 'LDO', {1: 'VBUS', 3: 'VBUS', 2: G, 4: None, 5: '+3V3'}, group='power')
add('C1', 'C1U', {1: 'VBUS', 2: G}, group='power')
add('C2', 'C10U', {1: '+3V3', 2: G}, group='power')
# ---- RP2040
io = {i: None for i in range(1, 58)}
io.update({1: '+3V3', 10: '+3V3', 22: '+3V3', 33: '+3V3', 42: '+3V3', 49: '+3V3',
           43: '+3V3', 44: '+3V3', 48: '+3V3', 45: '+1V1', 23: '+1V1', 50: '+1V1',
           19: G, 57: G, 20: 'XIN', 21: 'XOUT',
           46: 'USB_DM', 47: 'USB_DP', 51: 'QSPI_SD3', 52: 'QSPI_SCLK', 53: 'QSPI_SD0',
           54: 'QSPI_SD2', 55: 'QSPI_SD1', 56: 'QSPI_SS', 37: 'LED_IO'})
add('U1', 'MCU', io, group='mcu')
for k, n in enumerate(['IOVDD1', 'IOVDD10', 'IOVDD22', 'IOVDD33', 'IOVDD42', 'IOVDD49', 'ADC', 'USBVDD', 'VREGIN']):
    add(f'C{10 + k}', 'C100N', {1: '+3V3', 2: G}, group='mcu')
add('C20', 'C1U', {1: '+3V3', 2: G}, group='mcu')        # VREG_IN bulk
add('C21', 'C1U', {1: '+1V1', 2: G}, group='mcu')        # VREG_VOUT
add('C22', 'C100N', {1: '+1V1', 2: G}, group='mcu')      # DVDD 23
add('C23', 'C100N', {1: '+1V1', 2: G}, group='mcu')      # DVDD 50
# crystal (RP2040 hardware design guide: 1k series on XOUT)
add('Y1', 'XTAL12', {1: 'XIN', 3: 'XO_X', 2: G, 4: G}, group='mcu')
add('R4', 'R1K', {1: 'XOUT', 2: 'XO_X'}, group='mcu')
add('C24', 'C33P', {1: 'XIN', 2: G}, group='mcu')
add('C25', 'C33P', {1: 'XO_X', 2: G}, group='mcu')
# flash
add('U2', 'FLASH', {1: 'QSPI_SS', 2: 'QSPI_SD1', 3: 'QSPI_SD2', 4: G, 5: 'QSPI_SD0', 6: 'QSPI_SCLK',
                    7: 'QSPI_SD3', 8: '+3V3'}, group='mcu')
add('C26', 'C100N', {1: '+3V3', 2: G}, group='mcu')
# boot / status / test pads on the back. SWD/RUN left unconnected: firmware loads over USB (UF2 bootloader);
# debugging is done on an RP2040 dev board.
add('R5', 'R1K', {1: 'QSPI_SS', 2: 'BOOT'}, group='debug')
add('R6', 'R1K', {1: 'LED_IO', 2: 'LED_A'}, group='debug')
add('D1', 'LEDG', {2: 'LED_A', 1: G}, group='debug')
for k, n in enumerate(['BOOT', G, '+3V3']):
    add(f'TP{k + 1}', 'TP', {1: n}, group='debug', side='B')

SHEETS = OrderedDict([('link', 'Pocket Link - USB-C phone adapter')])


def nets():
    out = OrderedDict()
    for c in COMPS.values():
        for p, n in c.pins.items():
            if n:
                out.setdefault(n, []).append((c.ref, p))
    return out


if __name__ == '__main__':
    ns = nets()
    print(len(COMPS), 'components,', len(ns), 'nets')
    for n, m in ns.items():
        if len(m) < 2:
            print('SINGLE-PIN NET', n, m)
