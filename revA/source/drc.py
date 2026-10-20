import sys, re, pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
ds = b.GetDesignSettings()
out = sys.argv[2] if len(sys.argv) > 2 else '/tmp/drc.rpt'
pcbnew.WriteDRCReport(b, out, pcbnew.EDA_UNITS_MILLIMETRES, True)
s = open(out).read()
print(re.findall(r'\*\* Found \d+ [^\n]*', s))
from collections import Counter
print(Counter(re.findall(r'^\[(\w+)\]', s, re.M)).most_common())
