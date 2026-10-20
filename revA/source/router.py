"""Grid-based clearance-aware A* router for 2 signal layers (F.Cu / B.Cu).

Inner layers are planes (GND / +5V) and are reached with fan-out vias.
Not a general autorouter: it is tuned for this board (short local nets,
generous placement) and every result is checked by KiCad's own DRC.
"""
import heapq
import math
import numpy as np
from scipy import ndimage
import pcbnew

MM = pcbnew.FromMM
G = 0.1            # grid pitch, mm
CLR = 0.11         # copper clearance used for routing (DRC rule 0.15; fab min 0.09 at JLC)
MARGIN = 0.06      # raster safety margin
VIA_D = 0.6
VIA_DRILL = 0.3
EDGE_CLR = 0.3
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


def attract_pitch(w):
    return w + 0.15 + 0.0   # centre-to-centre distance of a coupled pair (edge gap 0.15 mm)


class Router:
    def __init__(self, board, W, H):
        self.board = board
        self.W, self.H = W, H
        self.nx, self.ny = int(round(W / G)) + 1, int(round(H / G)) + 1
        self.occ = np.zeros((2, self.ny, self.nx), np.int32)      # net code, -1 = no-net obstacle
        self.viakeep = np.zeros((self.ny, self.nx), np.int32)     # SMD pads: no vias (any net), value=net
        self.netcode = {}
        for n, ni in board.GetNetsByName().items():
            self.netcode[str(n)] = ni.GetNetCode()
        self.tracks = []    # (net, layer, x1, y1, x2, y2, w)
        self.vias = []      # (net, x, y)
        self._edges()
        self._pads()

    # ------------------------------------------------------------- raster
    def ij(self, x, y):
        return int(round(y / G)), int(round(x / G))

    def _grid(self, x0, y0, x1, y1):
        i0, i1 = max(0, int(math.floor(y0 / G))), min(self.ny - 1, int(math.ceil(y1 / G)))
        j0, j1 = max(0, int(math.floor(x0 / G))), min(self.nx - 1, int(math.ceil(x1 / G)))
        return i0, i1, j0, j1

    def mark_rect(self, arr, x0, y0, x1, y1, val):
        i0, i1, j0, j1 = self._grid(x0, y0, x1, y1)
        ys = np.arange(i0, i1 + 1) * G
        xs = np.arange(j0, j1 + 1) * G
        my = (ys >= y0 - 1e-9) & (ys <= y1 + 1e-9)
        mx = (xs >= x0 - 1e-9) & (xs <= x1 + 1e-9)
        sub = arr[i0:i1 + 1, j0:j1 + 1]
        m = np.outer(my, mx)
        sub[m] = val

    def mark_circle(self, arr, cx, cy, r, val):
        i0, i1, j0, j1 = self._grid(cx - r, cy - r, cx + r, cy + r)
        ys = np.arange(i0, i1 + 1)[:, None] * G
        xs = np.arange(j0, j1 + 1)[None, :] * G
        m = (xs - cx) ** 2 + (ys - cy) ** 2 <= r * r + 1e-9
        arr[i0:i1 + 1, j0:j1 + 1][m] = val

    def mark_seg(self, arr, x1, y1, x2, y2, r, val):
        i0, i1, j0, j1 = self._grid(min(x1, x2) - r, min(y1, y2) - r, max(x1, x2) + r, max(y1, y2) + r)
        ys = np.arange(i0, i1 + 1)[:, None] * G
        xs = np.arange(j0, j1 + 1)[None, :] * G
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        if L2 == 0:
            t = 0
        else:
            t = np.clip(((xs - x1) * dx + (ys - y1) * dy) / L2, 0, 1)
        px, py = x1 + t * dx, y1 + t * dy
        m = (xs - px) ** 2 + (ys - py) ** 2 <= r * r + 1e-9
        arr[i0:i1 + 1, j0:j1 + 1][m] = val

    def _edges(self):
        e = int(math.ceil(EDGE_CLR / G))
        for l in range(2):
            self.occ[l, :e, :] = -1
            self.occ[l, -e:, :] = -1
            self.occ[l, :, :e] = -1
            self.occ[l, :, -e:] = -1

    def pad_shape(self, pad):
        bb = pad.GetBoundingBox()
        x0, y0, x1, y1 = bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6
        circ = pad.GetShape() in (pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL) and abs(pad.GetSize().x - pad.GetSize().y) < 1000
        return circ, (x0, y0, x1, y1)

    def _pads(self):
        self.pads = []
        for fp in self.board.GetFootprints():
            for pad in fp.Pads():
                net = pad.GetNetCode()
                attr = pad.GetAttribute()
                circ, (x0, y0, x1, y1) = self.pad_shape(pad)
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                val = net if net > 0 else -1
                ls = [l for l, L in enumerate(LAYERS) if pad.IsOnLayer(L)]
                if attr == pcbnew.PAD_ATTRIB_NPTH:
                    ls = [0, 1]
                    val = -1
                    d = max(pad.GetDrillSize().x, pad.GetDrillSize().y) / 1e6
                    for l in ls:
                        self.mark_circle(self.occ[l], cx, cy, d / 2 + 0.2, -1)
                    self.mark_circle(self.viakeep, cx, cy, d / 2 + 0.5, -1)
                    continue
                for l in ls:
                    if circ:
                        self.mark_circle(self.occ[l], cx, cy, (x1 - x0) / 2 + MARGIN / 2, val)
                    else:
                        m = MARGIN / 2
                        self.mark_rect(self.occ[l], x0 - m, y0 - m, x1 + m, y1 + m, val)
                if attr == pcbnew.PAD_ATTRIB_SMD:
                    self.mark_rect(self.viakeep, x0 - 0.1, y0 - 0.1, x1 + 0.1, y1 + 0.1, -1)
                else:
                    d = max(pad.GetDrillSize().x, pad.GetDrillSize().y) / 1e6
                    self.mark_circle(self.viakeep, cx, cy, d / 2 + 0.45, -1)
                self.pads.append(dict(pad=pad, net=net, layers=ls, rect=(x0, y0, x1, y1), circ=circ,
                                      c=(cx, cy), smd=attr == pcbnew.PAD_ATTRIB_SMD, ref=fp.GetReference(),
                                      num=pad.GetNumber()))

    # ------------------------------------------------------------- legality maps
    def free_map(self, net, hw, win):
        """True where a track of half-width hw for `net` may be centred."""
        i0, i1, j0, j1 = win
        out = []
        for l in range(2):
            sub = self.occ[l, i0:i1 + 1, j0:j1 + 1]
            foreign = (sub != 0) & (sub != net)
            if not foreign.any():
                out.append(np.ones_like(foreign))
                continue
            dist = ndimage.distance_transform_edt(~foreign) * G
            out.append(dist >= CLR + hw + MARGIN)
        return out

    def via_map(self, net, win, free=None):
        i0, i1, j0, j1 = win
        r = VIA_D / 2
        ok = np.ones((i1 - i0 + 1, j1 - j0 + 1), bool)
        for l in range(2):
            sub = self.occ[l, i0:i1 + 1, j0:j1 + 1]
            foreign = (sub != 0) & (sub != net)
            if foreign.any():
                dist = ndimage.distance_transform_edt(~foreign) * G
                ok &= dist >= CLR + r + MARGIN
        vk = self.viakeep[i0:i1 + 1, j0:j1 + 1] != 0
        if vk.any():
            dist = ndimage.distance_transform_edt(~vk) * G
            ok &= dist >= r
        # hole-to-hole spacing to existing vias
        return ok

    # ------------------------------------------------------------- commit
    def add_track(self, net, l, x1, y1, x2, y2, w):
        self.tracks.append((net, l, x1, y1, x2, y2, w))
        self.mark_seg(self.occ[l], x1, y1, x2, y2, w / 2 + MARGIN / 2, net)

    def add_via(self, net, x, y):
        self.vias.append((net, x, y))
        for l in range(2):
            self.mark_circle(self.occ[l], x, y, VIA_D / 2 + MARGIN / 2, net)
        self.mark_circle(self.viakeep, x, y, VIA_D / 2 + 0.25, -2)

    # ------------------------------------------------------------- fan-out to planes
    def fanout(self, pinfo, net, w=0.2, nvias=1, rmax=4.0):
        """connect an SMD pad to the inner plane with a short stub + via."""
        cx, cy = pinfo['c']
        x0, y0, x1, y1 = pinfo['rect']
        win = self._grid(cx - rmax - 1, cy - rmax - 1, cx + rmax + 1, cy + rmax + 1)
        i0, i1, j0, j1 = win
        placed = 0
        for _ in range(nvias):
            vm = self.via_map(net, win)
            fm = self.free_map(net, w / 2, win)[pinfo['layers'][0]]
            best = None
            ii, jj = np.nonzero(vm)
            if len(ii) == 0:
                break
            xs = (jj + j0) * G
            ys = (ii + i0) * G
            # distance from via centre to pad edge
            dx = np.maximum(np.maximum(x0 - xs, xs - x1), 0)
            dy = np.maximum(np.maximum(y0 - ys, ys - y1), 0)
            d = np.hypot(dx, dy)
            order = np.argsort(d + 0.05 * np.hypot(xs - cx, ys - cy))
            for k in order[:400]:
                if d[k] > rmax:
                    break
                vx, vy = xs[k], ys[k]
                # stub from nearest point of pad to via must be clear on F.Cu
                px, py = min(max(vx, x0), x1), min(max(vy, y0), y1)
                if self._seg_clear(fm, win, px, py, vx, vy):
                    best = (vx, vy, px, py)
                    break
            if not best:
                break
            vx, vy, px, py = best
            l = pinfo['layers'][0]
            self.add_track(net, l, cx, cy, vx, vy, w) if (abs(px - vx) + abs(py - vy)) > 1e-6 else None
            self.add_via(net, vx, vy)
            placed += 1
        return placed

    def _seg_clear(self, fm, win, x1, y1, x2, y2):
        i0, i1, j0, j1 = win
        n = int(max(abs(x2 - x1), abs(y2 - y1)) / (G / 2)) + 1
        for t in np.linspace(0, 1, n + 1):
            x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            i, j = int(round(y / G)) - i0, int(round(x / G)) - j0
            if not (0 <= i < fm.shape[0] and 0 <= j < fm.shape[1]) or not fm[i, j]:
                return False
        return True

    # ------------------------------------------------------------- A*
    def route_net(self, net, pads, w=0.2, margin=6.0, via_cost=14, turn_cost=1.0, layer_bias=None, attract=None):
        """connect all pads (list of pinfo) of one net. returns True on success."""
        hw = w / 2
        xs = [p['c'][0] for p in pads]
        ys = [p['c'][1] for p in pads]
        win = self._grid(min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)
        i0, i1, j0, j1 = win
        h, wd = i1 - i0 + 1, j1 - j0 + 1
        free = self.free_map(net, hw, win)
        vmap = self.via_map(net, win)
        # pads of this net count as free (their own copper)
        own = [(self.occ[l, i0:i1 + 1, j0:j1 + 1] == net) for l in range(2)]
        extra = np.full((2, h, wd), 0.0, np.float32)
        if attract is not None:
            # differential-pair coupling: cheap to run ~pitch away from the partner trace
            for l in range(2):
                part = self.occ[l, i0:i1 + 1, j0:j1 + 1] == attract
                if part.any():
                    dist = ndimage.distance_transform_edt(~part) * G
                    extra[l] = np.where(np.abs(dist - attract_pitch(w)) < 0.12, 0.0, 0.45).astype(np.float32)
        connected = [pads[0]]
        todo = pads[1:]
        new_tracks = []
        while todo:
            # tree = own-net copper that is connected: approximate by copper of connected pads + routed tracks
            src = np.zeros((2, h, wd), bool)
            for p in connected:
                for l in p['layers']:
                    self._pad_cells(src[l], p, win)
            for (l, xa, ya, xb, yb) in new_tracks:
                self._seg_cells(src[l], xa, ya, xb, yb, win)
            # nearest remaining pad
            todo.sort(key=lambda p: min(math.hypot(p['c'][0] - q['c'][0], p['c'][1] - q['c'][1]) for q in connected))
            tgt = todo[0]
            goal = np.zeros((2, h, wd), bool)
            for l in tgt['layers']:
                self._pad_cells(goal[l], tgt, win)
            path = self._astar(src, goal, free, own, self._layerswitch_mask(net, win), vmap, tgt['c'], win, via_cost, turn_cost, extra)
            if path is None:
                return False
            segs = self._path_to_segments(path, win, net)
            for s in segs:
                if s[0] == 'via':
                    _, x, y = s
                    self.add_via(net, x, y)
                    vmap = self.via_map(net, win)
                else:
                    _, l, xa, ya, xb, yb = s
                    self.add_track(net, l, xa, ya, xb, yb, w)
                    new_tracks.append((l, xa, ya, xb, yb))
            # refresh own copper & free maps (our own new copper doesn't block us)
            own = [(self.occ[l, i0:i1 + 1, j0:j1 + 1] == net) for l in range(2)]
            connected.append(tgt)
            todo = todo[1:]
        return True

    def _pad_cells(self, arr, p, win):
        i0, i1, j0, j1 = win
        x0, y0, x1, y1 = p['rect']
        cx, cy = p['c']
        # use the inner part of the pad so tracks end well inside it
        sx, sy = (x1 - x0) / 2, (y1 - y0) / 2
        sx, sy = max(sx - 0.1, 0.05), max(sy - 0.1, 0.05)
        if p['circ']:
            sx = sy = max(min(sx, sy) * 0.6, 0.05)
        ia, ib = int(math.ceil((cy - sy) / G)) - i0, int(math.floor((cy + sy) / G)) - i0
        ja, jb = int(math.ceil((cx - sx) / G)) - j0, int(math.floor((cx + sx) / G)) - j0
        if ib < ia:
            ia = ib = int(round(cy / G)) - i0
        if jb < ja:
            ja = jb = int(round(cx / G)) - j0
        arr[max(ia, 0):ib + 1, max(ja, 0):jb + 1] = True

    def _seg_cells(self, arr, xa, ya, xb, yb, win):
        i0, i1, j0, j1 = win
        n = int(max(abs(xb - xa), abs(yb - ya)) / G) + 1
        for t in np.linspace(0, 1, n + 1):
            i = int(round((ya + (yb - ya) * t) / G)) - i0
            j = int(round((xa + (xb - xa) * t) / G)) - j0
            if 0 <= i < arr.shape[0] and 0 <= j < arr.shape[1]:
                arr[i, j] = True

    def _layerswitch_mask(self, net, win):
        i0, i1, j0, j1 = win
        m = np.zeros((i1 - i0 + 1, j1 - j0 + 1), np.bool_)
        for (n, x, y) in self.vias:
            if n == net:
                i, j = int(round(y / G)) - i0, int(round(x / G)) - j0
                if 0 <= i < m.shape[0] and 0 <= j < m.shape[1]:
                    m[i, j] = True
        for p in self.pads:
            if p['net'] == net and not p['smd'] and len(p['layers']) == 2:
                i, j = int(round(p['c'][1] / G)) - i0, int(round(p['c'][0] / G)) - j0
                if 0 <= i < m.shape[0] and 0 <= j < m.shape[1]:
                    m[i, j] = True
        return m

    def _astar(self, src, goal, free, own, tht, vmap, tc, win, via_cost, turn_cost, extra):
        from astar_nb import astar
        i0, i1, j0, j1 = win
        h, wd = src.shape[1], src.shape[2]
        passable = np.stack([free[l] | own[l] | goal[l] for l in range(2)]).astype(np.bool_)
        res = astar(passable, goal.astype(np.bool_), src.astype(np.bool_), vmap.astype(np.bool_), tht,
                    tc[1] / G - i0, tc[0] / G - j0, float(via_cost), float(turn_cost), 3_000_000, extra)
        if len(res) == 0:
            return None
        path = []
        for s in res:
            d = s % 9
            cell = s // 9
            j = cell % wd
            i = (cell // wd) % h
            l = cell // (wd * h)
            path.append((int(l), int(i), int(j), int(d)))
        return path

    def _path_to_segments(self, path, win, net):
        i0, i1, j0, j1 = win
        segs = []
        pts = [(l, (j + j0) * G, (i + i0) * G) for (l, i, j, d) in path]
        existing = [(x, y) for (n, x, y) in self.vias if n == net] + \
                   [p['c'] for p in self.pads if p['net'] == net and not p['smd'] and len(p['layers']) == 2]
        # split by layer
        cur = [pts[0]]
        for p in pts[1:]:
            if p[0] != cur[-1][0]:
                self._emit(cur, segs)
                if not any(abs(p[1] - x) < 0.051 and abs(p[2] - y) < 0.051 for x, y in existing):
                    segs.append(('via', p[1], p[2]))
                cur = [p]
            else:
                cur.append(p)
        self._emit(cur, segs)
        return segs

    def _emit(self, pts, segs):
        if len(pts) < 2:
            return
        l = pts[0][0]
        # merge collinear
        out = [pts[0]]
        for k in range(1, len(pts) - 1):
            a, b, c = out[-1], pts[k], pts[k + 1]
            d1 = (round((b[1] - a[1]) / G), round((b[2] - a[2]) / G))
            d2 = (round((c[1] - b[1]) / G), round((c[2] - b[2]) / G))
            g1, g2 = math.gcd(abs(d1[0]), abs(d1[1])) or 1, math.gcd(abs(d2[0]), abs(d2[1])) or 1
            if (d1[0] // g1, d1[1] // g1) != (d2[0] // g2, d2[1] // g2):
                out.append(b)
        out.append(pts[-1])
        for a, b in zip(out, out[1:]):
            segs.append(('trk', l, a[1], a[2], b[1], b[2]))

    # ------------------------------------------------------------- write to board
    def commit(self, board):
        nets = board.GetNetsByName()
        bycode = {ni.GetNetCode(): ni for ni in nets.values()}
        for (net, l, x1, y1, x2, y2, w) in self.tracks:
            if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(MM(float(x1)), MM(float(y1))))
            t.SetEnd(pcbnew.VECTOR2I(MM(float(x2)), MM(float(y2))))
            t.SetWidth(MM(w))
            t.SetLayer(LAYERS[l])
            t.SetNet(bycode[net])
            board.Add(t)
        for (net, x, y) in self.vias:
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(MM(float(x)), MM(float(y))))
            v.SetWidth(MM(VIA_D))
            v.SetDrill(MM(VIA_DRILL))
            v.SetNet(bycode[net])
            board.Add(v)


def _fatten(self, net, wmax):
    """widen already-routed segments of `net` up to wmax where clearance allows."""
    changed = 0
    for k, (n, l, x1, y1, x2, y2, w) in enumerate(self.tracks):
        if n != net or w >= wmax - 1e-6:
            continue
        for wn in (wmax, (wmax + w) / 2):
            if wn <= w:
                continue
            win = self._grid(min(x1, x2) - 3, min(y1, y2) - 3, max(x1, x2) + 3, max(y1, y2) + 3)
            fm = self.free_map(net, wn / 2, win)[l]
            if self._seg_clear(fm, win, x1, y1, x2, y2):
                self.tracks[k] = (n, l, x1, y1, x2, y2, wn)
                self.mark_seg(self.occ[l], x1, y1, x2, y2, wn / 2 + MARGIN / 2, net)
                changed += 1
                break
    return changed


def _stitch(self, net, pitch, excl):
    """GND stitching vias on a grid wherever legal (not inside excluded rectangles)."""
    n = 0
    win = (0, self.ny - 1, 0, self.nx - 1)
    y = 1.5
    while y < self.H - 1.0:
        x = 1.5
        while x < self.W - 1.0:
            if not any(a <= x <= c and b <= y <= d for (a, b, c, d) in excl):
                lw = self._grid(x - 2, y - 2, x + 2, y + 2)
                vm = self.via_map(net, lw)
                i, j = int(round(y / G)) - lw[0], int(round(x / G)) - lw[2]
                if 0 <= i < vm.shape[0] and 0 <= j < vm.shape[1] and vm[i, j]:
                    self.add_via(net, round(x, 2), round(y, 2))
                    n += 1
            x += pitch
        y += pitch
    return n


Router.fatten = _fatten
Router.stitch = _stitch
