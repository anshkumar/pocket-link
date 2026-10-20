"""Generate the KiCad 7 hierarchical schematic from design.py."""
import re
import uuid
import math
from design import COMPS, SHEETS, PARTS
import sexp

PROJECT = 'pocket-link'
OUT = 'kicad'
NS = uuid.UUID('6f1c0a3e-7d2b-4c55-9a39-1b2c3d4e5f60')


def U(*k):
    return str(uuid.uuid5(NS, '/'.join(map(str, k))))


ROOT_UUID = U('root')
GRID = 2.54


def snap(v):
    return round(round(v / GRID) * GRID, 2)


# ------------------------------------------------------------------ symbols
def fe11s_revb():
    blk = sexp.flat_symbol('Interface_USB:FE1.1s')
    blk = blk.replace('(symbol "Interface_USB:FE1.1s"', '(symbol "Pocket:FE1.1s_RevB"', 1)
    blk = blk.replace('(symbol "FE1.1s_', '(symbol "FE1.1s_RevB_')
    blk = sexp.set_prop(blk, 'Value', 'FE1.1s')
    blk = sexp.set_prop(blk, 'Footprint', 'Package_SO:SSOP-28_3.9x9.9mm_P0.635mm')
    blk = sexp.set_prop(blk, 'Datasheet', 'https://www.lcsc.com/datasheet/C6706491.pdf')
    ren = {'12': ('NC', 'no_connect'), '28': ('NC', 'no_connect'),
           '13': ('NC{slash}VD33F', 'passive'), '21': ('VD33F', 'power_in'),
           '20': ('VDD5', 'no_connect')}

    def fix(m):
        pb = sexp.block_at(blk, m.start())
        num = re.search(r'\(number "([^"]*)"', pb).group(1)
        if num in ren:
            nm, ty = ren[num]
            pb2 = re.sub(r'\(pin \w+', f'(pin {ty}', pb, count=1)
            pb2 = re.sub(r'\(name "[^"]*"', f'(name "{nm}"', pb2, count=1)
            return pb2, pb
        return None, None
    out = blk
    for m in list(re.finditer(r'\(pin \w+ \w+', blk)):
        new, old = fix(m)
        if new:
            out = out.replace(old, new, 1)
    return out


_symcache = {}


def symbol_text(lib_id):
    if lib_id not in _symcache:
        if lib_id == 'Pocket:FE1.1s_RevB':
            _symcache[lib_id] = fe11s_revb()
        else:
            _symcache[lib_id] = sexp.flat_symbol(lib_id)
    return _symcache[lib_id]


# ------------------------------------------------------------------ emit helpers
def fx(v):
    return f'{v:.2f}'.rstrip('0').rstrip('.') if v != int(v) else str(int(v))


def prop_txt(key, val, x, y, hide=False, justify=None, angle=0):
    e = '(effects (font (size 1.27 1.27))' + (f' (justify {justify})' if justify else '') + (' hide' if hide else '') + ')'
    return f'    (property "{key}" "{val}" (at {fx(x)} {fx(y)} {angle}) {e})\n'


class Sheet:
    def __init__(self, name, title, page, paper='A2'):
        self.name, self.title, self.page, self.paper = name, title, page, paper
        self.uuid = U('sheet', name)
        self.items = []
        self.libs = set()

    def wire(self, x1, y1, x2, y2):
        self.items.append(f'  (wire (pts (xy {fx(x1)} {fx(y1)}) (xy {fx(x2)} {fx(y2)})) (stroke (width 0) (type default)) (uuid {U(self.name, "w", x1, y1, x2, y2)}))\n')

    def glabel(self, net, x, y, ang):
        just = 'left' if ang in (0, 90) else 'right'
        self.items.append(
            f'  (global_label "{net}" (shape bidirectional) (at {fx(x)} {fx(y)} {ang}) (fields_autoplaced)\n'
            f'    (effects (font (size 1.27 1.27)) (justify {just})) (uuid {U(self.name, "gl", net, x, y)})\n'
            f'    (property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {fx(x)} {fx(y)} 0) (effects (font (size 1.27 1.27)) hide)))\n')

    def noconn(self, x, y):
        self.items.append(f'  (no_connect (at {fx(x)} {fx(y)}) (uuid {U(self.name, "nc", x, y)}))\n')

    def text(self, s, x, y, size=2.5, bold=False):
        b = ' bold' if bold else ''
        s = s.replace('"', "'")
        self.items.append(f'  (text "{s}" (at {fx(x)} {fx(y)} 0) (effects (font (size {size} {size}){b}) (justify left bottom)) (uuid {U(self.name, "t", s, x, y)}))\n')

    def rect(self, x1, y1, x2, y2):
        self.items.append(f'  (rectangle (start {fx(x1)} {fx(y1)}) (end {fx(x2)} {fx(y2)}) (stroke (width 0.25) (type dash)) (fill (type none)) (uuid {U(self.name, "r", x1, y1)}))\n')

    def symbol(self, lib_id, ref, value, X, Y, pins_map, props, in_bom=True, on_board=True, dnp=False):
        """place symbol, wire every pin to a global label (or NC flag)."""
        self.libs.add(lib_id)
        blk = symbol_text(lib_id)
        pins = sexp.pins(blk)
        x0, y0, x1, y1 = sexp.graphics_bbox(blk)
        yn = 'yes' if in_bom else 'no'
        s = (f'  (symbol (lib_id "{lib_id}") (at {fx(X)} {fx(Y)} 0) (unit 1) (in_bom {yn}) '
             f'(on_board {"yes" if on_board else "no"}) (dnp {"yes" if dnp else "no"}) (uuid {U(self.name, "sym", ref)})\n')
        if (x1 - x0) < 12:   # small 2/3-pin parts: text to the right, clear of the labels
            s += prop_txt('Reference', ref, X + x1 + 1.5, Y - 1.3, justify='left')
            s += prop_txt('Value', value, X + x1 + 1.5, Y + 1.3, justify='left')
        else:
            s += prop_txt('Reference', ref, X + x0, Y - y1 - 1.6, justify='left')
            s += prop_txt('Value', value, X + x0, Y - y0 + 2.6, justify='left')
        for k, v in props.items():
            s += prop_txt(k, v, X, Y, hide=True)
        seen = set()
        for p in pins:
            s += f'    (pin "{p["number"]}" (uuid {U(self.name, "pin", ref, p["number"])}))\n'
        s += (f'    (instances (project "{PROJECT}" (path "/{ROOT_UUID}/{self.uuid}" '
              f'(reference "{ref}") (unit 1))))\n  )\n')
        self.items.append(s)
        # pin stubs
        done = {}
        for p in pins:
            px, py = X + p['x'], Y - p['y']           # lib y is up, sheet y is down
            a = int(p['angle']) % 360
            d = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}[a]
            net = pins_map.get(p['number'])
            key = (round(px, 2), round(py, 2))
            if key in done:
                assert done[key] == net, (ref, p['number'], net, done[key])
                continue
            done[key] = net
            if net is None:
                self.noconn(px, py)
                continue
            L = 2.54
            ex, ey = px + d[0] * L, py + d[1] * L
            self.wire(px, py, ex, ey)
            ang = {(-1, 0): 180, (1, 0): 0, (0, 1): 270, (0, -1): 90}[d]
            self.glabel(net, ex, ey, ang)

    def write(self, path):
        libs = ''.join('    ' + symbol_text(l).replace('\n', '\n    ').rstrip() + '\n' for l in sorted(self.libs))
        tb = (f'  (title_block (title "Pocket Link - {self.title}") (date "2026-10-06") (rev "A")\n'
              f'    (company "Pocket") (comment 1 "USB-C phone adapter: USB headset + data channel") (comment 2 "Generated from design.py - edit the source, not this file"))\n')
        with open(path, 'w') as f:
            f.write(f'(kicad_sch (version 20230121) (generator eeschema)\n  (uuid {self.uuid}_f)\n'
                    .replace(f'{self.uuid}_f', U('file', self.name)))
            f.write(f'  (paper "{self.paper}")\n{tb}  (lib_symbols\n{libs}  )\n')
            f.writelines(self.items)
            f.write(')\n')


def cell_size(lib_id):
    x0, y0, x1, y1 = sexp.graphics_bbox(symbol_text(lib_id))
    lab = 22  # room for stub + global label text
    return (x1 - x0) + 2 * lab, (y1 - y0) + 14, x0, y1


def layout_sheet(sh, comps, width, x_start=25, y_start=30):
    """flow-place groups of components; each group gets a dashed frame."""
    groups = []
    for c in comps:
        key = c.group
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(c)
    gy = y_start
    gx = x_start
    rowh = 0
    group_w = width if len(groups) == 1 else None
    for key, cs in groups:
        # pre-compute group box using simple wrap inside a fixed group width
        gw = 170 if key != 'mcu' else 350
        x, y, lineh = 0, 12, 0
        places = []
        for c in cs:
            w, h, x0, y1 = cell_size(c.lib_id)
            if x + w > gw and x > 0:
                x = 0
                y += lineh
                lineh = 0
            places.append((c, x + 22 - x0, y + y1 + 6))
            x += w
            lineh = max(lineh, h)
        gh = y + lineh + 4
        if gx + gw > width + x_start:
            gx = x_start
            gy += rowh + 10
            rowh = 0
        title = {'usb': 'USB-C plug + ESD', 'power': 'Power (phone VBUS -> 3.3 V)', 'mcu': 'RP2040 + flash + crystal',
                 'debug': 'Boot / status / test pads'}.get(key, str(key))
        if title:
            sh.text(title, gx + 2, gy + 6, 2.5, True)
            sh.rect(gx, gy, gx + gw, gy + gh)
        for c, px, py in places:
            X, Y = snap(gx + px), snap(gy + py)
            props = {'Footprint': c.fp, 'Datasheet': '~', 'MPN': c.mpn, 'Manufacturer': c.mfr,
                     'LCSC': c.lcsc, 'Description': c.desc}
            if c.note:
                props['Note'] = c.note
            val = c.value + (' (DNP)' if c.dnp else '')
            on_board = c.part not in ()
            sh.symbol(c.lib_id, c.ref, val, X, Y, c.pins, props, in_bom=not c.dnp, dnp=c.dnp)
        gx += gw + 10
        rowh = max(rowh, gh)


NOTES = {
    'link': [
        'Phone = USB host. J1 plugs into the phone; CC has Rd (5.1k) so the phone supplies VBUS and enumerates us as a device.',
        'RP2040 firmware (TinyUSB) = composite device: UAC headset (16 kHz mono in/out) + vendor bulk data interface for the Pocket app.',
        'Blank flash -> RP2040 USB bootloader appears as a drive: drag the .uf2. To force bootloader later: short TP BOOT to GND while plugging in.',
        'RP2040 support circuit follows the Raspberry Pi RP2040 hardware design guide (1k on XOUT, 27R USB series, 1uF on VREG).',
    ]}



def main():
    import os
    os.makedirs(OUT, exist_ok=True)
    sheets = []
    for i, (name, title) in enumerate(SHEETS.items()):
        paper = 'A2'
        sh = Sheet(name, title, i + 2, paper)
        width = 540 if paper == 'A2' else 370
        comps = [c for c in COMPS.values() if c.sheet == name]
        y0 = 30 + 6 * len(NOTES[name])
        for k, line in enumerate(NOTES[name]):
            sh.text(line, 25, 22 + 6 * k, 2.0)
        layout_sheet(sh, comps, width, y_start=y0 + 4)
        if name == 'link':
            for k, net in enumerate(['GND', 'VBUS']):
                X, Y = snap(40 + 40 * k), snap(395)
                sh.symbol('power:PWR_FLAG', f'#FLG0{k+1}', 'PWR_FLAG', X, Y, {'1': net}, {'Footprint': '', 'Datasheet': '~'},
                          in_bom=False, on_board=False)
        sh.write(f'{OUT}/{name}.kicad_sch')
        sheets.append(sh)

    # root sheet
    items = []
    titles = {'link': 'Pocket Link'}
    for k, sh in enumerate(sheets):
        x, y = 40 + (k % 2) * 120, 60 + (k // 2) * 60
        items.append(
            f'  (sheet (at {x} {y}) (size 90 35) (fields_autoplaced) (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000))\n'
            f'    (uuid {sh.uuid})\n'
            f'    (property "Sheetname" "{titles[sh.name]}" (at {x} {y - 0.7} 0) (effects (font (size 1.27 1.27)) (justify left bottom)))\n'
            f'    (property "Sheetfile" "{sh.name}.kicad_sch" (at {x} {y + 35.6} 0) (effects (font (size 1.27 1.27)) (justify left top)))\n'
            f'    (instances (project "{PROJECT}" (path "/{ROOT_UUID}" (page "{sh.page}"))))\n  )\n')
    notes = [
        'POCKET LINK  rev A  -  USB-C phone adapter for the Pocket voice agent',
        'Plugs into the phone. Phone sees a USB headset (call audio) + a data interface (Pocket app).',
        'The app bridges call audio <-> voice agent WebSocket using the phone internet. No radio, no battery.',
        'RP2040 + 2 MB QSPI flash + AP2112K 3.3 V LDO, powered from phone VBUS.',
        '4-layer 0.8 mm (plug straddles the board edge).  Fab: JLCPCB, see fab/ folder.',
    ]
    for k, line in enumerate(notes):
        items.append(f'  (text "{line}" (at 40 {170 + k * 7} 0) (effects (font (size {3 if k == 0 else 2} {3 if k == 0 else 2}){" bold" if k == 0 else ""}) (justify left bottom)) (uuid {U("root", "t", k)}))\n')
    with open(f'{OUT}/{PROJECT}.kicad_sch', 'w') as f:
        f.write(f'(kicad_sch (version 20230121) (generator eeschema)\n  (uuid {ROOT_UUID})\n  (paper "A4")\n'
                f'  (title_block (title "Pocket Hub-8") (date "2026-10-06") (rev "A") (company "Pocket"))\n  (lib_symbols)\n')
        f.writelines(items)
        f.write('  (sheet_instances (path "/" (page "1")))\n)\n')
    # project-local library holding the corrected hub symbol
    with open(f'{OUT}/pocket.kicad_sym', 'w') as f:
        blk = symbol_text('Pocket:FE1.1s_RevB').replace('(symbol "Pocket:FE1.1s_RevB"', '(symbol "FE1.1s_RevB"', 1)
        f.write('(kicad_symbol_lib (version 20220914) (generator gen_sch)\n  ' + blk.replace('\n', '\n  ') + '\n)\n')
    with open(f'{OUT}/sym-lib-table', 'w') as f:
        f.write('(sym_lib_table\n  (lib (name "Pocket")(type "KiCad")(uri "${KIPRJMOD}/pocket.kicad_sym")(options "")(descr "Pocket Hub-8 local symbols"))\n)\n')
    print('schematic written')


if __name__ == '__main__':
    main()
