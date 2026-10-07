"""Patch a compiled Iron Storm GEL level script (.gex).

The KYWD section is a flat list of instructions:  (index, opcode, argc) + argc x 5-word operands.
A constant operand is (string_offset, 0xFFFFFFFF, int, float_bits, int); the string lives in KYWT.
We only rewrite operands of existing instructions and append new strings to KYWT, so
instruction count, labels and variables stay untouched."""
import struct

def _f2u(v): return struct.unpack('<I', struct.pack('<f', v))[0]

class Gex:
    def __init__(self, data):
        self.d = bytearray(data)
        assert self.d[:4] == b'GELX'
        self.sec = {}
        o = 8
        while o < len(self.d):
            tag = bytes(self.d[o:o+4]); sz = struct.unpack_from('<I', self.d, o+4)[0]
            self.sec.setdefault(tag, o)
            if sz < 8: break
            o += sz
        k = self.sec[b'KYWD']; n = (struct.unpack_from('<I', self.d, k+4)[0]-8)//4
        self.w = list(struct.unpack_from('<%dI' % n, self.d, k+8))
        t = self.sec[b'KYWT']; tl = struct.unpack_from('<I', self.d, self.sec[b'NKWT']+8)[0]
        self.tab = bytearray(self.d[t+8:t+8+tl])
        self.ins = []
        i = 0
        while i + 3 <= len(self.w):
            idx, opc, argc = self.w[i:i+3]
            self.ins.append((i, opc, argc)); i += 3 + 5*argc

    def s(self, off):
        return self.tab[off:self.tab.index(b'\0', off)].decode('latin1')

    def string(self, text):
        b = text.encode('latin1') + b'\0'
        i = self.tab.find(b'\0' + b)
        if i >= 0: return i + 1
        if self.tab.startswith(b): return 0
        off = len(self.tab); self.tab += b
        return off

    def op(self, i, j):          # word index of operand j of instruction at word i
        return i + 3 + 5*j

    def calls(self, func=None):
        """yield (word_index, [operand strings]) for call instructions (opcode 55)."""
        for i, opc, argc in self.ins:
            if opc != 55: continue
            names = []
            for j in range(argc):
                o = self.op(i, j); names.append(self.s(self.w[o]) if self.w[o] < len(self.tab) else None)
            if func is None or names[0] == func:
                yield i, names

    def set_const(self, i, j, value, fmt='%f'):
        if isinstance(value, int) and fmt == '%f': fmt = '%d'
        text = fmt % value if not isinstance(value, str) else value
        o = self.op(i, j)
        if isinstance(value, str):
            self.w[o:o+5] = [self.string(text), 0xFFFFFFFF, 0, 0, 0]
            return
        iv = int(value) & 0xFFFFFFFF
        self.w[o:o+5] = [self.string(text), 0xFFFFFFFF, iv, _f2u(float(value)), iv]

    def set_prop(self, entity, prop, *values, func=None):
        """set the constant arguments of every set_property_* call on (entity, prop)."""
        hit = 0
        for i, names in self.calls(func):
            if names[0] and names[0].startswith('set_property') and names[1] == entity and names[2] == prop:
                for j, v in enumerate(values): self.set_const(i, 3+j, v)
                hit += 1
        return hit

    def entities(self, prefix):
        out = []
        for i, names in self.calls('create_entity'):
            pass
        for i, opc, argc in self.ins:
            if opc == 15 and argc == 2:
                name = self.s(self.w[self.op(i, 0)])
                if name.startswith(prefix): out.append(name)
        return out

    def get_vec(self, entity, prop):
        for i, names in self.calls('set_property_vector'):
            if names[1] == entity and names[2] == prop:
                return [struct.unpack('<f', struct.pack('<I', self.w[self.op(i, 3+j)+3]))[0] for j in range(3)]

    def tobytes(self):
        d = self.d
        k = self.sec[b'KYWD']
        struct.pack_into('<%dI' % len(self.w), d, k+8, *self.w)
        tab = bytes(self.tab) + b'\0' * ((-len(self.tab)) % 4)
        t = self.sec[b'KYWT']; oldsz = struct.unpack_from('<I', d, t+4)[0]
        out = bytearray(d[:t]) + b'KYWT' + struct.pack('<I', len(tab)+8) + tab + d[t+oldsz:]
        struct.pack_into('<I', out, self.sec[b'NKWT']+8, len(tab))
        delta = len(tab)+8 - oldsz
        hdr = struct.unpack_from('<I', out, 4)[0]
        if hdr > t: struct.pack_into('<I', out, 4, hdr + delta)
        return bytes(out)
