"""PCB pad nets vs design.py (every pin on every footprint) + schematic match."""
import pcbnew, sys
from design import COMPS
b = pcbnew.LoadBoard('kicad/pocket-link.kicad_pcb')
bad = 0
seen = set()
for fp in b.GetFootprints():
    r = fp.GetReference(); seen.add(r)
    c = COMPS[r]
    for p in fp.Pads():
        want = c.pins.get(p.GetNumber()) or ''
        if p.GetNumber() == '' : continue
        if p.GetNetname() != want:
            bad += 1; print('MISMATCH', r, p.GetNumber(), p.GetNetname(), want)
print('missing on PCB:', set(COMPS) - seen)
print('PCB <-> design:', 'MATCH' if bad == 0 and not (set(COMPS) - seen) else 'FAIL', len(seen), 'footprints')
