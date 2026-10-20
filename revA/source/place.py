"""Board outline, stackup and component placement for Pocket Hub-8 rev A."""
import math
import pcbnew
from design import COMPS, nets

FPDIR = '/usr/share/kicad/footprints'
MM = pcbnew.FromMM

# ------------------------------------------------------------- geometry
W = 31.0          # board length (plug at x=0)
H = 16.0          # board width
MID = H / 2

FIXED = {
    'J1': (0.96, 8.0, 90),
    'U4': (5.2, 5.4, 0),
    'C1': (5.2, 8.9, 0),
    'U3': (5.0, 11.6, 0), 'C2': (5.0, 14.4, 0),
    'R3': (13.45, 6.6, 0), 'R2': (11.45, 7.4, 0),
    'U2': (10.8, 10.7, 0),
    'U1': (19.5, 8.0, 90),
    'C22': (24.1, 5.3, 90), 'C23': (25.3, 5.3, 90), 'C21': (24.7, 3.4, 0),
    'R4': (24.65, 8.0, 0),
    'Y1': (27.4, 8.4, 90),
    'C25': (26.5, 5.0, 90), 'C24': (29.8, 9.5, 90),
    'D1': (21.5, 1.4, 0),
    # test / programming pads on the back
    'TP1': (16.0, 14.4, 0), 'TP2': (18.4, 14.4, 0), 'TP3': (20.8, 14.4, 0),
}
BOTTOM = {'TP1', 'TP2', 'TP3'}


def positions():
    return dict(FIXED)


def load_fp(libfp):
    lib, name = libfp.split(':')
    d = '/home/claude/link/kicad/Pocket.pretty' if lib == 'Pocket' else f'{FPDIR}/{lib}.pretty'
    fp = pcbnew.FootprintLoad(d, name)
    if fp is None:
        raise RuntimeError(libfp)
    return fp


def make_board():
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(MM(0.8))
    # net classes
    netinfo = {}
    for n in nets():
        ni = pcbnew.NETINFO_ITEM(board, n)
        board.Add(ni)
        netinfo[n] = ni
    pos = positions()
    for ref, c in COMPS.items():
        fp = load_fp(c.fp)
        fp.SetReference(ref)
        fp.SetValue(c.value)
        fp.SetFPID(pcbnew.LIB_ID(*c.fp.split(':')))
        if c.lcsc:
            fp.SetField('LCSC', c.lcsc) if hasattr(fp, 'SetField') else None
        board.Add(fp)
        if ref in pos:
            x, y, r = pos[ref]
            fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
            fp.SetOrientationDegrees(r)
            if ref in BOTTOM:
                fp.Flip(fp.GetPosition(), False)
        for pad in fp.Pads():
            n = c.pins.get(pad.GetNumber())
            if n:
                pad.SetNet(netinfo[n])
        c.fpobj = fp
    return board, netinfo, pos


def outline(board):
    pts = [(0, 0), (W, 0), (W, H), (0, H)]
    r = 1.0
    # rounded rectangle on Edge.Cuts
    segs = [((r, 0), (W - r, 0)), ((W, r), (W, H - r)), ((W - r, H), (r, H)), ((0, H - r), (0, r))]
    for a, b in segs:
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetStart(pcbnew.VECTOR2I(MM(a[0]), MM(a[1])))
        s.SetEnd(pcbnew.VECTOR2I(MM(b[0]), MM(b[1])))
        s.SetWidth(MM(0.1))
        board.Add(s)
    for cx, cy, a0 in [(r, r, 180), (W - r, r, 270), (W - r, H - r, 0), (r, H - r, 90)]:
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetCenter(pcbnew.VECTOR2I(MM(cx), MM(cy)))
        sx = cx + r * math.cos(math.radians(a0))
        sy = cy + r * math.sin(math.radians(a0))
        s.SetStart(pcbnew.VECTOR2I(MM(sx), MM(sy)))
        s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T), True)
        s.SetWidth(MM(0.1))
        board.Add(s)


if __name__ == '__main__':
    b, ni, pos = make_board()
    outline(b)
    missing = [r for r in COMPS if r not in pos]
    print('unplaced:', missing)
    b.Save('/tmp/place.kicad_pcb')


# ------------------------------------------------------------- auto placement of support passives
ANCHORS = {
    'C10': ('U1', '1'), 'C11': ('U1', '10'), 'C12': ('U1', '22'), 'C13': ('U1', '33'), 'C14': ('U1', '42'),
    'C15': ('U1', '49'), 'C16': ('U1', '43'), 'C17': ('U1', '48'), 'C18': ('U1', '44'),
    'C20': ('U1', '44'),
    'C26': ('U2', '8'),
    'R1': ('J1', 'A5'), 
    'R5': ('U2', '1'), 'R6': ('U1', '37'),
}


def anchors():
    return dict(ANCHORS)


def fab_bbox(fp):
    xs, ys = [], []
    for g in fp.GraphicalItems():
        if g.GetLayer() == pcbnew.F_Fab and g.GetClass() != 'MTEXT' and hasattr(g, 'GetStart'):
            for p in (g.GetStart(), g.GetEnd()):
                xs.append(p.x / 1e6); ys.append(p.y / 1e6)
    return min(xs), min(ys), max(xs), max(ys)


def bbox_of(fp, grow=0.0):
    if fp.GetValue().startswith('ESP32'):
        x0, y0, x1, y1 = fab_bbox(fp)
        g = 0.75 + grow
        return (max(x0 - g, 0), max(y0 - g, 0), min(x1 + g, W), min(y1 + g, H))
    cy = fp.GetCourtyard(pcbnew.F_CrtYd)
    if cy.OutlineCount() == 0:
        cy = fp.GetCourtyard(pcbnew.B_CrtYd)
    bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False, False)
    x0, y0, x1, y1 = (bb.GetLeft() / 1e6 - grow, bb.GetTop() / 1e6 - grow, bb.GetRight() / 1e6 + grow, bb.GetBottom() / 1e6 + grow)
    return (max(x0, 0), max(y0, 0), min(x1, W), min(y1, H))   # only the on-board part matters


def overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def autoplace(board, pos):
    anc = anchors()
    placed = {}
    for ref, c in COMPS.items():
        if ref in pos:
            fp = c.fpobj
            big = c.part in ('MCU', 'FLASH', 'PLUG', 'LDO', 'ESD')
            if ref in BOTTOM:
                continue
            placed[ref] = bbox_of(fp, 0.45 if big else 0.1)
    order = [r for r in COMPS if r not in pos]
    for ref in order:
        c = COMPS[ref]
        fp = c.fpobj
        aref, apin = anc[ref]
        ap = [p for p in COMPS[aref].fpobj.Pads() if p.GetNumber() == apin][0].GetPosition()
        ax, ay = ap.x / 1e6, ap.y / 1e6
        best = None
        for ring in range(3, 80):
            d = ring * 0.2
            cands = []
            n = max(8, int(2 * math.pi * d / 0.5))
            for i in range(n):
                t = 2 * math.pi * i / n
                cands.append((ax + d * math.cos(t), ay + d * math.sin(t)))
            for (x, y) in cands:
                x, y = round(x * 10) / 10, round(y * 10) / 10
                for rot in (0, 90):
                    fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
                    fp.SetOrientationDegrees(rot)
                    bb = bbox_of(fp, 0.15)
                    if bb[0] < 2.6 or bb[1] < 0.2 or bb[2] > W - 0.2 or bb[3] > H - 0.2:
                        continue
                    if any(overlap(bb, o) for o in placed.values()):
                        continue
                    best = (x, y, rot, bb)
                    break
                if best:
                    break
            if best:
                break
        assert best, ref
        x, y, rot, bb = best
        fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
        fp.SetOrientationDegrees(rot)
        placed[ref] = bb
        pos[ref] = (x, y, rot)
    return pos


def check_overlaps(board):
    bbs = {r: bbox_of(c.fpobj, 0.0) for r, c in COMPS.items() if r not in BOTTOM}
    bad = []
    refs = list(bbs)
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            if overlap(bbs[a], bbs[b]):
                bad.append((a, b))
    return bad
