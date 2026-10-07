"""Replace the visible mesh of a stock Iron Storm model (weapon, pickup, ...) with a mesh imported from an .obj, keeping the
model's node tree (muzzle / ejection dummies, pivots) so the game still finds what it attaches things to."""
import struct, os
from . import chunks as C
from .repack import read_map_bytes, write_map
from .scene import texture_record, f4, u4, chunk, lst, sphere, HEAD
from .texio import encode_dxt1

def _pot(im):
    w, h = im.size; W = max(4, 1 << (w - 1).bit_length()); H = max(4, 1 << (h - 1).bit_length())
    return im if (W, H) == (w, h) else im.resize((W, H))

def build_prim(tris, tex_id, mat_id):
    """tris: [(texture key, [(pos, uv, normal) x3])] -> a LIST PRIM chunk. Vertices are shared by (pos, normal), uvs separately."""
    keys = []
    for t, _ in tris:
        if t not in keys: keys.append(t)
    vmap, pos, nrm, umap, uvs = {}, [], [], {}, []
    face = [(0x90, mat_id)]; indx = []; first = True
    for key in keys:
        group = [vs for t, vs in tris if t == key]
        face.append((0x80, tex_id[key]))
        if first: face.append((0x1000, 0x10002)); first = False
        for vs in group:
            indx.append(3)
            for p, uv, n in vs:
                vk = (tuple(round(x, 5) for x in p), tuple(round(x, 4) for x in n))
                if vk not in vmap: vmap[vk] = len(pos); pos.append(p); nrm.append(n)
                uk = (round(uv[0], 5), round(uv[1], 5))
                if uk not in umap: umap[uk] = len(uvs); uvs.append((uv[0], 1.0 - uv[1]))     # obj v runs bottom-up
                indx.append(vmap[vk] | (umap[uk] << 16))
        face.append((5, len(group)))
    if len(pos) > 65535 or len(uvs) > 65535: raise ValueError('mesh too big: %d vertices / %d uvs (limit 65535)' % (len(pos), len(uvs)))
    c, r = sphere(pos)
    vrtx = (u4(0x132, len(pos)) + b''.join(f4(*p, 1.0) for p in pos) + u4(len(nrm)) + b''.join(f4(*q, 1.0) for q in nrm)
            + u4(0) + u4(len(uvs)) + b''.join(f4(*uv) for uv in uvs) + b'\0' * 28)
    return C.Chunk(b'LIST', form=b'PRIM', kids=[C.Chunk(b'vrtx', vrtx), C.Chunk(b'bsph', f4(*c, 1.0, r)),
                   C.Chunk(b'face', b''.join(u4(a, b) for a, b in face)), C.Chunk(b'indx', u4(*indx))]), len(pos), len(uvs), len(indx)

def swap_mesh(stock, tris, textures, node=None, keep_children=False, log=print):
    """stock: bytes of a stock .4x3. tris: [(texture key, verts)]; textures: {key: PIL image}. Returns new .4x3 bytes."""
    head, recs, tags, _ = read_map_bytes(stock)
    ni = [i for i, t in enumerate(tags) if t == b'NODE']
    if not ni: raise ValueError('stock model has no NODE record')
    tree = C.parse(recs[ni[0]])
    meshes = C.find_lists(tree, b'MESH')
    if not meshes: raise ValueError('stock model has no MESH node')
    target = next((m for m in meshes if node and m.name() == node), meshes[0] if not node else None)
    if target is None: raise ValueError('no mesh node %r (have: %s)' % (node, ', '.join(m.name() or '?' for m in meshes)))
    mat_ids = [struct.unpack_from('<I', C.parse(r)[0].data)[0] for r, t in zip(recs, tags) if t == b'MATL']
    mat_id = mat_ids[0]
    # fresh ids for the new textures, above anything the model already uses
    used = [struct.unpack_from('<I', C.parse(r)[0].data)[0] for r in recs if C.parse(r) and C.parse(r)[0].cid == b'def!']
    nxt = max(used + [0]) + 1; tex_id = {}
    for k in textures: tex_id[k] = nxt; nxt += 1
    prim, nv, nu, ni_ = build_prim(tris, tex_id, mat_id)
    target.kids = [prim if (k.is_list and k.form == b'PRIM') else k for k in target.kids]
    if not any(k is prim for k in target.kids): target.kids.insert(0, prim)
    if not keep_children:
        removed = [k.name() for k in target.kids if k.is_list and k.form == b'MESH']
        target.kids = [k for k in target.kids if not (k.is_list and k.form == b'MESH')]
        if removed: log('  removed child meshes: ' + ', '.join(str(n) for n in removed))
    newrecs = [C.pack(tree)]; newtags = [b'NODE']
    tex_recs = [texture_record(tex_id[k], k, textures[k]) for k in textures]
    old_tex = [(r, t) for r, t in zip(recs, tags) if t == b'TEXU'] if keep_children else []
    others = [(r, t) for r, t in zip(recs, tags) if t not in (b'NODE', b'TEXU')]
    out_recs = [r for r, _ in old_tex] + tex_recs + [r for r, _ in others] + newrecs
    out_tags = [t for _, t in old_tex] + [b'TEXU'] * len(tex_recs) + [t for _, t in others] + newtags
    log('  mesh %r: %d vertices, %d uvs, %d index entries, %d texture(s)' % (target.name(), nv, nu, ni_, len(textures)))
    import tempfile
    tmp = tempfile.mktemp(suffix='.4x3'); data = write_map(tmp, head, out_recs, out_tags); os.remove(tmp)
    return data

def mesh_bbox(stock, node=None):
    """Bounding box of the named (or first) mesh node of a stock model, from its vrtx chunk."""
    head, recs, tags, _ = read_map_bytes(stock)
    tree = C.parse(next(r for r, t in zip(recs, tags) if t == b'NODE'))
    meshes = C.find_lists(tree, b'MESH')
    m = next((x for x in meshes if node and x.name() == node), meshes[0])
    pr = next(k for k in m.kids if k.is_list and k.form == b'PRIM'); vr = next(k for k in pr.kids if k.cid == b'vrtx').data
    n = struct.unpack_from('<I', vr, 4)[0]
    P = [struct.unpack_from('<3f', vr, 8 + 16 * k) for k in range(n)]
    return [min(p[i] for p in P) for i in range(3)], [max(p[i] for p in P) for i in range(3)]
