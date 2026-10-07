"""Parse a Trenchbroom/Quake .map (Valve 220 or Standard format) and turn brushes into polygons."""
import re, math

def _tokens(text):
    text = re.sub(r'//[^\n]*', '', text)
    for m in re.finditer(r'"([^"]*)"|([(){}\[\]])|([^\s(){}\[\]"]+)', text):
        if m.group(1) is not None: yield ('str', m.group(1))
        elif m.group(2): yield ('sym', m.group(2))
        else: yield ('word', m.group(3))

def parse(text):
    """-> list of entities: {'props': {...}, 'brushes': [[face,...],...]}
       face = {'pts': 3 points, 'tex': name, 'U': (ux,uy,uz,off) | None, 'V':..., 'rot', 'sx', 'sy', 'off': (ox,oy)}"""
    toks = list(_tokens(text)); i = 0; ents = []
    def num(): 
        nonlocal i; v = float(toks[i][1]); i += 1; return v
    def expect(s):
        nonlocal i
        if toks[i][1] != s: raise ValueError('expected %s near token %d (%r)' % (s, i, toks[i]))
        i += 1
    while i < len(toks):
        expect('{'); ent = {'props': {}, 'brushes': []}
        while toks[i][1] != '}':
            if toks[i][0] == 'str':
                k = toks[i][1]; v = toks[i+1][1]; ent['props'][k] = v; i += 2; continue
            expect('{'); brush = []
            if toks[i][0] == 'word' and toks[i][1] in ('patchDef2', 'brushDef', 'brushDef3'):
                raise ValueError('only Standard/Valve brush format is supported')
            while toks[i][1] != '}':
                pts = []
                for _ in range(3):
                    expect('('); pts.append((num(), num(), num())); expect(')')
                tex = toks[i][1]; i += 1
                f = {'pts': pts, 'tex': tex}
                if toks[i][1] == '[':
                    expect('['); U = (num(), num(), num(), num()); expect(']')
                    expect('['); V = (num(), num(), num(), num()); expect(']')
                    f.update(U=U, V=V, rot=num(), sx=num(), sy=num())
                else:
                    f.update(U=None, V=None, off=(num(), num()), rot=num(), sx=num(), sy=num())
                # skip optional Quake2/3 extras (content, surface, value)
                while i < len(toks) and toks[i][0] == 'word' and toks[i][1] not in ('}',) and toks[i][1] != '(' and re.fullmatch(r'-?[\d.eE+-]+', toks[i][1]):
                    i += 1
                brush.append(f)
            expect('}'); ent['brushes'].append(brush)
        expect('}'); ents.append(ent)
    return ents

def sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def dot(a, b): return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def norm(a):
    l = math.sqrt(dot(a, a)); return (a[0]/l, a[1]/l, a[2]/l)

def face_plane(f):
    p1, p2, p3 = f['pts']
    n = norm(cross(sub(p3, p1), sub(p2, p1)))      # outward normal (Quake convention)
    return n, dot(n, p1)

def brush_polygons(brush, eps=1e-3):
    """-> [(face, normal, [points CCW about the outward normal])]"""
    planes = [face_plane(f) for f in brush]
    out = []
    for fi, f in enumerate(brush):
        n, d = planes[fi]
        # big quad on the plane
        a = (1, 0, 0) if abs(n[0]) < 0.9 else (0, 1, 0)
        u = norm(cross(n, a)); v = cross(n, u)       # u,v,n right-handed -> CCW about n
        c = (n[0]*d, n[1]*d, n[2]*d); S = 1e5
        poly = [tuple(c[k] + s*u[k]*S + t*v[k]*S for k in range(3)) for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        for fj, (m, e) in enumerate(planes):
            if fj == fi or not poly: continue
            new = []
            for k in range(len(poly)):
                p = poly[k]; q = poly[(k+1) % len(poly)]
                dp = dot(m, p) - e; dq = dot(m, q) - e
                if dp <= eps: new.append(p)
                if (dp < -eps and dq > eps) or (dp > eps and dq < -eps):
                    t = dp / (dp - dq); new.append(tuple(p[k2] + t*(q[k2]-p[k2]) for k2 in range(3)))
            poly = new
        # drop duplicate points
        clean = []
        for p in poly:
            if not clean or max(abs(p[k]-clean[-1][k]) for k in range(3)) > eps: clean.append(p)
        if len(clean) > 1 and max(abs(clean[0][k]-clean[-1][k]) for k in range(3)) <= eps: clean.pop()
        clean = [tuple(round(x * 1024) / 1024 for x in p) for p in clean]
        if len(clean) >= 3: out.append((f, n, clean))
    return out

# Quake 'Standard' format texture axes
_BASEAXIS = [((0,0,1),(1,0,0),(0,-1,0)), ((0,0,-1),(1,0,0),(0,-1,0)), ((1,0,0),(0,1,0),(0,0,-1)),
             ((-1,0,0),(0,1,0),(0,0,-1)), ((0,1,0),(1,0,0),(0,0,-1)), ((0,-1,0),(1,0,0),(0,0,-1))]

def face_uv(f, n, p, w, h):
    sx = f['sx'] or 1.0; sy = f['sy'] or 1.0
    if f['U'] is not None:
        U, V = f['U'], f['V']
        s = (dot(p, U[:3]) / sx + U[3]) / w; t = (dot(p, V[:3]) / sy + V[3]) / h
        return (s, t)
    best = max(range(6), key=lambda k: dot(n, _BASEAXIS[k][0]))
    ua, va = _BASEAXIS[best][1], _BASEAXIS[best][2]
    ang = math.radians(f['rot']); c, s_ = math.cos(ang), math.sin(ang)
    s = dot(p, ua); t = dot(p, va)
    s, t = c*s - s_*t, s_*s + c*t
    return ((s / sx + f['off'][0]) / w, (t / sy + f['off'][1]) / h)
