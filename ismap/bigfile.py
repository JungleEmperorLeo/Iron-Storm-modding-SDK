"""Read and rewrite Iron Storm bigfiles (Models.ibf + Models.lst)."""
import os, struct, shutil

def read_lst(path):
    d = open(path, 'rb').read()
    assert d[:8] == b'_TSL1.0V', 'not a .lst file'
    n = struct.unpack_from('<I', d, 8)[0]
    recs = []
    for i in range(n):
        r = d[12 + 72*i: 12 + 72*(i+1)]
        name = r[:64].split(b'\0')[0].decode('latin1')
        off, size = struct.unpack_from('<II', r, 64)
        recs.append((name, off, size, r))
    return recs

def read_file(ibf, lst, name):
    for n, off, size, _ in read_lst(lst):
        if n.lower() == name.lower():
            with open(ibf, 'rb') as f:
                f.seek(off); return f.read(size)
    return None

def _file_chunk(name, data):
    nm = name.encode('latin1') + b'\0'
    inner = (b'@nam' + struct.pack('<I', len(nm)) + nm + (b'\0' if len(nm) & 1 else b'')
             + b'SIZE' + struct.pack('<I', 4) + struct.pack('<I', len(data))
             + b'DATA' + struct.pack('<I', len(data)) + data + (b'\0' if len(data) & 1 else b''))
    return b'LIST' + struct.pack('<I', len(inner) + 4) + b'FILE' + inner, 12 + 8 + len(nm) + (len(nm) & 1) + 12 + 8

def replace_files(ibf, lst, files):
    """files: {name: bytes}. Removes existing entries with those names (case-insensitive) and appends new ones.
    Makes ibf.bak / lst.bak once (first run) so the stock archive can always be restored."""
    for p in (ibf, lst):
        if not os.path.exists(p + '.bak'): shutil.copy2(p, p + '.bak')
    drop = {k.lower() for k in files}
    recs = read_lst(lst)
    tmp = ibf + '.tmp'
    with open(ibf, 'rb') as src, open(tmp, 'wb') as out:
        head = src.read(12)
        assert head[:4] == b'RIFF' and head[8:12] == b'ISBF', 'not an Iron Storm .ibf'
        out.write(head)
        newrecs = []; slots = {}
        pos = 12; byname = {}
        for r in recs: byname.setdefault(r[1], r)
        src.seek(0, 2); end = src.tell(); src.seek(12)
        while pos < end:
            src.seek(pos); hdr = src.read(12)
            cid = hdr[:4]; sz = struct.unpack_from('<I', hdr, 4)[0]; total = 8 + sz + (sz & 1)
            src.seek(pos); blob = src.read(total)
            keep = True; rec = None
            if cid == b'LIST' and hdr[8:12] == b'FILE':
                # find DATA offset inside this chunk to match the lst record
                o = 12
                while o < len(blob):
                    c = blob[o:o+4]; s = struct.unpack_from('<I', blob, o+4)[0]
                    if c == b'DATA': rec = byname.get(pos + o + 8); dataoff = o + 8; break
                    o += 8 + s + (s & 1)
                if rec and rec[0].lower() in drop: keep = False; slots[rec[0].lower()] = len(newrecs); newrecs.append(None)   # keeps its place in the .lst
            if keep:
                newpos = out.tell(); out.write(blob)
                if rec:
                    r = bytearray(rec[3]); struct.pack_into('<I', r, 64, newpos + dataoff); newrecs.append(bytes(r))
            pos += total
        for name, data in files.items():
            blob, dataoff = _file_chunk(name, data)
            newpos = out.tell(); out.write(blob)
            r = bytearray(72); nb = name.encode('latin1') + b'\0'; r[:len(nb)] = nb
            struct.pack_into('<II', r, 64, newpos + dataoff, len(data))
            if name.lower() in slots: newrecs[slots[name.lower()]] = bytes(r)
            else: newrecs.append(bytes(r))
        total = out.tell(); out.seek(4); out.write(struct.pack('<I', total - 8))
    os.replace(tmp, ibf)
    newrecs = [r for r in newrecs if r is not None]
    open(lst, 'wb').write(b'_TSL1.0V' + struct.pack('<I', len(newrecs)) + b''.join(newrecs))
    return len(newrecs)
