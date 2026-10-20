"""Compare the netlist exported by KiCad from the generated schematic against design.py."""
import re
import sys
import subprocess
from design import COMPS, nets

subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '-o', '/tmp/net.net', 'kicad/pocket-link.kicad_sch'], check=True,
               capture_output=True)
s = open('/tmp/net.net').read()
sch = {}
for chunk in s.split('(net (code ')[1:]:
    name = re.search(r'\(name "([^"]*)"\)', chunk).group(1).split('/')[-1]
    nodes = set(re.findall(r'\(node \(ref "([^"]*)"\) \(pin "([^"]*)"\)', chunk))
    nodes = {n for n in nodes if not n[0].startswith('#')}
    if not nodes:
        continue
    if name.startswith('unconnected-') or name.startswith('Net-('):
        if len(nodes) == 1:
            continue
    sch.setdefault(name, set()).update(nodes)
comps_in_sch = set(re.findall(r'\(comp \(ref "([^"]*)"\)', s))

want = {n: set(v) for n, v in nets().items()}
ok = True
for n, v in want.items():
    if sch.get(n) != v:
        ok = False
        print('MISMATCH', n, 'design', sorted(v), 'sch', sorted(sch.get(n, [])))
for n in sch:
    if n not in want:
        ok = False
        print('EXTRA sch net', n, sorted(sch[n]))
missing = set(COMPS) - comps_in_sch
if missing:
    ok = False
    print('components missing in schematic', missing)
print('schematic <-> design:', 'MATCH' if ok else 'FAIL', f'({len(want)} nets, {len(comps_in_sch)} symbols)')
sys.exit(0 if ok else 1)
