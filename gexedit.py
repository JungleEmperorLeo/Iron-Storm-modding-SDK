#!/usr/bin/env python3
"""gexedit - turn a compiled Iron Storm level script (.gex) into readable text, and back.

    python gexedit.py dump  level.gex [-o level.gexs]          # text listing
    python gexedit.py build level.gexs --base level.gex -o new.gex   # reassemble (other chunks come from --base)
    python gexedit.py check level.gex                          # round-trip self test

Text format (one instruction per line, labels as ':name' lines, ';N' = source line, '#' comments):

    :create_heli
    call !set_property_float $id_helico "17+BASE_PROPERTY_HELICOPTER"#d1 $heli_sound_start ;1204
    callf @heli_move $id_helico -3543 -505 -150

  operands
    12  -3.5            number constant              "text"        string constant
    "name"#d1           string constant that also carries the number 0xd1 (property names)
    "x"{w2,w3,w4}       string/number constant with explicit raw words (hex), only when unusual
    $name               script variable (declared in VARB as gel::name)   $name#id  built-in variable with id
    $name/1             variable operand whose second word is 1
    !name               engine function (the first operand of 'call')
    @name               a label: user function or jump target
    ?"text":w1:w2:w3:w4 anything else, raw words in hex

  '.var NAME HEX16'     declares a variable (VARB record); variables you use that are not declared are added.
Opcodes are written by name when known (call, callf, set, jne, ...), else opNN.
"""
import struct, re, sys, argparse

NBUILTIN = 51
OPS = {55: 'call', 3: 'callf', 15: 'set', 32: 'jne', 6: 'ret', 7: 'end', 1: 'func', 5: 'return0'}
OPN = {v: k for k, v in OPS.items()}
MASK = 0xFFFFFFFF

def f2u(v): return struct.unpack('<I', struct.pack('<f', float(v)))[0]
def u2f(u): return struct.unpack('<f', struct.pack('<I', u))[0]

def chunks(d):
    out = []; o = 8
    while o < len(d):
        tag = bytes(d[o:o+4]); sz = struct.unpack_from('<I', d, o+4)[0]
        out.append([tag, bytes(d[o+8:o+sz])])
        if sz < 8: break
        o += sz
    return out, o

class Script:
    """parsed view of the code-related chunks."""
    def __init__(self, data):
        self.data = data
        self.chunks, self.end = chunks(data)
        c = dict((t, p) for t, p in self.chunks)
        self.tab = c[b'KYWT']
        kw = c[b'KYWD']; self.w = list(struct.unpack('<%dI' % (len(kw)//4), kw))
        self.ins = []; i = 0
        while i + 3 <= len(self.w):
            idx, opc, argc = self.w[i:i+3]; self.ins.append((i, opc, argc)); i += 3 + 5*argc
        self.labels = []; p = c[b'LABE']; i = 0
        while i + 8 <= len(p):
            off, n = struct.unpack_from('<II', p, i); self.labels.append((off, p[i+8:i+8+n].split(b'\0')[0].decode('latin1'))); i += 8 + n
        self.vars = []; p = c[b'VARB']; i = 0
        while i < len(p):
            ln = struct.unpack_from('<I', p, i)[0]; nm = p[i+4:i+4+ln].split(b'\0')[0].decode('latin1')
            self.vars.append((nm, p[i+4+ln:i+12+ln])); i += 12 + ln

    def s(self, off):
        if off >= len(self.tab): return None
        e = self.tab.index(b'\0', off); return self.tab[off:e].decode('latin1')

NUM = re.compile(r'-?\d+(\.\d*)?')

def derive(text):
    v = float(text); i = int(v) & MASK if v == int(v) else 0
    return [MASK, i, f2u(v), i]

def quote(s): return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

def dump(data):
    sc = Script(data); vnames = {nm: n for n, (nm, _) in enumerate(sc.vars)}
    LN = {}
    for off, nm in sc.labels: LN.setdefault(nm, off)
    out = ['# gexedit text; instructions %d, labels %d, variables %d' % (len(sc.ins), len(sc.labels), len(sc.vars))]
    for nm, tail in sc.vars: out.append('.var %s %s' % (nm, tail.hex()))
    out.append('.code')
    bylabel = {}
    for off, nm in sc.labels: bylabel.setdefault(off, []).append(nm)
    def opnd(i, j):
        o = i + 3 + 5*j; w = sc.w[o:o+5]; s = sc.s(w[0])
        if s is None: return '?%s:%x:%x:%x:%x' % ((quote(''),) + tuple(w[1:]))
        if w[1] == MASK:
            if NUM.fullmatch(s) and w[1:] == derive(s): return s
            if w[2] == w[4] and w[3] == f2u(w[2]) and not NUM.fullmatch(s): return '%s#%x' % (quote(s), w[2]) if w[2] else quote(s)
            if w[2:] == [0, 0, 0] and not NUM.fullmatch(s): return quote(s)
            return '%s{%x,%x,%x}' % (quote(s), w[2], w[3], w[4])
        if w[1] == 0xFFFFFFF1 and w[2:4] == [MASK, 0xBF800000]: return '!' + s
        if w[1] == 0xFFFFFFFC and s in LN and w[2] == LN[s] and w[3] == f2u(w[2]): return '@' + s
        if w[1] < 0xFFFFF000 and w[3] == f2u(w[1]):
            vn = 'gel::' + s
            ref = '$' + s if (w[1] >= NBUILTIN and w[1] - NBUILTIN < len(sc.vars) and sc.vars[w[1] - NBUILTIN][0] == vn) else '$%s#%x' % (s, w[1])
            if w[1] < NBUILTIN or '$' + s == ref:
                return ref + ('/%x' % w[2] if w[2] else '')
        return '?%s:%x:%x:%x:%x' % ((quote(s),) + tuple(w[1:]))
    n = len(sc.ins)
    for k, (i, opc, argc) in enumerate(sc.ins):
        for nm in bylabel.get(k, []): out.append(':' + nm)
        out.append('  %s %s ;%d' % (OPS.get(opc, 'op%d' % opc), ' '.join(opnd(i, j) for j in range(argc)), sc.w[i]) if argc else '  %s ;%d' % (OPS.get(opc, 'op%d' % opc), sc.w[i]))
    for nm in bylabel.get(n, []): out.append(':' + nm)
    return '\n'.join(out) + '\n'

TOK = re.compile(r'''\s*(?:
    (?P<q>\?)?(?P<str>"(?:[^"\\]|\\.)*")(?P<ext>\#[0-9a-fA-F]+|\{[0-9a-fA-F,]+\}|(?::[0-9a-fA-F]+){4})?
  | (?P<tok>[^\s"]+) )''', re.X)

def unq(q): return re.sub(r'\\(.)', r'\1', q[1:-1])

def build(text, base):
    sc = Script(base)
    vars_ = []; vindex = {}
    code = []        # (opcode, line, [operand tokens as tuples])
    labels = []      # (offset, name) in file order
    ntab0 = struct.unpack('<I', dict((t, p) for t, p in sc.chunks)[b'NKWT'])[0]
    tabs = bytearray(sc.tab[:ntab0]); tabi = {}      # keep the original string table (other chunks may point into it) and append to it
    o = 0
    while o < len(tabs):
        e = tabs.index(b'\0', o); tabi.setdefault(bytes(tabs[o:e]).decode('latin1'), o); o = e + 1
    def string(t):
        if t in tabi: return tabi[t]
        o = len(tabs); tabs.extend(t.encode('latin1') + b'\0'); tabi[t] = o; return o
    string('')
    def tail_default(): return b'\0' * 8
    ln_no = 0; incode = False; lastline = 0
    for raw in text.split('\n'):
        ln_no += 1
        line = raw.strip()
        if not line or line.startswith('#'): continue
        if line.startswith('.var '):
            _, nm, hx = line.split(); vindex[nm] = len(vars_); vars_.append((nm, bytes.fromhex(hx))); continue
        if line == '.code': incode = True; continue
        if line.startswith(':'): labels.append((len(code), line[1:])); continue
        # instruction
        m = re.match(r'(\w+)\s*(.*)$', line)
        mn = m.group(1); rest = m.group(2)
        opc = OPN[mn] if mn in OPN else (int(mn[2:]) if re.fullmatch(r'op\d+', mn) else None)
        if opc is None: raise ValueError('line %d: unknown opcode %r' % (ln_no, mn))
        lineno = lastline
        # strip trailing ;N (outside quotes)
        mm = re.search(r'\s;(\d+)\s*$', ' ' + rest)
        if mm: lineno = int(mm.group(1)); rest = (' ' + rest)[:mm.start()].strip()
        lastline = lineno
        toks = []; pos = 0
        while pos < len(rest):
            t = TOK.match(rest, pos)
            if not t or t.end() == pos: raise ValueError('line %d: cannot read operands near %r' % (ln_no, rest[pos:pos+20]))
            toks.append(t); pos = t.end()
            while pos < len(rest) and rest[pos].isspace(): pos += 1
        code.append((opc, lineno, toks, ln_no))
    LN = {}
    for off, nm in labels: LN.setdefault(nm, off)
    for k, (opc, lineno, toks, ln_no) in enumerate(code): pass
    def varid(name, ident):
        if ident is not None: return ident
        full = 'gel::' + name
        if full not in vindex:
            vindex[full] = len(vars_); vars_.append((full, tail_default()))
        return NBUILTIN + vindex[full]
    kwd = []
    for opc, lineno, toks, ln_no in code:
        kwd += [lineno, opc, len(toks)]
        for t in toks:
            if t.group('str') is not None:
                s = unq(t.group('str')); ext = t.group('ext')
                if t.group('q'):
                    w1, w2, w3, w4 = [int(x, 16) for x in ext[1:].split(':')]
                    kwd += [string(s), w1, w2, w3, w4]; continue
                if ext is None: kwd += [string(s), MASK, 0, 0, 0]
                elif ext[0] == '#': v = int(ext[1:], 16); kwd += [string(s), MASK, v, f2u(v), v]
                else: a, b, c = [int(x, 16) for x in ext[1:-1].split(',')]; kwd += [string(s), MASK, a, b, c]
                continue
            tok = t.group('tok')
            if tok == '?': raise ValueError('line %d: bad raw operand' % ln_no)
            if tok[0] == '?':
                mm = re.fullmatch(r'\?("(?:[^"\\]|\\.)*"):([0-9a-f]+):([0-9a-f]+):([0-9a-f]+):([0-9a-f]+)', tok)
                if not mm: raise ValueError('line %d: bad raw operand %r' % (ln_no, tok))
                kwd += [string(unq(mm.group(1)))] + [int(mm.group(x), 16) for x in (2, 3, 4, 5)]; continue
            if tok[0] == '!': kwd += [string(tok[1:]), 0xFFFFFFF1, MASK, 0xBF800000, 0]; continue
            if tok[0] == '@':
                nm = tok[1:]
                if nm not in LN: raise ValueError('line %d: unknown label %r' % (ln_no, nm))
                kwd += [string(nm), 0xFFFFFFFC, LN[nm], f2u(LN[nm]), 0]; continue
            if tok[0] == '$':
                mm = re.fullmatch(r'\$([^#/\s]+)(?:#([0-9a-f]+))?(?:/([0-9a-f]+))?', tok)
                if not mm: raise ValueError('line %d: bad variable %r' % (ln_no, tok))
                vid = varid(mm.group(1), int(mm.group(2), 16) if mm.group(2) else None)
                kwd += [string(mm.group(1)), vid, int(mm.group(3), 16) if mm.group(3) else 0, f2u(vid), 0]; continue
            if NUM.fullmatch(tok): kwd += [string(tok)] + derive(tok); continue
            raise ValueError('line %d: cannot understand operand %r' % (ln_no, tok))
    labe = b''.join(struct.pack('<II', o, len(n) + 1) + n.encode('latin1') + b'\0' for o, n in labels)
    varb = b''.join(struct.pack('<I', len(nm) + 1) + nm.encode('latin1') + b'\0' + tl for nm, tl in vars_)
    return kwd, labe, varb, bytes(tabs) + b'\0' * ((-len(tabs)) % 4), len(tabs), len(code), len(labels), len(vars_), sc


def assemble(text, base):
    kwd, labe, varb, tab, ntab, ncode, nlab, nvar, sc = build(text, base)
    # variable records: the stock ones store name + NUL inside the length-prefixed block; rebuild from VARB layout
    rep = {b'KYWD': struct.pack('<%dI' % len(kwd), *kwd), b'NKWD': struct.pack('<I', ncode), b'LABE': labe, b'NLAB': struct.pack('<I', nlab),
           b'KYWT': tab, b'NKWT': struct.pack('<I', ntab), b'VARB': varb, b'NVAR': struct.pack('<I', nvar)}
    out = bytearray(base[:8]); delta = 0
    for t, p in sc.chunks:
        if t in rep: delta += len(rep[t]) - len(p); p = rep[t]
        out += t + struct.pack('<I', len(p) + 8) + p
    struct.pack_into('<I', out, 4, struct.unpack_from('<I', base, 4)[0] + delta)
    out += base[sc.end:]
    return bytes(out)


def check(path):
    base = open(path, 'rb').read(); t1 = dump(base)
    b = assemble(t1, base); t2 = dump(b)
    s1, s2 = Script(base), Script(b)
    ok = t1 == t2 and len(s1.ins) == len(s2.ins) and s1.labels == s2.labels and s1.vars == s2.vars
    print('instructions %d  text lines %d  dump(build(dump)) %s  labels %s  vars %s' % (len(s1.ins), t1.count('\n'), 'same' if t1 == t2 else 'DIFFERENT', s1.labels == s2.labels, s1.vars == s2.vars))
    # word-by-word compare ignoring string offsets and the unused fourth word of variable/label operands
    bad = 0
    for (i1, o1, a1), (i2, o2, a2) in zip(s1.ins, s2.ins):
        if (o1, a1, s1.w[i1]) != (o2, a2, s2.w[i2]): bad += 1; continue
        for j in range(a1):
            x = s1.w[i1+3+5*j:i1+8+5*j]; y = s2.w[i2+3+5*j:i2+8+5*j]
            if s1.s(x[0]) != s2.s(y[0]) or x[1:4] != y[1:4]: bad += 1; break
    print('instruction mismatches:', bad)
    return ok and bad == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['dump', 'build', 'check']); ap.add_argument('file'); ap.add_argument('-o'); ap.add_argument('--base')
    a = ap.parse_args()
    if a.cmd == 'dump':
        t = dump(open(a.file, 'rb').read()); open(a.o or a.file + 's', 'w', encoding='latin1').write(t); print('wrote', a.o or a.file + 's')
    elif a.cmd == 'build':
        if not a.base: sys.exit('build needs --base original.gex (the other chunks are copied from it)')
        try: data = assemble(open(a.file, encoding='latin1').read(), open(a.base, 'rb').read())
        except ValueError as e: sys.exit('error: %s' % e)
        open(a.o or a.file.rsplit('.', 1)[0] + '.gex', 'wb').write(data); print('wrote', a.o or a.file.rsplit('.', 1)[0] + '.gex')
    else:
        sys.exit(0 if check(a.file) else 1)

if __name__ == '__main__': main()
