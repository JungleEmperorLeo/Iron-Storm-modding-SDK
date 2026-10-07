#!/usr/bin/env python3
"""gexpad - a Notepad-style editor for compiled Iron Storm level scripts (.gex).

Run:  python gexpad.py [level.gex]      (or double-click it)
File > Open a .gex, edit the text, File > Save (Ctrl+S) writes the .gex back (a .bak copy of the original is kept the first time).
Ctrl+F finds, F3 finds next, Ctrl+G goes to a line, Ctrl+L lists the functions. See GEXEDIT.md for what the lines mean."""
import os, sys, re, shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gexedit

class Pad:
    def __init__(self, root, path=None):
        self.root = root; self.path = None; self.base = None; self.last = ''
        root.geometry('1100x720')
        bar = tk.Menu(root); root.config(menu=bar)
        fm = tk.Menu(bar, tearoff=0); bar.add_cascade(label='File', menu=fm)
        fm.add_command(label='Open...', accelerator='Ctrl+O', command=self.open)
        fm.add_command(label='Save', accelerator='Ctrl+S', command=self.save)
        fm.add_command(label='Save As...', command=lambda: self.save(True))
        fm.add_separator(); fm.add_command(label='Exit', command=root.destroy)
        em = tk.Menu(bar, tearoff=0); bar.add_cascade(label='Edit', menu=em)
        em.add_command(label='Undo', accelerator='Ctrl+Z', command=lambda: self.t.edit_undo())
        em.add_command(label='Find...', accelerator='Ctrl+F', command=self.find)
        em.add_command(label='Find next', accelerator='F3', command=self.next)
        em.add_command(label='Go to line...', accelerator='Ctrl+G', command=self.goto)
        em.add_command(label='Functions...', accelerator='Ctrl+L', command=self.funcs)
        self.t = tk.Text(root, wrap='none', undo=True, font=('Consolas', 10), bg='white', fg='black')
        ys = tk.Scrollbar(root, command=self.t.yview); xs = tk.Scrollbar(root, command=self.t.xview, orient='horizontal')
        self.t.config(yscrollcommand=ys.set, xscrollcommand=xs.set)
        xs.pack(side='bottom', fill='x'); ys.pack(side='right', fill='y'); self.t.pack(fill='both', expand=True)
        self.status = tk.Label(root, anchor='w', text='File > Open a .gex'); self.status.pack(side='bottom', fill='x')
        self.t.tag_config('label', foreground='#0050c0', font=('Consolas', 10, 'bold')); self.t.tag_config('comment', foreground='#808080')
        self.t.tag_config('hit', background='#ffe680')
        for k, f in (('<Control-o>', self.open), ('<Control-s>', self.save), ('<Control-f>', self.find), ('<F3>', self.next), ('<Control-g>', self.goto), ('<Control-l>', self.funcs)):
            root.bind(k, lambda e, f=f: (f(), 'break')[1])
        if path: self.load(path)

    def title(self): self.root.title('gexpad - %s' % (self.path or ''))
    def open(self):
        p = filedialog.askopenfilename(filetypes=[('Level script', '*.gex'), ('All files', '*.*')])
        if p: self.load(p)
    def load(self, p):
        try: self.base = open(p, 'rb').read(); text = gexedit.dump(self.base)
        except Exception as e: messagebox.showerror('gexpad', 'Cannot read %s\n%s' % (p, e)); return
        self.path = p; self.t.delete('1.0', 'end'); self.t.insert('1.0', text); self.t.edit_reset(); self.t.edit_modified(False)
        self.colour(); self.title(); self.status.config(text='%d lines' % text.count('\n'))
    def colour(self):
        for tg in ('label', 'comment'): self.t.tag_remove(tg, '1.0', 'end')
        n = int(self.t.index('end-1c').split('.')[0])
        for i in range(1, n + 1):
            s = self.t.get('%d.0' % i, '%d.end' % i)
            if s.startswith(':'): self.t.tag_add('label', '%d.0' % i, '%d.end' % i)
            elif s.startswith('#') or s.startswith('.'): self.t.tag_add('comment', '%d.0' % i, '%d.end' % i)
    def save(self, as_=False):
        if self.base is None: return
        text = self.t.get('1.0', 'end')
        try: data = gexedit.assemble(text, self.base)
        except Exception as e:
            m = re.search(r'line (\d+)', str(e))
            if m: self.t.see('%s.0' % m.group(1)); self.t.tag_add('hit', '%s.0' % m.group(1), '%s.end' % m.group(1))
            messagebox.showerror('gexpad', 'Cannot save:\n%s' % e); return
        p = self.path
        if as_ or not p:
            p = filedialog.asksaveasfilename(defaultextension='.gex', filetypes=[('Level script', '*.gex')])
            if not p: return
        if os.path.exists(p) and not os.path.exists(p + '.bak'): shutil.copyfile(p, p + '.bak')
        open(p, 'wb').write(data); self.path = p; self.title(); self.t.edit_modified(False)
        self.status.config(text='saved %s (%d bytes)' % (p, len(data)))
    def find(self):
        s = simpledialog.askstring('Find', 'Find text:', initialvalue=self.last, parent=self.root)
        if s: self.last = s; self.t.mark_set('insert', '1.0'); self.next()
    def next(self):
        if not self.last: return self.find()
        self.t.tag_remove('hit', '1.0', 'end')
        i = self.t.search(self.last, 'insert+1c', 'end', nocase=True)
        if not i: i = self.t.search(self.last, '1.0', 'end', nocase=True)
        if not i: self.status.config(text='not found: ' + self.last); return
        e = '%s+%dc' % (i, len(self.last)); self.t.tag_add('hit', i, e); self.t.mark_set('insert', i); self.t.see(i); self.status.config(text='found at line ' + i.split('.')[0])
    def goto(self):
        n = simpledialog.askinteger('Go to line', 'Line number:', parent=self.root)
        if n: self.t.mark_set('insert', '%d.0' % n); self.t.see('%d.0' % n)
    def funcs(self):
        n = int(self.t.index('end-1c').split('.')[0]); names = []
        for i in range(1, n + 1):
            s = self.t.get('%d.0' % i, '%d.end' % i)
            if s.startswith(':') and not s.endswith('@end') and not s.startswith(':label@'): names.append((s[1:], i))
        w = tk.Toplevel(self.root); w.title('Functions'); w.geometry('360x500')
        e = tk.Entry(w); e.pack(fill='x'); lb = tk.Listbox(w); lb.pack(fill='both', expand=True)
        def fill(*_):
            lb.delete(0, 'end')
            for nm, i in names:
                if e.get().lower() in nm.lower(): lb.insert('end', '%s  (%d)' % (nm, i))
        def go(*_):
            if lb.curselection():
                i = int(lb.get(lb.curselection()[0]).rsplit('(', 1)[1][:-1]); self.t.mark_set('insert', '%d.0' % i); self.t.see('%d.0' % i); self.t.focus_set()
        e.bind('<KeyRelease>', fill); lb.bind('<Double-Button-1>', go); lb.bind('<Return>', go); fill(); e.focus_set()

if __name__ == '__main__':
    r = tk.Tk()
    ico = os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))), 'launcher.ico')
    try: r.iconbitmap(ico)
    except Exception: pass
    Pad(r, sys.argv[1] if len(sys.argv) > 1 else None); r.mainloop()
