"""Silkscreen/fab text, refill, DRC, and all fabrication outputs."""
import os
import re
import csv
import subprocess
import pcbnew
import place
from design import COMPS

MM = pcbnew.FromMM
SRC = '/tmp/lpoured.kicad_pcb'
PCB = 'kicad/pocket-link.kicad_pcb'
FAB = 'fab'

board = pcbnew.LoadBoard(SRC)

# ---------------------------------------------------------------- text: refs -> F.Fab, values hidden
for fp in board.GetFootprints():
    r = fp.Reference()
    r.SetLayer(pcbnew.F_Fab)
    r.SetTextSize(pcbnew.VECTOR2I(MM(0.6), MM(0.6)))
    r.SetTextThickness(MM(0.09))
    r.SetPosition(fp.GetPosition())
    fp.Value().SetVisible(False)
    # drop footprint 'user' texts on silk (e.g. ${REFERENCE} copies)
    for g in fp.GraphicalItems():
        if g.GetClass() == 'MTEXT' and g.GetLayer() == pcbnew.F_SilkS:
            g.SetLayer(pcbnew.F_Fab)
        elif g.GetLayer() == pcbnew.F_SilkS:
            bb = g.GetBoundingBox()
            if bb.GetTop() < MM(0.3) or bb.GetBottom() > MM(place.H - 0.3) or bb.GetLeft() < MM(0.3):
                g.SetLayer(pcbnew.F_Fab)     # module outline beyond the board edge


def silk(txt, x, y, size=1.0, layer=pcbnew.F_SilkS, rot=0, bold=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(txt)
    t.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetTextThickness(MM(0.15 if size < 1.2 else 0.2))
    t.SetBold(bold)
    if rot:
        t.SetTextAngleDegrees(rot)
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)


silk('POCKET LINK', 12.5, 3.2, 1.0, pcbnew.B_SilkS, bold=True)
silk('rev A 2026-10', 12.5, 4.8, 0.8, pcbnew.B_SilkS)
for ref, lab in (('TP1', 'BT'), ('TP2', 'G'), ('TP3', '3V3')):
    p = board.FindFootprintByReference(ref).GetPosition()
    silk(lab, p.x / 1e6, p.y / 1e6 - 1.4, 0.8, pcbnew.B_SilkS)
# ---------------------------------------------------------------- rules / severities
ds = board.GetDesignSettings()
for name in ('DRCE_LIB_FOOTPRINT_ISSUES', 'DRCE_LIB_FOOTPRINT_MISMATCH'):
    if hasattr(pcbnew, name):
        ds.m_DRCSeverities[getattr(pcbnew, name)] = pcbnew.RPT_SEVERITY_IGNORE

board.BuildConnectivity()
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
pcbnew.SaveBoard(PCB, board)
print('saved', PCB)
