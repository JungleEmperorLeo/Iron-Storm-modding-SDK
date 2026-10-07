import struct,io
from PIL import Image
def dds_wrap(fmt,w,h,mips,payload):
    fourcc={'DXT1':b'DXT1','DXT3':b'DXT3','DXT5':b'DXT5'}[fmt]
    blk=8 if fmt=='DXT1' else 16
    flags=0x1|0x2|0x4|0x1000|0x20000|0x80000
    hdr=b'DDS '+struct.pack('<7I',124,flags,h,w,max(1,(w+3)//4)*max(1,(h+3)//4)*blk,0,mips)
    hdr+=b'\0'*44+struct.pack('<2I4s5I',32,4,fourcc,0,0,0,0,0)+struct.pack('<5I',0x401008,0,0,0,0)
    return hdr+payload
def decode(fmt,w,h,mips,bufr):
    """largest mip -> RGBA PIL image"""
    return Image.open(io.BytesIO(dds_wrap(fmt,w,h,mips,bufr))).convert('RGBA')
def mip_sizes(fmt,w,h,mips):
    blk=8 if fmt=='DXT1' else 16;out=[]
    for i in range(mips):
        ww=max(1,w>>i);hh=max(1,h>>i);out.append(max(1,(ww+3)//4)*max(1,(hh+3)//4)*blk)
    return out

def _c565(r,g,b): return ((r>>3)<<11)|((g>>2)<<5)|(b>>3)
def _from565(c):
    r=(c>>11)&31; g=(c>>5)&63; b=c&31
    return ((r<<3)|(r>>2),(g<<2)|(g>>4),(b<<3)|(b>>2))
def _color_block(px):
    """px: 16 (r,g,b) tuples -> 8-byte DXT1 colour block (bounding-box endpoints, nearest of 4 colours per pixel)"""
    lo=[min(p[k] for p in px) for k in range(3)]; hi=[max(p[k] for p in px) for k in range(3)]
    ins=[(hi[k]-lo[k])>>4 for k in range(3)]
    c0=_c565(*[hi[k]-ins[k] for k in range(3)]); c1=_c565(*[lo[k]+ins[k] for k in range(3)])
    if c0==c1: return struct.pack('<HHI',c0,c1,0)
    if c0<c1: c0,c1=c1,c0
    a=_from565(c0); b=_from565(c1)
    pal=[a,b,tuple((2*a[k]+b[k])//3 for k in range(3)),tuple((a[k]+2*b[k])//3 for k in range(3))]
    bits=0
    for n,p in enumerate(px):
        best=0;bd=1<<30
        for q,c in enumerate(pal):
            d=(p[0]-c[0])**2+(p[1]-c[1])**2+(p[2]-c[2])**2
            if d<bd: bd=d;best=q
        bits|=best<<(2*n)
    return struct.pack('<HHI',c0,c1,bits)
def _alpha_block(al):
    a0=max(al);a1=min(al)
    if a0==a1: return struct.pack('<BB',a0,a1)+b'\0'*6
    pal=[a0,a1]+[((7-k)*a0+k*a1)//7 for k in range(1,7)]
    bits=0
    for n,v in enumerate(al):
        best=0;bd=1<<30
        for q,c in enumerate(pal):
            d=abs(v-c)
            if d<bd: bd=d;best=q
        bits|=best<<(3*n)
    return struct.pack('<BB',a0,a1)+bits.to_bytes(6,'little')
def _encode_py(im,alpha):
    """pure-Python DXT1/DXT5 encoder, used when this Pillow version cannot write DXT files itself"""
    im=im.convert('RGBA');w,h=im.size;raw=im.tobytes();out=[]
    for by in range(0,h,4):
        for bx in range(0,w,4):
            px=[];al=[]
            for y in range(4):
                o=((by+y)*w+bx)*4
                for x in range(4):
                    r,g,b,a=raw[o+4*x:o+4*x+4];px.append((r,g,b));al.append(a)
            out.append((_alpha_block(al) if alpha else b'')+_color_block(px))
    return b''.join(out)
_warned=[]
def _level(im,fmt):
    blk=8 if fmt=='DXT1' else 16
    n=max(1,(im.size[0]+3)//4)*max(1,(im.size[1]+3)//4)*blk
    try:
        import io as _io
        buf=_io.BytesIO();im.save(buf,format='DDS',pixel_format=fmt);data=buf.getvalue()
        # a Pillow that cannot write DXT silently saves uncompressed pixels: only trust a DXT header (fourcc at byte 84) of the right size
        if data[84:88]==fmt.encode() and len(data) in (128+n,148+n): return data[-n:]
    except Exception: pass
    if not _warned: _warned.append(1);print('NOTE: this Pillow version cannot write %s files; using the built-in encoder (slower)'%fmt)
    return _encode_py(im,fmt=='DXT5')
def _dxt1_level(im): return _level(im,'DXT1')
def encode_dxt1(im):
    """PIL image (power-of-two, >=4px) -> (w,h,mips,bufr): DXT1, mip chain down to 4x4 (matches stock files)."""
    im=im.convert('RGBA');w,h=im.size
    assert w&(w-1)==0 and h&(h-1)==0 and w>=4 and h>=4,'texture size must be a power of two, at least 4x4'
    out=[];lv=im;mips=0
    while True:
        out.append(_dxt1_level(lv));mips+=1
        nw,nh=max(1,lv.size[0]//2),max(1,lv.size[1]//2)
        if lv.size[0]<=4 or lv.size[1]<=4:break
        lv=im.resize((max(4,w>>mips),max(4,h>>mips)),Image.LANCZOS)
    return w,h,mips,b''.join(out)

def _dxt5_level(im): return _level(im,'DXT5')
def encode_dxt5(im):
    """like encode_dxt1 but DXT5 (keeps the alpha channel)"""
    im=im.convert('RGBA');w,h=im.size
    assert w&(w-1)==0 and h&(h-1)==0 and w>=4 and h>=4,'texture size must be a power of two, at least 4x4'
    out=[];lv=im;mips=0
    while True:
        out.append(_dxt5_level(lv));mips+=1
        if lv.size[0]<=4 or lv.size[1]<=4:break
        lv=im.resize((max(4,w>>mips),max(4,h>>mips)),Image.LANCZOS)
    return w,h,mips,b''.join(out)
