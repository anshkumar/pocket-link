"""Tiny helpers for pulling symbol blocks out of KiCad .kicad_sym libraries."""
import re

SYMDIR = '/usr/share/kicad/symbols'
_cache = {}


def _lib(lib):
    if lib not in _cache:
        _cache[lib] = open(f'{SYMDIR}/{lib}.kicad_sym').read()
    return _cache[lib]


def block_at(s, i):
    """return s[i:j] for the balanced (...) starting at i"""
    depth = 0
    instr = False
    j = i
    while True:
        ch = s[j]
        if instr:
            if ch == '\\':
                j += 1
            elif ch == '"':
                instr = False
        else:
            if ch == '"':
                instr = True
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    return s[i:j + 1]
        j += 1


def raw_symbol(lib, name):
    s = _lib(lib)
    i = s.find(f'(symbol "{name}"')
    if i < 0:
        raise KeyError(f'{lib}:{name}')
    return block_at(s, i)


def prop(blk, key):
    m = re.search(r'\(property "%s" "((?:[^"\\]|\\.)*)"' % re.escape(key), blk)
    return m.group(1) if m else None


def set_prop(blk, key, val):
    def rep(m):
        return f'(property "{key}" "{val}"'
    return re.sub(r'\(property "%s" "((?:[^"\\]|\\.)*)"' % re.escape(key), rep, blk, count=1)


def flat_symbol(lib_id):
    """Return symbol text renamed to lib_id, with 'extends' resolved."""
    lib, name = lib_id.split(':')
    blk = raw_symbol(lib, name)
    m = re.search(r'\(extends "([^"]+)"\)', blk)
    if m:
        parent = m.group(1)
        pblk = raw_symbol(lib, parent)
        for key in ('Value', 'Footprint', 'Datasheet', 'ki_description', 'ki_keywords', 'ki_fp_filters'):
            v = prop(blk, key)
            if v is not None and prop(pblk, key) is not None:
                pblk = set_prop(pblk, key, v)
        pblk = pblk.replace(f'(symbol "{parent}_', f'(symbol "{name}_')
        pblk = pblk.replace(f'(symbol "{parent}"', f'(symbol "{name}"', 1)
        blk = pblk
    blk = blk.replace(f'(symbol "{name}"', f'(symbol "{lib_id}"', 1)
    return blk


def pins(blk):
    """list of dicts: number, name, type, x, y, angle, length, hidden"""
    out = []
    for m in re.finditer(r'\(pin (\w+) (\w+)', blk):
        pb = block_at(blk, m.start())
        at = re.search(r'\(at ([-\d.]+) ([-\d.]+) ?([-\d.]*)\)', pb)
        ln = re.search(r'\(length ([-\d.]+)\)', pb)
        nm = re.search(r'\(name "([^"]*)"', pb)
        nu = re.search(r'\(number "([^"]*)"', pb)
        out.append(dict(number=nu.group(1), name=nm.group(1), type=m.group(1),
                        x=float(at.group(1)), y=float(at.group(2)), angle=float(at.group(3) or 0),
                        length=float(ln.group(1)) if ln else 0, hidden=' hide' in pb.split('(name')[0]))
    return out


def graphics_bbox(blk):
    xs, ys = [], []
    for m in re.finditer(r'\((?:start|end|xy|center) ([-\d.]+) ([-\d.]+)\)', blk):
        xs.append(float(m.group(1)))
        ys.append(float(m.group(2)))
    for p in pins(blk):
        xs.append(p['x'])
        ys.append(p['y'])
    return min(xs), min(ys), max(xs), max(ys)
