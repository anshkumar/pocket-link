"""numba A* over a 2-layer grid with 8 directions, turn and via costs."""
import numpy as np
from numba import njit

DJ = np.array([1, 1, 0, -1, -1, -1, 0, 1], np.int64)
DI = np.array([0, 1, 1, 1, 0, -1, -1, -1], np.int64)


@njit(cache=True)
def _push(hk, hv, n, key, val):
    hk[n] = key
    hv[n] = val
    i = n
    while i > 0:
        p = (i - 1) >> 1
        if hk[p] <= hk[i]:
            break
        hk[p], hk[i] = hk[i], hk[p]
        hv[p], hv[i] = hv[i], hv[p]
        i = p
    return n + 1


@njit(cache=True)
def _pop(hk, hv, n):
    k, v = hk[0], hv[0]
    n -= 1
    hk[0] = hk[n]
    hv[0] = hv[n]
    i = 0
    while True:
        l = 2 * i + 1
        r = l + 1
        m = i
        if l < n and hk[l] < hk[m]:
            m = l
        if r < n and hk[r] < hk[m]:
            m = r
        if m == i:
            break
        hk[m], hk[i] = hk[i], hk[m]
        hv[m], hv[i] = hv[i], hv[m]
        i = m
    return k, v, n


@njit(cache=True)
def astar(passable, goal, src, vmap, tht, ti, tj, via_cost, turn_cost, maxit, extra):
    L, h, w = passable.shape
    N = L * h * w * 9
    g = np.full(N, 1e30, np.float32)
    par = np.full(N, -1, np.int64)
    closed = np.zeros(N, np.bool_)
    cap = 4_000_000
    hk = np.empty(cap, np.float32)
    hv = np.empty(cap, np.int64)
    n = 0
    for l in range(L):
        for i in range(h):
            for j in range(w):
                if src[l, i, j]:
                    s = ((l * h + i) * w + j) * 9 + 8
                    g[s] = 0.0
                    dx = abs(j - tj)
                    dy = abs(i - ti)
                    hh = max(dx, dy) - min(dx, dy) + 1.4142 * min(dx, dy)
                    if n < cap:
                        n = _push(hk, hv, n, hh, s)
    it = 0
    while n > 0:
        it += 1
        if it > maxit:
            return np.empty(0, np.int64)
        f, s, n = _pop(hk, hv, n)
        if closed[s]:
            continue
        closed[s] = True
        d = s % 9
        cell = s // 9
        j = cell % w
        i = (cell // w) % h
        l = cell // (w * h)
        if goal[l, i, j]:
            # rebuild
            cnt = 0
            t = s
            while t != -1:
                cnt += 1
                t = par[t]
            out = np.empty(cnt, np.int64)
            t = s
            k = cnt - 1
            while t != -1:
                out[k] = t
                k -= 1
                t = par[t]
            return out
        gs = g[s]
        for k in range(8):
            ni = i + DI[k]
            nj = j + DJ[k]
            if ni < 0 or nj < 0 or ni >= h or nj >= w:
                continue
            if not passable[l, ni, nj]:
                continue
            if DI[k] != 0 and DJ[k] != 0:
                if not (passable[l, i, nj] and passable[l, ni, j]):
                    continue
                step = 1.4142
            else:
                step = 1.0
            if d != 8 and d != k:
                step += turn_cost
            step += extra[l, ni, nj]
            ns = ((l * h + ni) * w + nj) * 9 + k
            ng = gs + step
            if ng < g[ns]:
                g[ns] = ng
                par[ns] = s
                dx = abs(nj - tj)
                dy = abs(ni - ti)
                hh = max(dx, dy) - min(dx, dy) + 1.4142 * min(dx, dy)
                if n < cap:
                    n = _push(hk, hv, n, ng + hh, ns)
        if L == 2 and (vmap[i, j] or tht[i, j]):
            ol = 1 - l
            if passable[ol, i, j]:
                ns = ((ol * h + i) * w + j) * 9 + 8
                ng = gs + via_cost
                if ng < g[ns]:
                    g[ns] = ng
                    par[ns] = s
                    dx = abs(j - tj)
                    dy = abs(i - ti)
                    hh = max(dx, dy) - min(dx, dy) + 1.4142 * min(dx, dy)
                    if n < cap:
                        n = _push(hk, hv, n, ng + hh, ns)
    return np.empty(0, np.int64)
