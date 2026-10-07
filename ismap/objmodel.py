"""Wavefront .obj -> triangles, with the transforms needed to drop a modelled object into an Iron Storm model."""
import os, math

def load_obj(path):
    """Returns (tris, mtl) where tris = [(material, [(pos, uv, normal) x3])] and mtl = {material: texture file or None}."""
    P, T, N = [], [], []; tris = []; cur = 'default'; mtl = {}; base = os.path.dirname(path)
    def rd_mtl(fn):
        p = os.path.join(base, fn)
        if not os.path.exists(p): return
        name = None
        for ln in open(p, errors='replace'):
            w = ln.split()
            if not w: continue
            if w[0] == 'newmtl': name = ' '.join(w[1:]); mtl.setdefault(name, None)
            elif w[0].lower() == 'map_kd' and name: mtl[name] = os.path.join(base, ln.split(None, 1)[1].strip().split()[-1].replace('\\', '/'))
    def idx(s, n):
        i = int(s); return i - 1 if i > 0 else n + i
    for ln in open(path, errors='replace'):
        w = ln.split()
        if not w or w[0].startswith('#'): continue
        if w[0] == 'v': P.append(tuple(float(x) for x in w[1:4]))
        elif w[0] == 'vt': T.append((float(w[1]), float(w[2]) if len(w) > 2 else 0.0))
        elif w[0] == 'vn': N.append(tuple(float(x) for x in w[1:4]))
        elif w[0] == 'mtllib': rd_mtl(' '.join(w[1:]))
        elif w[0] == 'usemtl': cur = ' '.join(w[1:]); mtl.setdefault(cur, None)
        elif w[0] == 'f':
            vs = []
            for t in w[1:]:
                a = (t.split('/') + ['', ''])[:3]
                vs.append((P[idx(a[0], len(P))], T[idx(a[1], len(T))] if a[1] else (0.0, 0.0), N[idx(a[2], len(N))] if a[2] else None))
            for k in range(1, len(vs) - 1): tris.append((cur, [vs[0], vs[k], vs[k + 1]]))
    return tris, mtl

AXES = {   # how the .obj axes map to the game's (x right, y forward-ish, z up)
    'zup':     lambda p: (p[0], p[1], p[2]),         # z up, barrel along -y: the 3ds Max / Blender convention the stock models use
    'yup':     lambda p: (-p[0], p[2], p[1]),        # y up, -z forward (Blender .obj export default): barrel -z -> game -y (a proper rotation)
    'yup_fwd': lambda p: (p[0], -p[2], p[1]),        # y up, +z forward: barrel +z -> game -y
}

def _sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def _cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def _norm(v):
    l = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2) or 1.0
    return (v[0]/l, v[1]/l, v[2]/l)

def transform(tris, axes='yup', scale=1.0, offset=(0, 0, 0), fit=None):
    """Apply axis mapping, then either fit to a target bbox ((mn),(mx): uniform scale to its longest side, centred on it)
    or scale/offset. Normals are recomputed to agree with the triangle winding (the game's visible side is cross(v1-v0, v2-v0))."""
    f = AXES[axes]; out = []
    for m, vs in tris:
        out.append((m, [(f(p), uv, (_norm(f(n)) if n else None)) for p, uv, n in vs]))
    pts = [p for _, vs in out for p, _, _ in vs]
    mn = [min(p[i] for p in pts) for i in range(3)]; mx = [max(p[i] for p in pts) for i in range(3)]
    if fit:
        tmn, tmx = fit
        k = max(tmx[i] - tmn[i] for i in range(3)) / (max(mx[i] - mn[i] for i in range(3)) or 1.0)
        c0 = [(mn[i] + mx[i]) / 2 for i in range(3)]; c1 = [(tmn[i] + tmx[i]) / 2 for i in range(3)]
        tf = lambda p: tuple((p[i] - c0[i]) * k + c1[i] for i in range(3))
    else:
        tf = lambda p: tuple(p[i] * scale + offset[i] for i in range(3))
    res = []
    for m, vs in out:
        vs = [(tf(p), uv, n) for p, uv, n in vs]
        fn = _norm(_cross(_sub(vs[1][0], vs[0][0]), _sub(vs[2][0], vs[0][0])))
        # the axis map can mirror the model: keep the stored vertex normals on the side the winding faces
        ns = [n if n else fn for _, _, n in vs]
        if sum(a * b for a, b in zip(fn, ns[0])) < 0:
            vs = [vs[0], vs[2], vs[1]]; ns = [ns[0], ns[2], ns[1]]
        res.append((m, [(p, uv, n) for (p, uv, _), n in zip(vs, ns)]))
    return res
