"""JLCPCB BOM + CPL, full BOM with cost estimate, from design.py and the exported positions."""
import csv
from collections import OrderedDict
from design import COMPS

# ------------------------------------------------------------ BOM (JLCPCB format)
HAND = {'J1'}   # straddle-mount plug: soldered after SMT (pads on both sides)
groups = OrderedDict()
for ref, c in COMPS.items():
    if c.dnp or not c.lcsc or ref in HAND:
        continue
    key = (c.value, c.fp.split(':')[1], c.lcsc)
    groups.setdefault(key, []).append(ref)


def refkey(r):
    import re
    m = re.match(r'([A-Z]+)(\d+)', r)
    return (m.group(1), int(m.group(2)))


with open('fab/BOM_JLCPCB.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #'])
    for (val, fp, lcsc), refs in groups.items():
        w.writerow([val, ','.join(sorted(refs, key=refkey)), fp, lcsc])

# rough unit prices (USD, LCSC 100-pc tier, Oct 2026 estimate - verify at order)
PRICE = {'C2040': 0.80, 'C2456211': 0.20, 'C134082': 0.92, 'C51118': 0.06, 'C7519': 0.08, 'C9002': 0.08,
         'C25100': 0.001, 'C11702': 0.001, 'C25905': 0.001, 'C1525': 0.002, 'C52923': 0.003, 'C19702': 0.01,
         'C1562': 0.002, 'C72043': 0.01}
HAND = {'J1'}   # straddle-mount plug: soldered after SMT (pads on both sides)
total = 0.0
with open('fab/BOM_full.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['Qty', 'Designators', 'Value', 'Description', 'Manufacturer', 'MPN', 'LCSC', 'Footprint',
                'Assemble', 'Est. unit USD', 'Est. line USD'])
    allg = OrderedDict()
    for ref, c in COMPS.items():
        if c.part in ('TP',):
            continue
        allg.setdefault((c.value, c.mpn, c.lcsc, c.fp, c.desc, c.mfr, c.dnp), []).append(ref)
    for (val, mpn, lcsc, fp, desc, mfr, dnp), refs in allg.items():
        u = PRICE.get(lcsc, 0.0)
        line = 0 if dnp else u * len(refs)
        total += line
        w.writerow([len(refs), ' '.join(sorted(refs, key=refkey)), val, desc, mfr, mpn, lcsc, fp.split(':')[1],
                    'hand-solder after SMT' if any(r in HAND for r in refs) else ('DNP' if dnp else 'yes'), f'{u:.3f}', f'{line:.2f}'])
    w.writerow([])
    w.writerow(['', '', '', 'Parts total per adapter', '', '', '', '', '', '', f'{total:.2f}'])
print(f'parts estimate: ${total:.2f}')

# ------------------------------------------------------------ CPL (JLCPCB format)
rows = list(csv.DictReader(open('/tmp/pos.csv')))
with open('fab/CPL_JLCPCB.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
    n = 0
    for r in rows:
        ref = r['Ref']
        c = COMPS.get(ref)
        if not c or c.dnp or not c.lcsc or ref in HAND:
            continue
        # KiCad uses +Y down in the editor but the pos file is Y-up (negated); JLC expects the pos-file convention
        w.writerow([ref, f"{float(r['PosX']):.4f}mm", f"{float(r['PosY']):.4f}mm",
                    'Top' if r['Side'] == 'top' else 'Bottom', f"{float(r['Rot']):.1f}"])
        n += 1
print('CPL rows', n)
