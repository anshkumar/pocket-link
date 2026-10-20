"""Build, route and pour the Pocket Hub-8 PCB."""
import sys
import time
import math
import pcbnew
import place
import router as R
from design import COMPS, nets

MM = pcbnew.FromMM
OUTPCB = 'kicad/pocket-link.kicad_pcb'

PLANE_NETS = {'GND': 0, '+3V3': 1}     # inner layer index In1/In2
POWER_W = {'VBUS': 0.5, '+1V1': 0.3}
HS_NETS = ['USB_DP', 'USB_DM']


def width_for(net):
    if net in POWER_W:
        return POWER_W[net]
    if net in HS_NETS or net in ('DP_C', 'DM_C'):
        return 0.2
    return 0.15


def build():
    board, netinfo, pos = place.make_board()
    place.outline(board)
    place.autoplace(board, pos)
    bad = place.check_overlaps(board)
    if bad:
        print('OVERLAPS', bad)
    ds = board.GetDesignSettings()
    nc = ds.m_NetSettings.m_DefaultNetClass
    nc.SetClearance(MM(0.1))
    nc.SetTrackWidth(MM(0.15))
    nc.SetViaDiameter(MM(R.VIA_D))
    nc.SetViaDrill(MM(R.VIA_DRILL))
    ds.m_TrackMinWidth = MM(0.127)
    ds.m_ViasMinSize = MM(0.5)
    ds.m_MinThroughDrill = MM(0.3)
    ds.m_CopperEdgeClearance = MM(0.3)
    ds.m_HoleClearance = MM(0.25)
    ds.m_HoleToHoleMin = MM(0.25)
    ds.m_SilkClearance = MM(0.0)
    return board


def route(board, priority=()):
    rt = R.Router(board, place.W, place.H)
    t0 = time.time()
    # 2. signal nets
    by_net = {}
    for p in rt.pads:
        if p['net'] <= 0:
            continue
        name = board.FindNet(p['net']).GetNetname()
        if name in PLANE_NETS:
            continue
        by_net.setdefault(name, []).append(p)

    PRE = ['+1V1', 'XIN', 'XOUT', 'USB_DM', 'USB_DP']
    pre_ok = {}
    for n in PRE:
        ok = rt.route_net(by_net[n][0]['net'], [dict(p) for p in by_net[n]], w=width_for(n), margin=6, attract=None) or \
             rt.route_net(by_net[n][0]['net'], [dict(p) for p in by_net[n]], w=0.127, margin=6, attract=None)
        print('  pre-route', n, ok, flush=True)
        pre_ok[n] = ok
    for n in PRE:
        if pre_ok.get(n):
            by_net.pop(n, None)
    # 1. plane fan-outs
    fan_failed = []
    nfan = 0
    for p in rt.pads:
        if not p['smd']:
            continue
        name = board.FindNet(p['net']).GetNetname() if p['net'] > 0 else ''
        if name in PLANE_NETS:
            ref = p['ref']
            nv = 1
            if ref == 'U1' and p['num'] == '57':
                continue   # exposed pad has its own vias
            got = rt.fanout(p, p['net'], w=0.2, nvias=nv)
            nfan += got
            if got == 0:
                print('  fanout FAILED', ref, p['num'], name)
                fan_failed.append(p)
    print(f'fan-out vias: {nfan}  ({time.time() - t0:.1f}s)')
    def span(n):
        ps = by_net[n]
        xs = [p['c'][0] for p in ps]
        ys = [p['c'][1] for p in ps]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))
    order = [n for n in priority if n in by_net] + [n for n in HS_NETS if n in by_net and n not in priority]
    rest = sorted([n for n in by_net if n not in order and len(by_net[n]) > 1], key=span)
    # power first among the rest (they need room), then short to long
    rest = [n for n in rest if n in POWER_W or n.startswith('3V3_')] + \
           [n for n in rest if not (n in POWER_W or n.startswith('3V3_'))]
    order += rest
    # keep every differential pair together; the member that failed before goes first,
    # the second member is attracted to the first (coupled routing)
    paired = []
    done = set()
    for n in order:
        if n in done:
            continue
        base = n[:-3] if n.endswith(('_DP', '_DM')) else None
        if base and base + '_DP' in by_net and base + '_DM' in by_net:
            first = n
            other = base + ('_DM' if n.endswith('_DP') else '_DP')
            paired += [first, other]
            done |= {first, other}
        else:
            paired.append(n)
            done.add(n)
    order = paired
    failed = []
    routed_ok = set()
    for n in order:
        ps = by_net[n]
        w = width_for(n)
        ok = False
        for ww, marg in ((w, 4), (w, 10), (min(w, 0.2), 10), (0.15, 30), (0.127, 30)):
            snap = (len(rt.tracks), len(rt.vias), rt.occ.copy(), rt.viakeep.copy())
            t1 = time.time()
            att = None
            if n.endswith(('_DP', '_DM')):
                partner = n[:-3] + ('_DM' if n.endswith('_DP') else '_DP')
                if partner in routed_ok:
                    att = rt.netcode[partner]
            ok = rt.route_net(ps[0]['net'], [dict(p) for p in ps], w=ww, margin=marg, attract=att)
            if ok:
                break
            # roll back partial copper
            rt.tracks = rt.tracks[:snap[0]]
            rt.vias = rt.vias[:snap[1]]
            rt.occ, rt.viakeep = snap[2], snap[3]
        print(f'  {n:12s} {"ok" if ok else "FAIL"} w={ww} {time.time()-t1:.1f}s', flush=True)
        if ok:
            routed_ok.add(n)
        if not ok:
            failed.append(n)
    # pads whose plane via could not be placed: tie them to the nearest same-net pad instead
    for p in fan_failed:
        mates = [q for q in rt.pads if q['net'] == p['net'] and q is not p and q['smd'] and q['layers'] == p['layers']]
        mates.sort(key=lambda q: (q['c'][0] - p['c'][0]) ** 2 + (q['c'][1] - p['c'][1]) ** 2)
        ok = False
        for q in mates[:4]:
            if rt.route_net(p['net'], [dict(p), dict(q)], w=0.15, margin=4):
                ok = True
                break
        print('  tie', p['ref'], p['num'], ok)
        if not ok:
            failed.append(f"{p['ref']}.{p['num']}")
    print(f'routed {len(order) - len(failed)}/{len(order)} nets in {time.time() - t0:.1f}s; failed: {failed}')
    if not failed:
        for n, wmax in POWER_W.items():
            c = rt.fatten(rt.netcode[n], wmax)
        excl = [(0, 0, 3.0, place.H)]   # keep stitching vias out of the plug straddle zone
        ns = rt.stitch(rt.netcode['GND'], 2.0, excl)
        print('stitching vias', ns)
    rt.commit(board)
    return rt, failed


def zones(board):
    W, H = place.W, place.H
    nets = board.GetNetsByName()

    def zone(layer, net, prio, clr=0.25):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(nets[net])
        ol = z.Outline()
        ol.NewOutline()
        for x, y in [(0.3, 0.3), (W - 0.3, 0.3), (W - 0.3, H - 0.3), (0.3, H - 0.3)]:
            ol.Append(MM(x), MM(y))
        z.SetLocalClearance(MM(clr))
        z.SetMinThickness(MM(0.2))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(MM(0.3))
        z.SetThermalReliefSpokeWidth(MM(0.4))
        z.SetAssignedPriority(prio)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        board.Add(z)
        return z
    zone(pcbnew.In1_Cu, 'GND', 0)
    zone(pcbnew.In2_Cu, '+5V', 0)
    zone(pcbnew.F_Cu, 'GND', 0, 0.3)
    zone(pcbnew.B_Cu, 'GND', 0, 0.3)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())


if __name__ == '__main__':
    import json, os, ast
    prio = json.load(open('route_priority.json')) if os.path.exists('route_priority.json') else []
    for attempt in range(10):
        board = build()
        rt, failed = route(board, prio)
        if not failed:
            json.dump(prio, open('route_priority.json', 'w'))
            break
        prio = failed + [n for n in prio if n not in failed]
        print('RETRY with priority', prio, flush=True)
    pcbnew.SaveBoard('/tmp/routed.kicad_pcb', board)
    print('routed board saved', flush=True)
    # zones are poured by pour.py on the reloaded board (in-memory fill is unstable in KiCad 7 python)
    print('saved', OUTPCB)
