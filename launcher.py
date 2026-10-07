"""Iron Storm mod launcher.

Lists the mods in <Iron Storm>\\Mods (folders or .zip files, see ismap\\modpack.py) with their screenshot and
description. Play installs the mod's levels and first-person arms, starts the game straight into its first level,
and when the game closes puts the stock campaign levels and the normal arms back.

Run:  launcher.bat   (or: python launcher.py, or python launcher.py MODNAME to play without the window)
Make a mod: TrenchBroom profiles "Package mod: first level / level N", or
    python map2is.py MAP --name test --package mymod --title "My mod" --description "..."
then add preview.png next to mod.json in Mods\\mymod, and press "Make zip" in the launcher to get a shareable Mods\\mymod.zip.
"""
import os, sys, io, threading, subprocess, shutil
if getattr(sys, 'frozen', False):        # ISModLauncher.exe (PyInstaller): sits in the Iron Storm folder
    GAME = os.path.dirname(sys.executable); HERE = getattr(sys, '_MEIPASS', GAME)
else:                                    # python launcher.py from modtools
    HERE = os.path.dirname(os.path.abspath(__file__)); GAME = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ismap import modpack, gamepatch

# Which game folder to work on: the folder of Game.exe. Default: next to the launcher / above modtools. "Change game..." in the window
# lets you pick another Game.exe; the choice is remembered in ismod_game.txt and passed to the tools (map2is, build_mod...) as ISMOD_GAME.
BASE = GAME
CFG = os.path.join(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else HERE, 'ismod_game.txt')
def game_ok(p): return bool(p) and os.path.isfile(os.path.join(p, 'Game.exe'))
def set_game(p, save=True):
    global GAME
    GAME = os.path.normpath(p); os.environ['ISMOD_GAME'] = GAME
    if save:
        try: open(CFG, 'w').write(GAME + '\n')
        except OSError: pass
def load_game():
    try: p = open(CFG).read().strip()
    except OSError: p = ''
    set_game(p if game_ok(p) else GAME, save=False)
load_game()

def loader_dll():
    for p in (os.path.join(GAME, 'modtools', 'sdk', 'bin', 'ISModLoader.dll'),      # the working copy first: DLL updates need no launcher rebuild
              os.path.join(HERE, 'ISModLoader.dll'), os.path.join(HERE, 'sdk', 'bin', 'ISModLoader.dll')):
        if os.path.exists(p): return p
    return None

def setup_plugins(src=None):
    """Put ISModLoader.dll and the mod's plugin DLLs next to the game for this run. Returns the files to delete afterwards."""
    made = []; ld = loader_dll()
    if not ld: return made
    tgt = os.path.join(GAME, 'ISModLoader.dll'); shutil.copyfile(ld, tgt)       # left in place: IronStormConsole.exe needs them when run on its own (an unpatched Game.exe ignores them)
    core = os.path.join(os.path.dirname(ld), 'ISModLoader_core.dll')     # the front DLL (loose files) loads the core loader
    if os.path.exists(core):
        tgt = os.path.join(GAME, 'ISModLoader_core.dll'); shutil.copyfile(core, tgt)
    pdir = os.path.join(GAME, 'ismod_plugins'); lines = []
    if src is not None:
        for fn in src.listdir('plugins'):
            if fn.lower().endswith('.dll'):
                os.makedirs(pdir, exist_ok=True)
                p = os.path.join(pdir, fn); open(p, 'wb').write(src.read('plugins/' + fn)); lines.append(p)
    lst = os.path.join(GAME, 'ismod_plugins.txt'); open(lst, 'w').write('\n'.join(lines) + '\n'); made += [lst, pdir]
    return made

def cleanup(made):
    for p in made:
        try:
            if os.path.isdir(p): shutil.rmtree(p)
            elif os.path.exists(p): os.remove(p)
        except OSError: pass

def play(path, status):
    try:
        status('Installing...')
        import json
        info = modpack.Source(path).info()
        exe, temp = gamepatch.patched_exe(GAME, info.get('weapons'))   # stock Game.exe untouched: a patched copy exists only while a mod runs
        slots = modpack.install(GAME, path)
        made = setup_plugins(modpack.Source(path)) + modpack.install_loose(GAME, path)
        if 'test' in slots: open(os.path.join(GAME, 'solo.flag'), 'w').close()   # start the first campaign level directly
        else: status('Multiplayer maps installed: pick them in the game menu')
        status('Playing (close the game to come back here)')
        subprocess.Popen([exe], cwd=GAME).wait()
        status('Restoring the stock campaign...')
        modpack.restore(GAME, slots)
        cleanup(made)
        if temp:
            try: os.remove(exe)
            except OSError: pass
        status('Ready')
    except Exception as e:
        status('Error: %s' % e)

TOOLS = os.path.join(BASE, 'modtools') if getattr(sys, 'frozen', False) else HERE      # where map2is.py, build_mod.py, gexpad.py live

def python_exe():
    if not getattr(sys, 'frozen', False): return sys.executable
    return shutil.which('python') or shutil.which('py') or 'python'

def find_maps():
    root = os.path.join(TOOLS, 'trenchbroom', 'maps'); out = []
    for d, _, fs in os.walk(root):
        for f in fs:
            if f.lower().endswith('.map'): out.append(os.path.relpath(os.path.join(d, f), root))
    return sorted(out, key=str.lower)

def build_tools(root, nb, refresh_mods):
    """The 'Maps and tools' tab: compile and play maps, build mods, open the script editor, without any .bat files."""
    import tkinter as tk, re
    from tkinter import ttk, filedialog, simpledialog, messagebox
    tab = ttk.Frame(nb); nb.add(tab, text='  Maps and tools  ')
    left = ttk.Frame(tab); left.pack(side='left', fill='y', padx=(10, 5), pady=10)
    ttk.Label(left, text='Maps (modtools\\trenchbroom\\maps)').pack(anchor='w')
    lb = tk.Listbox(left, width=34, exportselection=False); lb.pack(fill='y', expand=True)
    extra = []
    def reload():
        lb.delete(0, 'end')
        for m in find_maps(): lb.insert('end', m)
        for p in extra: lb.insert('end', p)
    def browse():
        p = filedialog.askopenfilename(filetypes=[('TrenchBroom map', '*.map')])
        if p: extra.append(p); reload(); lb.selection_clear(0, 'end'); lb.selection_set('end')
    ttk.Button(left, text='Browse for a map...', command=browse).pack(fill='x', pady=(6, 0))
    ttk.Button(left, text='Refresh list', command=reload).pack(fill='x', pady=(4, 0))
    right = ttk.Frame(tab); right.pack(side='left', fill='both', expand=True, padx=(5, 10), pady=10)
    btns = ttk.Frame(right); btns.pack(side='top', fill='x')
    log = tk.Text(right, height=12, wrap='word', font=('Consolas', 9), state='disabled'); log.pack(side='bottom', fill='both', expand=True, pady=(8, 0))
    def put(t):
        def w():
            log.config(state='normal'); log.insert('end', t if t.endswith('\n') else t + '\n'); log.see('end'); log.config(state='disabled')
        root.after(0, w)
    busy = []
    def mapfile():
        sel = lb.curselection()
        if not sel: put('Pick a map in the list first.'); return None
        m = lb.get(sel[0])
        return m if os.path.isabs(m) else os.path.join(TOOLS, 'trenchbroom', 'maps', m)
    def run(cmd, then=None):
        if busy: put('Wait for the current job to finish.'); return
        busy.append(1)
        def job():
            try:
                put('> ' + ' '.join(os.path.basename(c) if os.path.isabs(c) else c for c in cmd))
                p = subprocess.Popen(cmd, cwd=TOOLS, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace',
                                     creationflags=0x08000000 if os.name == 'nt' else 0)
                for line in p.stdout: put(line.rstrip())
                ok = p.wait() == 0
                put('Done.' if ok else 'FAILED (see the messages above).')
                if ok and then: then()
            except Exception as e: put('Error: %s' % e)
            finally: busy.clear(); root.after(0, refresh_mods)
        threading.Thread(target=job, daemon=True).start()
    py = python_exe()
    def compile_to(name, then=None):
        m = mapfile()
        if m: run([py, '-u', os.path.join(TOOLS, 'map2is.py'), m, '--name', name, '--install'], then)
    def play_solo(): threading.Thread(target=lambda: (put('Playing (close the game to come back)...'), play_test(), put('Game closed.')), daemon=True).start()
    def play_mp(name):
        subprocess.Popen([os.path.join(GAME, 'Game.exe'), '-game', 'dm', '-map', name], cwd=GAME)
    def ask_mod(m):
        """Ask for the mod's name (folder name in Mods); suggests the map's folder unless that is the top maps folder."""
        d = os.path.basename(os.path.dirname(m)); guess = '' if d.lower() == 'maps' else d
        name = simpledialog.askstring('Mod name', 'Name of the mod to put this map in\n(the folder Mods\\<name>; an existing mod gets the map added or replaced):', initialvalue=guess, parent=root)
        if not name: return None
        name = re.sub(r'[^\w\- ]', '', name.strip()).replace(' ', '_')
        if not name: messagebox.showerror('Mod name', 'Use letters, digits, - or _ in the name.', parent=root); return None
        return name
    def package():
        m = mapfile()
        if not m: return
        mod = ask_mod(m)
        if mod: run([py, '-u', os.path.join(TOOLS, 'map2is.py'), m, '--name', 'test', '--package', mod])
    def build_mod():
        m = mapfile()
        if not m: return
        if os.path.exists(os.path.join(os.path.dirname(m), 'mod.json')): run([py, '-u', os.path.join(TOOLS, 'build_mod.py'), os.path.dirname(m)])
        else: package()          # no mod.json next to the map: same as packaging this one map (asks for the mod name)
    def row(title, items):
        f = ttk.LabelFrame(btns, text=title); f.pack(fill='x', pady=(0, 6))
        for text, cmd in items: ttk.Button(f, text=text, command=cmd).pack(side='left', padx=4, pady=4)
    row('Single player (selected map)', [('Compile and play', lambda: compile_to('test', play_solo)), ('Compile only', lambda: compile_to('test')), ('Play what is installed', play_solo)])
    row('Multiplayer (selected map)', [('Compile and play as isdm5', lambda: compile_to('isdm5', lambda: play_mp('isdm5'))), ('Compile and play as isdm6', lambda: compile_to('isdm6', lambda: play_mp('isdm6')))])
    row('Mods', [('Package this map into a mod', package), ('Build the mod in the map\'s folder (mod.json)', build_mod)])
    def opener(path): return lambda: (os.makedirs(path, exist_ok=True), os.startfile(path)) if hasattr(os, 'startfile') else put(path)
    def editor():
        script = os.path.join(TOOLS, 'gexpad.py')
        if os.path.exists(script): subprocess.Popen([py, script], cwd=TOOLS, creationflags=0x08000000 if os.name == 'nt' else 0)
        else: put('gexpad.py not found in %s' % TOOLS)
    row('Tools', [('Edit a level script (gexpad)', editor), ('Open maps folder', opener(os.path.join(TOOLS, 'trenchbroom', 'maps'))), ('Open documentation', opener(os.path.join(TOOLS, 'docs')))])
    put('Compile and play builds the selected map into the campaign Test slot and starts the game. The same buttons replace the old .bat files.')
    reload()

def main():
    import tkinter as tk
    from tkinter import ttk
    try:    # own taskbar entry and icon (otherwise Windows groups the window under python.exe)
        import ctypes; ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('IronStorm.ISModLauncher')
    except Exception: pass
    root = tk.Tk(); root.title('ISModLauncher'); root.geometry('820x560'); root.minsize(560, 380)
    try: root.iconbitmap(default=os.path.join(HERE, 'launcher.ico'))     # title bar + taskbar
    except Exception: pass
    from tkinter import filedialog, messagebox
    def pick_game(first=False):
        while True:
            p = filedialog.askopenfilename(title='Select Game.exe in your Iron Storm folder', filetypes=[('Game.exe', 'Game.exe'), ('Programs', '*.exe')],
                                           initialdir=GAME if os.path.isdir(GAME) else None)
            if not p: return False
            if os.path.basename(p).lower() != 'game.exe' and not game_ok(os.path.dirname(p)):
                messagebox.showwarning('ISModLauncher', 'That folder has no Game.exe. Pick Game.exe in the Iron Storm folder.'); continue
            set_game(os.path.dirname(p)); return True
    if not game_ok(GAME) and not pick_game(True): root.destroy(); return
    mods = []
    gbar = ttk.Frame(root); gbar.pack(side='top', fill='x', padx=10, pady=(8, 0))
    gvar = tk.StringVar(value='Game: ' + GAME)
    ttk.Label(gbar, textvariable=gvar).pack(side='left')
    changer = []
    ttk.Button(gbar, text='Change game...', command=lambda: changer and changer[0]()).pack(side='right')
    nb = ttk.Notebook(root); nb.pack(fill='both', expand=True)
    tab_mods = ttk.Frame(nb); nb.add(tab_mods, text='  Mods  ')
    left = ttk.Frame(tab_mods); left.pack(side='left', fill='y', padx=(10, 5), pady=10)
    ttk.Label(left, text='Mods').pack(anchor='w')
    lb = tk.Listbox(left, width=32, exportselection=False); lb.pack(fill='y', expand=True)
    right = ttk.Frame(tab_mods); right.pack(side='left', fill='both', expand=True, padx=(5, 10), pady=10)
    msg = tk.StringVar(value='Ready')
    ttk.Label(right, textvariable=msg).pack(side='bottom', anchor='w', pady=(6, 0))
    bar = ttk.Frame(right); bar.pack(side='bottom', fill='x', pady=(6, 0))
    pic = ttk.Label(right); pic.pack(side='top', anchor='n')
    title = ttk.Label(right, font=('Segoe UI', 14, 'bold')); title.pack(side='top', anchor='w', pady=(8, 0))
    meta = ttk.Label(right, foreground='#666'); meta.pack(side='top', anchor='w')
    desc = tk.Text(right, height=4, wrap='word', relief='flat', font=('Segoe UI', 10), background=root.cget('background'))
    desc.pack(side='top', fill='both', expand=True, pady=6)
    img_ref = {}

    def load_image(name, data):
        try:
            from PIL import Image, ImageTk
            im = Image.open(io.BytesIO(data)); im.thumbnail((480, 240)); return ImageTk.PhotoImage(im)
        except ImportError:
            if not name.endswith(('.png', '.gif')): return None
            im = tk.PhotoImage(data=data)
            f = max(1, -(-im.width() // 520), -(-im.height() // 260))
            return im.subsample(f, f) if f > 1 else im
        except Exception:
            return None

    def show(_=None):
        sel = lb.curselection()
        if not sel: return
        m = mods[sel[0]]
        title.config(text=m.get('title', m['id']))
        lv = sorted(m.get('levels', {}), key=lambda s: (s != 'test', len(s), s))
        bits = ['%d level%s' % (len(lv), '' if len(lv) == 1 else 's')] if lv else []
        mpn = list(m.get('multiplayer', {}))
        if mpn: bits.append('multiplayer: ' + ', '.join(mpn))
        if m.get('author'): bits.insert(0, 'by ' + m['author'])
        bits.append('zip' if m['path'].lower().endswith('.zip') else 'folder')
        meta.config(text='  ·  '.join(bits))
        desc.config(state='normal'); desc.delete('1.0', 'end'); desc.insert('1.0', (m.get('description') or '(no description)') + ''.join('\n\nWarning: ' + w for w in m.get('warnings', []))); desc.config(state='disabled')
        img = None
        try:
            n, d = modpack.Source(m['path']).preview()
            if d: img = load_image(n, d)
        except Exception: pass
        img_ref['i'] = img
        pic.config(image=img if img else '', text='' if img else '(no preview.png)')
        zipbtn.state(['!disabled'] if os.path.isdir(m['path']) else ['disabled'])
        playbtn.state(['disabled'] if m.get('broken') else ['!disabled'])

    def refresh():
        nonlocal mods
        mods = modpack.list_mods(GAME); lb.delete(0, 'end')
        for m in mods: lb.insert('end', m.get('title', m['id']))
        if mods: lb.selection_set(0); show()
        else: msg.set('No mods in %s yet.' % modpack.mods_dir(GAME))

    def status(t): root.after(0, msg.set, t)
    def go():
        sel = lb.curselection()
        if not sel: return
        playbtn.state(['disabled'])
        def run():
            play(mods[sel[0]]['path'], status); root.after(0, lambda: playbtn.state(['!disabled']))
        threading.Thread(target=run, daemon=True).start()
    def zipit():
        sel = lb.curselection()
        if not sel: return
        out = modpack.make_zip(GAME, mods[sel[0]]['id']); msg.set('Made ' + out)
    playbtn = ttk.Button(bar, text='Play', command=go); playbtn.pack(side='left')
    zipbtn = ttk.Button(bar, text='Make zip', command=zipit); zipbtn.pack(side='left', padx=6)
    ttk.Button(bar, text='Open Mods folder', command=lambda: (os.makedirs(modpack.mods_dir(GAME), exist_ok=True), os.startfile(modpack.mods_dir(GAME)))).pack(side='left')
    ttk.Button(bar, text='Refresh', command=refresh).pack(side='right')
    lb.bind('<<ListboxSelect>>', show)
    build_tools(root, nb, refresh)
    def change_game():
        if pick_game(): gvar.set('Game: ' + GAME); refresh(); msg.set('Now using ' + GAME)
    changer.append(change_game)
    refresh(); root.mainloop()

class TestPlugins:
    """TrenchBroom test runs use the plugins the last export left in modtools\\build\\test_plugins."""
    d = os.path.join(HERE, 'build', 'test_plugins')
    def listdir(self, rel): return os.listdir(self.d) if os.path.isdir(self.d) else []
    def read(self, rel): return open(os.path.join(self.d, rel.split('/', 1)[1]), 'rb').read()

def play_test():
    """TrenchBroom 'Play campaign Test slot': run what is already installed in the Test slot, with a temporary patched exe."""
    exe, temp = gamepatch.patched_exe(GAME)
    try: os.remove(os.path.join(GAME, 'ismod_paths.txt'))   # play the Test slot as installed by the compiler
    except OSError: pass
    open(os.path.join(GAME, 'solo.flag'), 'w').close()
    made = setup_plugins(TestPlugins())
    try: subprocess.Popen([exe], cwd=GAME).wait()
    finally:
        cleanup(made)
        if temp:
            try: os.remove(exe)
            except OSError: pass

if __name__ == '__main__':
    if sys.argv[1:] == ['--test']:
        play_test()
    elif len(sys.argv) > 1:
        m = next((x for x in modpack.list_mods(GAME) if x['id'] == sys.argv[1]), None)
        if not m: sys.exit('no mod %r in %s' % (sys.argv[1], modpack.mods_dir(GAME)))
        play(m['path'], print)
    else:
        main()
