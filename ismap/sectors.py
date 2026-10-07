"""Split a level into box-shaped sectors (rooms) and find the portals between them.

A sector is an axis-aligned box. Geometry is clipped to the boxes, and where two boxes touch the shared
face is sampled against the solid brushes: every connected open area becomes a portal (a 4-point rectangle)."""
import math

EPS = 1e-4
AX = ((1, 0, 0), (0, 1, 0), (0, 0, 1))

def _clip_poly(poly, axis, value, keep_greater):
    """clip [(pos, uv)] against pos[axis] >= value (keep_greater) or <= value"""
    out = []
    sgn = 1 if keep_greater else -1
    for k in range(len(poly)):
        p, q = poly[k], poly[(k + 1) % len(poly)]
        dp = sgn * (p[0][axis] - value); dq = sgn * (q[0][axis] - value)
        if dp >= -EPS: out.append(p)
        if (dp > EPS and dq < -EPS) or (dp < -EPS and dq > EPS):
            t = dp / (dp - dq)
            pos = tuple(p[0][i] + t * (q[0][i] - p[0][i]) for i in range(3))
            uv = tuple(p[1][i] + t * (q[1][i] - p[1][i]) for i in range(len(p[1]))) if p[1] is not None else None
            out.append((pos, uv))
    return out

def clip_to_box(poly, box):
    mn, mx = box
    for ax in range(3):
        poly = _clip_poly(poly, ax, mn[ax], True)
        if len(poly) < 3: return []
        poly = _clip_poly(poly, ax, mx[ax], False)
        if len(poly) < 3: return []
    return poly

def _area2(poly):
    a = [0, 0, 0]
    for k in range(len(poly)):
        p, q = poly[k][0], poly[(k + 1) % len(poly)][0]
        a[0] += p[1] * q[2] - p[2] * q[1]; a[1] += p[2] * q[0] - p[0] * q[2]; a[2] += p[0] * q[1] - p[1] * q[0]
    return math.sqrt(sum(x * x for x in a))

def _inside(box, p, pad=0.0):
    return all(box[0][i] - pad <= p[i] <= box[1][i] + pad for i in range(3))

def _drop_boundary_face(poly, n, box, boxes, me):
    """a face lying exactly on a box wall and facing out of the box belongs to the neighbour on the far side"""
    c = [sum(p[0][i] for p in poly) / len(poly) for i in range(3)]
    for ax in range(3):
        for side, val in ((1, box[1][ax]), (-1, box[0][ax])):
            if all(abs(p[0][ax] - val) < 1e-3 for p in poly) and n[ax] * side > 0.5:
                probe = list(c); probe[ax] += side * 0.05
                if any(j != me and _inside(b, probe) for j, b in enumerate(boxes)): return True
    return False

def partition(render, collide, boxes):
    """render: [(tex, (p0,p1,p2), (uv0,uv1,uv2), n)]  collide: [(tri, n, surf)]  -> per-box lists"""
    out_r = [[] for _ in boxes]; out_c = [[] for _ in boxes]; stray = 0
    def centre(tri): return [sum(p[i] for p in tri) / 3 for i in range(3)]
    def targets(tri):
        lo = [min(p[i] for p in tri) for i in range(3)]; hi = [max(p[i] for p in tri) for i in range(3)]
        t = [j for j, b in enumerate(boxes) if all(hi[i] >= b[0][i] - EPS and lo[i] <= b[1][i] + EPS for i in range(3))]
        if t: return t, True
        c = centre(tri)
        d = [sum(max(b[0][i] - c[i], 0, c[i] - b[1][i]) ** 2 for i in range(3)) for b in boxes]
        return [d.index(min(d))], False
    def fan(poly): return [(poly[0], poly[k], poly[k + 1]) for k in range(1, len(poly) - 1)]
    for tex, tri, uv, n in render:
        t, ok = targets(tri); stray += 0 if ok else 1
        for j in t:
            poly = [(tri[k], uv[k]) for k in range(3)]
            if ok:
                poly = clip_to_box(poly, boxes[j])
                if len(poly) < 3 or _area2(poly) < 1e-6 or _drop_boundary_face(poly, n, boxes[j], boxes, j): continue
            for a, b, c in fan(poly): out_r[j].append((tex, (a[0], b[0], c[0]), (a[1], b[1], c[1]), n))
    for item in collide:
        tri, n = item[0], item[1]
        t, ok = targets(tri)
        for j in t:
            poly = [(tri[k], None) for k in range(3)]
            if ok:
                poly = clip_to_box(poly, boxes[j])
                if len(poly) < 3 or _area2(poly) < 1e-6 or _drop_boundary_face(poly, n, boxes[j], boxes, j): continue
            for a, b, c in fan(poly): out_c[j].append(((a[0], b[0], c[0]), n) + tuple(item[2:]))
    return out_r, out_c, stray

def find_portals(boxes, solid_at, step=4.0, min_size=24.0, touch=0.5):
    """boxes in map units. solid_at(p) -> True when p is inside a solid brush.
    -> [dict(a, b, quad (counter-clockwise about 'normal'), normal (points into sector a))]"""
    portals = []
    for a in range(len(boxes)):
        for b in range(a + 1, len(boxes)):
            A, B = boxes[a], boxes[b]
            for ax in range(3):
                for sa, va, vb in ((1, A[1][ax], B[0][ax]), (-1, A[0][ax], B[1][ax])):
                    if abs(va - vb) > touch: continue
                    u, v = [i for i in range(3) if i != ax]
                    lo_u = max(A[0][u], B[0][u]); hi_u = min(A[1][u], B[1][u])
                    lo_v = max(A[0][v], B[0][v]); hi_v = min(A[1][v], B[1][v])
                    if hi_u - lo_u < 1 or hi_v - lo_v < 1: continue
                    plane = (va + vb) / 2
                    nu = max(1, int(math.ceil((hi_u - lo_u) / step))); nv = max(1, int(math.ceil((hi_v - lo_v) / step)))
                    while nu * nv > 90000: step *= 1.5; nu = max(1, int(math.ceil((hi_u - lo_u) / step))); nv = max(1, int(math.ceil((hi_v - lo_v) / step)))
                    du = (hi_u - lo_u) / nu; dv = (hi_v - lo_v) / nv
                    def pt(iu, iv):
                        p = [0, 0, 0]; p[ax] = plane; p[u] = lo_u + (iu + 0.5) * du; p[v] = lo_v + (iv + 0.5) * dv; return p
                    # sample slightly to both sides of the plane: a cell is open only if both sides are open
                    def blocked(iu, iv):
                        p = pt(iu, iv)
                        for off in (-0.5, 0.5):
                            q = list(p); q[ax] += off
                            if solid_at(q): return True
                        return False
                    open_ = [[not blocked(iu, iv) for iv in range(nv)] for iu in range(nu)]
                    seen = [[False] * nv for _ in range(nu)]
                    for iu in range(nu):
                        for iv in range(nv):
                            if not open_[iu][iv] or seen[iu][iv]: continue
                            stack = [(iu, iv)]; seen[iu][iv] = True; cells = []
                            while stack:
                                x, y = stack.pop(); cells.append((x, y))
                                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                                    X, Y = x + dx, y + dy
                                    if 0 <= X < nu and 0 <= Y < nv and open_[X][Y] and not seen[X][Y]:
                                        seen[X][Y] = True; stack.append((X, Y))
                            u0 = min(c[0] for c in cells); u1 = max(c[0] for c in cells) + 1
                            v0 = min(c[1] for c in cells); v1 = max(c[1] for c in cells) + 1
                            wu = (u1 - u0) * du; wv = (v1 - v0) * dv
                            if wu < min_size or wv < min_size: continue
                            U0, U1 = lo_u + u0 * du, lo_u + u1 * du; V0, V1 = lo_v + v0 * dv, lo_v + v1 * dv
                            def P(pu, pv):
                                p = [0, 0, 0]; p[ax] = plane; p[u] = pu; p[v] = pv; return tuple(p)
                            normal = [0, 0, 0]; normal[ax] = float(sa)       # into sector a: a lies on the side the face looks out of... see below
                            normal[ax] = -float(sa)
                            quad = [P(U0, V0), P(U1, V0), P(U1, V1), P(U0, V1)]
                            # wind counter-clockwise about the normal
                            e1 = [quad[1][i] - quad[0][i] for i in range(3)]; e2 = [quad[2][i] - quad[0][i] for i in range(3)]
                            cr = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
                            if sum(cr[i] * normal[i] for i in range(3)) < 0: quad = quad[::-1]
                            portals.append(dict(a=a, b=b, quad=quad, normal=tuple(normal)))
    return portals
