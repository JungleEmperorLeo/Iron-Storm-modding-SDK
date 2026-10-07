"""Compile plugin sources (.c / .cpp) into a 32-bit Windows DLL with the zig C compiler (pip package 'ziglang')."""
import os, sys, subprocess, glob

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # modtools
INCLUDE = os.path.join(HERE, 'sdk', 'include')

def ensure_zig():
    try:
        import ziglang  # noqa
    except ImportError:
        print('installing the C compiler (pip install ziglang, one time)...', flush=True)
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--quiet', 'ziglang'])

def compile_dir(src, out_dll):
    """All .c/.cpp files in src -> out_dll. Returns out_dll, or None when src has no sources."""
    files = sorted(glob.glob(os.path.join(src, '*.c')) + glob.glob(os.path.join(src, '*.cpp')))
    if not files: return None
    ensure_zig()
    os.makedirs(os.path.dirname(out_dll), exist_ok=True)
    cmd = [sys.executable, '-m', 'ziglang', 'c++' if any(f.endswith('.cpp') for f in files) else 'cc',
           '-target', 'x86-windows-gnu', '-shared', '-O2', '-s', '-I', INCLUDE, '-o', out_dll] + files
    print('compiling plugin %s' % os.path.basename(out_dll), flush=True)
    r = subprocess.call(cmd)
    if r: raise RuntimeError('plugin compile failed: %s' % src)
    stems = [out_dll[:-4]] + [os.path.join(os.path.dirname(out_dll), os.path.splitext(os.path.basename(f))[0]) for f in files]
    for junk in [st + ext for st in stems for ext in ('.lib', '.pdb')]:
        if os.path.exists(junk): os.remove(junk)
    return out_dll

if __name__ == '__main__':
    if len(sys.argv) != 2: sys.exit('usage: python -m ismap.plugins FOLDER')
    d = os.path.abspath(sys.argv[1])
    out = compile_dir(d, os.path.join(d, os.path.basename(d.rstrip('\\/')) + '.dll'))
    print('built', out) if out else sys.exit('no .c/.cpp files in ' + d)
