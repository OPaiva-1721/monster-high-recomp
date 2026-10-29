"""Small Tkinter front end; installation and updates share the CLI engine."""
import argparse
import json
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from installer.install import (ROOT, Cancelled, detect_options, doctor, launch,
                               profile, run_install, update_install)


class Model:
    def __init__(self):
        self.busy = False
        self.ready = False
        self.message = 'Escolha sua cópia do jogo e o destino.'

    def event(self, event):
        self.message = event.get('message', '')
        if event.get('stage') == 'complete' and event.get('status') == 'complete':
            self.ready = True


class Setup:
    def __init__(self, window):
        self.window, self.model = window, Model()
        self.events, self.cancel = queue.Queue(), threading.Event()
        game = profile()
        window.title(game['title'] + ' — instalação experimental')
        window.minsize(780, 620)
        outer = ttk.Frame(window, padding=18)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text=game['title'], font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='Windows/D3D12 • fontes experimentais • use sua própria cópia compatível', wraplength=740).pack(anchor='w', pady=(4, 12))
        self.values, self.buttons = {}, []
        fields = [('source', 'Pasta do jogo (PS3_GAME)', 'dir'), ('dest', 'Destino da instalação', 'dir'),
                  ('elf', 'EBOOT.elf já decifrado (opcional)', 'file'), ('rpcs3', 'RPCS3.exe (se faltar ELF)', 'file'),
                  ('firmware', 'Firmware: pasta dev_flash', 'dir'), ('ffmpeg', 'FFmpeg 8.1: pasta com bin e include', 'dir'),
                  ('vcvars', 'Visual Studio: vcvars64.bat', 'file'), ('compiler', 'Compilador clang-cl.exe', 'file')]
        options = detect_options()
        for key, label, kind in fields:
            row = ttk.Frame(outer); row.pack(fill='x', pady=3)
            ttk.Label(row, text=label, width=39).pack(side='left')
            var = tk.StringVar(value=options.get(key, ''))
            self.values[key] = var
            entry = ttk.Entry(row, textvariable=var); entry.pack(side='left', fill='x', expand=True)
            button = ttk.Button(row, text='Escolher', command=lambda v=var, k=kind: self.browse(v, k))
            button.pack(side='left', padx=(5, 0)); self.buttons += [entry, button]
        ttk.Label(outer, text='Requisitos: Windows x64, Python 3.12+, Git, CMake/Ninja, Visual Studio Build Tools com Clang, FFmpeg compartilhado e firmware próprios. Nada será instalado no sistema automaticamente.', wraplength=740).pack(anchor='w', pady=10)
        actions = ttk.Frame(outer); actions.pack(fill='x')
        for label, action in [('Conferir requisitos', self.requirements), ('Instalar / retomar', lambda: self.start(False)),
                              ('Atualizar instalação', lambda: self.start(True))]:
            button = ttk.Button(actions, text=label, command=action);button.pack(side='left', padx=(0, 6));self.buttons.append(button)
        self.play = ttk.Button(actions, text='Jogar', command=self.play_game, state='disabled');self.play.pack(side='left')
        self.stop = ttk.Button(actions, text='Cancelar', command=self.cancel.set, state='disabled');self.stop.pack(side='right')
        self.status = tk.StringVar(value=self.model.message)
        ttk.Label(outer, textvariable=self.status, wraplength=740).pack(anchor='w', pady=10)
        self.progress = ttk.Progressbar(outer, mode='indeterminate');self.progress.pack(fill='x')
        self.log = tk.Text(outer, height=10, wrap='word', state='disabled');self.log.pack(fill='both', expand=True, pady=(10, 0))
        window.protocol('WM_DELETE_WINDOW', self.close)
        window.after(100, self.pump)

    def browse(self, var, kind):
        result = filedialog.askdirectory() if kind == 'dir' else filedialog.askopenfilename()
        if result:var.set(result)

    def options(self):
        return {key: self.values[key].get().strip() for key in detect_options()}

    def requirements(self):
        issues = doctor(self.options())
        messagebox.showinfo('Requisitos', '\n'.join(issues) if issues else 'Requisitos encontrados. A edição do jogo será conferida ao instalar.')

    def start(self, updating):
        if self.model.busy:return
        source, dest, options = self.values['source'].get(), self.values['dest'].get(), self.options()
        if not dest or (not updating and not source):
            messagebox.showerror('Pastas ausentes', 'Selecione origem e destino. Para atualizar basta o destino.');return
        self.model.busy, self.model.ready = True, False
        self.cancel.clear();self.play.configure(state='disabled');self.stop.configure(state='normal')
        for button in self.buttons:button.configure(state='disabled')
        self.progress.start()
        def work():
            try:
                if updating:update_install(Path(dest), self.events.put, self.cancel)
                else:run_install(Path(source), Path(dest), self.events.put, options=options, cancel=self.cancel)
                self.events.put({'stage': 'complete', 'status': 'complete', 'message': 'Concluído. Use Jogar ou o atalho na pasta.'})
            except Exception as error:
                self.events.put({'stage': 'error', 'status': 'error', 'message': str(error)})
            finally:self.events.put({'stage': 'idle'})
        threading.Thread(target=work, daemon=True).start()

    def pump(self):
        while not self.events.empty():
            event = self.events.get();self.model.event(event)
            if event.get('stage') == 'idle':
                self.model.busy = False;self.progress.stop();self.stop.configure(state='disabled')
                for button in self.buttons:button.configure(state='normal')
                self.play.configure(state='normal' if self.model.ready else 'disabled')
                continue
            self.status.set(self.model.message)
            self.log.configure(state='normal');self.log.insert('end', self.model.message + '\n');self.log.see('end');self.log.configure(state='disabled')
        self.window.after(100, self.pump)

    def play_game(self):
        destination = Path(self.values['dest'].get())
        def run():
            try:launch(destination)
            except Exception as error:self.events.put({'stage': 'error', 'message': str(error)})
        threading.Thread(target=run, daemon=True).start()

    def close(self):
        if self.model.busy:
            self.cancel.set();self.status.set('Cancelando a etapa. Aguarde terminar antes de fechar.');return
        self.window.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--describe', type=Path, help='Write source package identity without opening UI')
    args = parser.parse_args()
    if args.describe:
        args.describe.write_text(json.dumps({'game': profile(), 'root': str(ROOT)}, indent=2), encoding='utf-8');return
    window = tk.Tk();Setup(window);window.mainloop()


if __name__ == '__main__':main()
