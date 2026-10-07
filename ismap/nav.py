"""AI navigation graph (.icp) for Iron Storm levels.

File layout (reverse-engineered from the stock campaign .icp files and Game.exe's loader):
  16 bytes  'IRONSTORM      \\0'
  u32       0x019d6421 (version)
  f32       unit       (path cost per D step; we use max path length / 65000)
  u32       N          node count
  N x node:
    u8      flag (2 in every stock file)
    3 f32   position (game units, at floor level)
    u32 N + N x u16   next hop towards node j (0xFFFF = unreachable, own index for itself)
    u32 N + N x u8    visibility: 3 = line of sight, 1 = none (stock files also use 0)
    u32 N + N x u8    6 = reachable, 255 = itself or unreachable (stock files have rare 1/2)
    u32 N + N x u16   path cost to node j, 0..65000 (65535 = unreachable)
    u32 0             (an optional byte list, empty in every stock file)
All coordinates below are map units until written; scale converts to game units."""
import heapq, math, struct

STEP = 20.0        # map units: highest step a soldier walks up
HEIGHT = 72.0      # map units: soldier height
EYE = 56.0

def _seg_hits(brushes, a, b):
    """True if segment a-b passes through the inside of any brush."""
    lo = [min(a[k], b[k]) for k in range(3)]; hi = [max(a[k], b[k]) for k in range(3)]
    d = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    for planes, blo, bhi in brushes:
        if blo[0] > hi[0] or bhi[0] < lo[0] or blo[1] > hi[1] or bhi[1] < lo[1] or blo[2] > hi[2] or bhi[2] < lo[2]:
            continue
        t0, t1 = 0.0, 1.0
        for n, dd in planes:
            den = n[0]*d[0] + n[1]*d[1] + n[2]*d[2]
            num = dd - (n[0]*a[0] + n[1]*a[1] + n[2]*a[2]) - 0.05
            if abs(den) < 1e-9:
                if num <= 0: break
                continue
            t = num / den
            if den > 0:
                if t < t1: t1 = t
            elif t > t0: t0 = t
            if t0 >= t1: break
        else:
            if t1 - t0 > 1e-4: return True
    return False

def _inside(brushes, p):
    for planes, lo, hi in brushes:
        if all(lo[k] - 0.01 <= p[k] <= hi[k] + 0.01 for k in range(3)) and \
           all(n[0]*p[0] + n[1]*p[1] + n[2]*p[2] - d < -0.05 for n, d in planes):
            return True
    return False

def _point_in_poly(x, y, poly):
    inside = False; n = len(poly)
    for i in range(n):
        x1, y1 = poly[i][0], poly[i][1]; x2, y2 = poly[(i+1) % n][0], poly[(i+1) % n][1]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1): inside = not inside
    return inside

def nodes_from_floors(floors, brushes, grid):
    """floors: list of polygons (map units) of upward faces. Returns floor points with headroom."""
    pts = {}
    for poly in floors:
        n = _normal(poly)
        if n[2] < 0.7: continue
        d = sum(n[k] * poly[0][k] for k in range(3))
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        gx0 = math.ceil(min(xs) / grid - 0.5); gx1 = math.floor(max(xs) / grid - 0.5)
        gy0 = math.ceil(min(ys) / grid - 0.5); gy1 = math.floor(max(ys) / grid - 0.5)
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                x, y = (gx + 0.5) * grid, (gy + 0.5) * grid
                if not _point_in_poly(x, y, poly): continue
                z = (d - n[0]*x - n[1]*y) / n[2]
                if any(_inside(brushes, (x + ox, y + oy, z + h)) for h in (2.0, 36.0, HEIGHT - 4)
                       for ox, oy in ((0, 0), (12, 0), (-12, 0), (0, 12), (0, -12))):
                    continue              # no headroom, or too close to a wall
                key = (gx, gy, round(z / 8))
                pts[key] = (x, y, z)
    return list(pts.values())

def _normal(poly):
    a, b, c = poly[0], poly[1], poly[2]
    u = [b[k] - a[k] for k in range(3)]; v = [c[k] - a[k] for k in range(3)]
    n = [u[1]*v[2] - u[2]*v[1], u[2]*v[0] - u[0]*v[2], u[0]*v[1] - u[1]*v[0]]
    l = math.sqrt(sum(x*x for x in n)) or 1.0
    return [x / l for x in n]

def _walkable(brushes, a, b):
    if abs(a[2] - b[2]) > STEP: return False
    for h in (STEP + 2, 40.0, HEIGHT - 4):
        if _seg_hits(brushes, (a[0], a[1], a[2] + h), (b[0], b[1], b[2] + h)): return False
    L = math.dist(a[:2], b[:2]); n = max(1, int(L / 12))
    for i in range(1, n):                 # ground under the whole way
        t = i / n; p = [a[k] + (b[k] - a[k]) * t for k in range(3)]
        if not _seg_hits(brushes, (p[0], p[1], p[2] + 2), (p[0], p[1], p[2] - STEP - 4)): return False
    return True

def build(floors, brushes, scale, grid=96.0, log=print, seeds=()):
    pts = nodes_from_floors(floors, brushes, grid)
    N = len(pts)
    if N == 0: return None, 0
    if N > 2000: raise ValueError('%d navigation points; raise worldspawn navgrid' % N)
    # links between grid neighbours (and diagonals)
    cell = {}
    for i, p in enumerate(pts): cell.setdefault((round(p[0] / grid - 0.5), round(p[1] / grid - 0.5)), []).append(i)
    adj = [[] for _ in range(N)]
    for i, p in enumerate(pts):
        cx, cy = round(p[0] / grid - 0.5), round(p[1] / grid - 0.5)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in cell.get((cx + dx, cy + dy), ()):
                    if j > i and _walkable(brushes, p, pts[j]):
                        w = math.dist(p, pts[j]); adj[i].append((j, w)); adj[j].append((i, w))
    # keep only the walkable areas the level's characters stand in (drops roofs, wall tops, closets)
    comp = [-1] * N; nc = 0
    for i in range(N):
        if comp[i] >= 0: continue
        stack = [i]; comp[i] = nc
        while stack:
            u = stack.pop()
            for v, w in adj[u]:
                if comp[v] < 0: comp[v] = nc; stack.append(v)
        nc += 1
    want = set()
    for sp in seeds:
        best = min(range(N), key=lambda i: math.dist(pts[i], sp))
        if math.dist(pts[best], sp) < 2 * grid: want.add(comp[best])
    if not want:
        sizes = {}
        for c in comp: sizes[c] = sizes.get(c, 0) + 1
        want = {max(sizes, key=sizes.get)}
    keep = [i for i in range(N) if comp[i] in want and adj[i]]
    if len(keep) < N:
        ren = {o: n for n, o in enumerate(keep)}
        pts = [pts[i] for i in keep]
        adj = [[(ren[j], w) for j, w in adj[i]] for i in keep]
        N = len(pts)
        if N == 0: return None, 0
    # all-pairs shortest paths (Dijkstra from every node), next hop towards each target
    dist = []; nxt = []
    for s in range(N):
        D = [math.inf] * N; first = [0xFFFF] * N; D[s] = 0.0; first[s] = s
        h = [(0.0, s)]
        while h:
            dd, u = heapq.heappop(h)
            if dd > D[u]: continue
            for v, w in adj[u]:
                nd = dd + w
                if nd < D[v] - 1e-9:
                    D[v] = nd; first[v] = v if u == s else first[u]; heapq.heappush(h, (nd, v))
        dist.append(D); nxt.append(first)
    # first[v] above is the first step from s towards v
    finite = [d for row in dist for d in row if d < math.inf]
    maxc = max(finite) * scale if finite else 1.0
    k = 65000.0 / maxc if maxc > 0 else 1.0
    # line of sight between eye heights
    vis = [[1] * N for _ in range(N)]
    for i in range(N):
        vis[i][i] = 3
        ai = (pts[i][0], pts[i][1], pts[i][2] + EYE)
        for j in range(i + 1, N):
            if not _seg_hits(brushes, ai, (pts[j][0], pts[j][1], pts[j][2] + EYE)): vis[i][j] = vis[j][i] = 3
    out = bytearray(b'IRONSTORM      \0') + struct.pack('<IfI', 0x019d6421, maxc / 65000.0 if maxc > 0 else 1.0, N)
    for i, p in enumerate(pts):
        out += struct.pack('<B3f', 2, p[0] * scale, p[1] * scale, p[2] * scale)
        out += struct.pack('<I%dH' % N, N, *nxt[i])
        out += struct.pack('<I', N) + bytes(vis[i])
        out += struct.pack('<I', N) + bytes(255 if (j == i or dist[i][j] == math.inf) else 6 for j in range(N))
        out += struct.pack('<I%dH' % N, N, *[65535 if dist[i][j] == math.inf else min(65000, int(round(dist[i][j] * scale * k))) for j in range(N)])
        out += struct.pack('<I', 0)
    links = sum(len(a) for a in adj) // 2
    log('navigation: %d points, %d links (grid %g)' % (N, links, grid))
    return bytes(out), N
