"""Tiny RIFF-style chunk tree for Iron Storm .4x3 records: parse a record into a tree, edit it, serialise it again."""
import struct

class Chunk:
    def __init__(self, cid, data=None, form=None, kids=None):
        self.cid, self.data, self.form, self.kids = cid, data, form, kids
    @property
    def is_list(self): return self.kids is not None
    def name(self):
        for k in self.kids or []:
            if k.cid == b'@nam': return k.data.split(b'\0')[0].decode('latin1')
        return None
    def pack(self):
        if self.is_list:
            body = self.form + b''.join(k.pack() for k in self.kids)
            cid = self.cid
        else: body, cid = self.data, self.cid
        return cid + struct.pack('<I', len(body)) + body + (b'\0' if len(body) & 1 else b'')

def parse(b, off=0, end=None):
    end = len(b) if end is None else end
    out = []
    while off + 8 <= end:
        cid = b[off:off + 4]; sz = struct.unpack_from('<I', b, off + 4)[0]
        body = b[off + 8:off + 8 + sz]
        if cid in (b'LIST', b'ALIS'):
            out.append(Chunk(cid, form=body[:4], kids=parse(b, off + 12, off + 8 + sz)))
        else: out.append(Chunk(cid, data=body))
        off += 8 + sz + (sz & 1)
    return out

def pack(chunks): return b''.join(c.pack() for c in chunks)

def find_lists(chunks, form=None, name=None):
    """All list chunks (any depth) with the given form and/or node name."""
    res = []
    for c in chunks:
        if c.is_list:
            if (form is None or c.form == form) and (name is None or c.name() == name): res.append(c)
            res += find_lists(c.kids, form, name)
    return res
