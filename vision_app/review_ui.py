"""Native incident browser. Heavy reads/exports dispatched through Window.task."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import cv2
from PIL import Image, ImageTk

from .interactions import MAJOR_EVENTS
from .review import DECISIONS


def fit_image(image, max_width=780, max_height=470):
    h, w = image.shape[:2]
    ratio = min(1, max_width/w, max_height/h)
    image = cv2.resize(image, (max(1, int(w*ratio)), max(1, int(h*ratio))), interpolation=cv2.INTER_AREA)
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


class ReviewWindow:
    def __init__(self, owner):
        self.owner = owner; self.controller = owner.controller
        self.root = tk.Toplevel(owner.root); self.root.title('Registros e revisão — CamCraft')
        self.root.geometry('1040x620'); self.root.minsize(800, 500)
        self.rows = {}; self.ceiling = None; self.before = None; self.next_before = None; self.stack = []
        self.camera = tk.StringVar(value='Todas'); self.code = tk.StringVar(value='Todos')
        self.decision = tk.StringVar(value='Todas'); self.search = tk.StringVar()
        self.start_date = tk.StringVar(); self.end_date = tk.StringVar(); self.important = tk.BooleanVar(value=True)
        self.info = tk.StringVar(value='Carregando...')
        a = ttk.Frame(self.root, padding=8); a.pack(fill='x')
        for text, variable, values, width in [('Câmera', self.camera, ['Todas']+[c.id for c in self.controller.configs.all()],16),
                                              ('Evento', self.code, ['Todos']+sorted(MAJOR_EVENTS),25),
                                              ('Revisão', self.decision, ['Todas','PENDENTE',*DECISIONS],18)]:
            ttk.Label(a, text=text).pack(side='left', padx=(0,4))
            ttk.Combobox(a,textvariable=variable,values=values,state='readonly',width=width).pack(side='left',padx=(0,10))
        b=ttk.Frame(self.root,padding=(8,0,8,8)); b.pack(fill='x')
        ttk.Label(b,text='Busca').pack(side='left'); ttk.Entry(b,textvariable=self.search,width=22).pack(side='left',padx=4)
        for label,var in [('De',self.start_date),('Até',self.end_date)]:
            ttk.Label(b,text=label).pack(side='left');ttk.Entry(b,textvariable=var,width=11).pack(side='left',padx=4)
        ttk.Label(b,text='AAAA-MM-DD · horário local').pack(side='left',padx=5)
        ttk.Checkbutton(b,text='Só ocorrências',variable=self.important).pack(side='left',padx=4)
        ttk.Button(b,text='Buscar',command=self.refresh).pack(side='right')
        table=ttk.Frame(self.root,padding=(8,0)); table.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(table,columns=('time','camera','event','object','decision'),show='headings')
        for name,text,width in [('time','Horário local',150),('camera','Câmera',100),('event','Evento',215),('object','Objeto',175),('decision','Revisão',130)]:
            self.tree.heading(name,text=text); self.tree.column(name,width=width,minwidth=80)
        scroll=ttk.Scrollbar(table,command=self.tree.yview);self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        self.tree.bind('<Double-1>',lambda e:self.details())
        bottom=ttk.Frame(self.root,padding=8);bottom.pack(fill='x')
        for text,fn in [('Mais recentes',self.previous),('Mais antigos',self.next),('Abrir ocorrência',self.details),('Atualizar',self.refresh)]:
            ttk.Button(bottom,text=text,command=fn).pack(side='left',padx=3)
        ttk.Label(self.root,textvariable=self.info,padding=8,wraplength=970).pack(fill='x')
        self.refresh()

    def refresh(self):
        if self.owner.busy:return
        self.before=None;self.ceiling=None;self.stack=[];self.load()

    def filters(self):
        def parse(text, end=False):
            if not text.strip():return None
            d=datetime.strptime(text.strip(),'%Y-%m-%d')
            if end:d+=timedelta(days=1)
            return d.timestamp() - (.000001 if end else 0)
        return dict(camera_id=None if self.camera.get()=='Todas' else self.camera.get(),
                    code=None if self.code.get()=='Todos' else self.code.get(),
                    decision=None if self.decision.get()=='Todas' else self.decision.get(),
                    text=self.search.get().strip(),since=parse(self.start_date.get()),until=parse(self.end_date.get(),True),
                    important_only=self.important.get(),before=self.before,ceiling=self.ceiling,limit=100)

    def load(self):
        if not self.root.winfo_exists() or self.owner.busy:return
        try:filters=self.filters()
        except ValueError:messagebox.showerror('Datas','Use AAAA-MM-DD.',parent=self.root);return
        def loaded(page):
            if not self.root.winfo_exists():return
            self.ceiling=page['ceiling'];self.next_before=page['next_before']
            self.rows={str(r['id']):r for r in page['rows']}; self.tree.delete(*self.tree.get_children())
            for iid,row in self.rows.items():
                p=row['payload']
                self.tree.insert('',tk.END,iid=iid,values=(time.strftime('%d/%m/%Y %H:%M:%S',time.localtime(row['utc'])),row['camera_id'],row['code'],p.get('object_name',p.get('class_name','')),row.get('review_decision') or 'PENDENTE'))
            self.info.set(f"{len(self.rows)} registros nesta página. Navegação fixa até o registro {self.ceiling}; Atualizar inclui novos eventos. Duplo clique abre imagens/revisão.")
        self.owner.task(lambda:self.controller.reviews.page(**filters),loaded)

    def next(self):
        if self.owner.busy or self.next_before is None:return
        self.stack.append(self.before);self.before=self.next_before;self.load()

    def previous(self):
        if self.owner.busy or not self.stack:return
        self.before=self.stack.pop();self.load()

    def details(self):
        selected=self.tree.selection()
        if selected and not self.owner.busy:
            DetailWindow(self.owner,self.rows[selected[0]])


class DetailWindow:
    def __init__(self,owner,row):
        self.owner=owner;self.controller=owner.controller;self.row=row;self.images=[]
        self.root=tk.Toplevel(owner.root);self.root.title('Ocorrência #'+str(row['id'])+' — '+row['code'])
        self.root.geometry('990x740');self.root.minsize(780,580)
        self.info=tk.StringVar(value='Conferindo evidências...');self.note=tk.StringVar();self.operator=tk.StringVar(value='operador local')
        self.eid=row['payload'].get('evidence_id');self.report=None
        ttk.Label(self.root,text=row['code']+' • '+time.strftime('%d/%m/%Y %H:%M:%S',time.localtime(row['utc'])),padding=10).pack(fill='x')
        self.notebook=ttk.Notebook(self.root);self.notebook.pack(fill='both',expand=True,padx=8)
        self.data=tk.Text(self.notebook,wrap='word',height=10);self.notebook.add(self.data,text='Registro e revisões')
        self.data.insert('1.0',json.dumps(row,ensure_ascii=False,indent=2));self.data.configure(state='disabled')
        ttk.Label(self.root,textvariable=self.info,wraplength=950,padding=8).pack(fill='x')
        actions=ttk.Frame(self.root,padding=(8,0));actions.pack(fill='x')
        for text,fn in [('Exportar ocorrência ZIP',self.export),('Preservar evidência',lambda:self.preserve(True)),('Liberar retenção',lambda:self.preserve(False)),('Abrir clipe',self.clip),('Atualizar',self.load)]:
            ttk.Button(actions,text=text,command=fn).pack(side='left',padx=3)
        if row['code'] in MAJOR_EVENTS:
            form=ttk.Frame(self.root,padding=8);form.pack(fill='x')
            ttk.Label(form,text='Operador informado').grid(row=0,column=0,sticky='w')
            ttk.Entry(form,textvariable=self.operator,width=24).grid(row=0,column=1,sticky='w')
            ttk.Label(form,text='Observação').grid(row=1,column=0,sticky='w')
            ttk.Entry(form,textvariable=self.note,width=70).grid(row=1,column=1,columnspan=3,sticky='ew')
            controls=ttk.Frame(form);controls.grid(row=2,column=0,columnspan=4,pady=6)
            for text,value in [('Confirmar observação','CONFIRMADO'),('Falso positivo','FALSO_POSITIVO'),('Inconclusivo','INCONCLUSIVO')]:
                ttk.Button(controls,text=text,command=lambda v=value:self.review(v)).pack(side='left',padx=3)
        self.load()

    def load(self):
        def read():
            reviews=self.controller.reviews.reviews(self.row['id'])
            report=self.controller.evidence_review.inspect(self.eid) if self.eid else {'state':'MISSING','issues':['Sem evidência associada.'],'files':[],'preserved':False}
            images=[]
            if report['state'] in ('VERIFIED','PENDING'):
                names=[f['name'] for f in report['files'] if f['name'].endswith('.jpg')]
                names.sort(key=lambda n:(0 if n.startswith('antes_') else 1 if n=='quadro.jpg' else 2,n))
                for name in names:
                    images.append((name,fit_image(self.controller.evidence_review.read_image(self.eid,name))))
            return report,reviews,images
        def display(result):
            if not self.root.winfo_exists():return
            report,reviews,images=result;self.report=report
            for tab in list(self.notebook.tabs())[1:]:
                widget=self.root.nametowidget(tab)
                self.notebook.forget(tab);widget.destroy()
            self.images.clear()
            self.data.configure(state='normal');self.data.delete('1.0','end')
            self.data.insert('1.0',json.dumps({'registro':self.row,'revisoes':reviews,'verificacao':report},ensure_ascii=False,indent=2));self.data.configure(state='disabled')
            for name,image in images:
                page=ttk.Frame(self.notebook);photo=ImageTk.PhotoImage(image);self.images.append(photo)
                ttk.Label(page,image=photo,anchor='center').pack(fill='both',expand=True)
                label='Antes · '+name[6:24] if name.startswith('antes_') else 'Depois · sem caixas' if name=='quadro.jpg' else 'Depois · anotado'
                self.notebook.add(page,text=label)
            self.info.set('Integridade: '+report['state']+' | '+('PRESERVADA contra retenção' if report.get('preserved') else 'Sujeita à retenção')+' | Hashes locais não são assinatura digital. '+ '; '.join(report.get('issues',[])))
            if images:self.notebook.select(1)
        self.owner.task(read,display)

    def review(self,value):
        note=self.note.get();operator=self.operator.get()
        self.owner.task(lambda:self.controller.review_event(self.row['id'],value,note,operator),
                        lambda _:self.load())

    def preserve(self,enabled):
        if not self.eid:return
        self.owner.task(lambda:self.controller.evidence_review.preserve(self.eid,enabled),
                        lambda _:self.load())

    def export(self):
        if self.owner.busy:return
        missing=not self.report or self.report['state']=='MISSING'
        if missing and not messagebox.askyesno('Sem evidência','Exportar somente o registro e as revisões, indicando a ausência de imagens?',parent=self.root):return
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.zip',initialfile=f"ocorrencia-{self.row['id']}.zip",filetypes=[('ZIP','*.zip')])
        if path:self.owner.task(lambda:self.controller.evidence_review.export_incident(self.row['id'],Path(path),allow_missing=missing),lambda _:self.info.set('Pacote exportado e hashes conferidos.'))

    def clip(self):
        if not self.eid or not self.report or not self.report.get('clip'):
            messagebox.showinfo('Clipe','Clipe não disponível ou ainda pendente.',parent=self.root);return
        # Open a verified local clip with the OS player; no shell command concatenation.
        eid=self.eid
        def check():
            report=self.controller.evidence_review.inspect(eid)
            if report['state']!='VERIFIED' or not report.get('clip'):raise ValueError('Clipe não está íntegro/concluído.')
            # Explicit preservation prevents deletion while the external player opens it.
            self.controller.evidence_review.preserve(eid,True)
            return self.controller.evidence_review.folder(eid)/'clip.avi'
        self.owner.task(check,lambda p:self.owner.open_path(p))
