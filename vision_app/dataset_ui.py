"""Small native annotation tool: explicit human boxes, scoped negative examples."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import ImageTk

from .classes import NAMES
from .review_ui import fit_image


class DatasetWindow:
    def __init__(self, owner):
        self.owner=owner;self.store=owner.controller.dataset
        self.root=tk.Toplevel(owner.root);self.root.title('Amostras e anotação manual — CamCraft')
        self.root.geometry('1120x760');self.root.minsize(850,620)
        self.row=None;self.frame=None;self.boxes=[];self.bounds=None;self.drag=None;self.photo=None;self.dirty=False
        self.info=tk.StringVar(value='Capture imagens e marque manualmente os objetos; previsões não são rótulos verdadeiros.')
        self.category=tk.StringVar(value=f'{NAMES[0]} [0]');self.scope=tk.StringVar(value='0')
        self.group=tk.StringVar();self.complete=tk.BooleanVar(value=False)
        # Metadata edits/negative confirmation are unsaved changes too.
        for variable in (self.scope,self.group,self.complete):
            variable.trace_add('write',lambda *args:self.mark_dirty())
        actions=ttk.Frame(self.root,padding=8);actions.pack(fill='x')
        for name,fn in [('Capturar quadro atual',self.capture),('Atualizar lista',self.refresh),('Exportar conjunto ZIP',self.export)]:
            ttk.Button(actions,text=name,command=fn).pack(side='left',padx=4)
        content=ttk.Panedwindow(self.root,orient='horizontal');content.pack(fill='both',expand=True,padx=8)
        left=ttk.Frame(content);right=ttk.Frame(content);content.add(left,weight=1);content.add(right,weight=4)
        self.listbox=tk.Listbox(left,width=28,exportselection=False);self.listbox.pack(fill='both',expand=True)
        self.listbox.bind('<<ListboxSelect>>',lambda e:self.select())
        self.canvas=tk.Canvas(right,bg='#111318',highlightthickness=0);self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.draw())
        self.canvas.bind('<ButtonPress-1>',self.down);self.canvas.bind('<B1-Motion>',self.move);self.canvas.bind('<ButtonRelease-1>',self.up)
        form=ttk.Frame(self.root,padding=8);form.pack(fill='x')
        ttk.Label(form,text='Categoria da caixa').grid(row=0,column=0,sticky='w')
        ttk.Combobox(form,textvariable=self.category,values=[f'{name} [{i}]' for i,name in enumerate(NAMES)],width=28,state='readonly').grid(row=0,column=1,sticky='w')
        ttk.Button(form,text='Desfazer caixa',command=self.undo).grid(row=0,column=2,padx=4)
        ttk.Button(form,text='Limpar caixas',command=self.clear).grid(row=0,column=3,padx=4)
        ttk.Label(form,text='Categorias anotadas (IDs)').grid(row=1,column=0,sticky='w')
        ttk.Entry(form,textvariable=self.scope,width=28).grid(row=1,column=1,sticky='w')
        ttk.Label(form,text='0 = pessoa; separe IDs por vírgula. Negativa = nenhuma destas categorias.').grid(row=1,column=2,columnspan=2,sticky='w')
        ttk.Label(form,text='Grupo / gravação').grid(row=2,column=0,sticky='w')
        ttk.Entry(form,textvariable=self.group,width=68).grid(row=2,column=1,columnspan=3,sticky='ew')
        ttk.Checkbutton(form,text='Conferi TODAS as ocorrências das categorias acima; anotação completa (inclusive imagens negativas).',variable=self.complete).grid(row=3,column=0,columnspan=4,sticky='w',pady=6)
        ttk.Button(form,text='Salvar anotação',command=self.save).grid(row=4,column=3,sticky='e')
        ttk.Label(self.root,textvariable=self.info,padding=8,wraplength=1050).pack(fill='x')
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.rows=[];self.refresh()

    def mark_dirty(self):
        if self.row is not None:self.dirty=True

    def refresh(self,select_id=None):
        def show(rows):
            if not self.root.winfo_exists():return
            self.rows=rows;self.listbox.delete(0,'end')
            for row in rows:self.listbox.insert('end',row['state']+' · '+row['id'][-10:]+f" · {len(row.get('objects',[]))} caixas")
            if select_id:
                for i,r in enumerate(rows):
                    if r['id']==select_id:
                        self.listbox.selection_set(i);self.load(r['id']);break
        self.owner.task(self.store.list,show)

    def capture(self):
        def done(row):
            self.info.set('Amostra capturada sem caixas automáticas. Marque a realidade observável.');self.refresh(row['id'])
        self.owner.task(self.owner.controller.capture_sample,done)

    def select(self):
        selected=self.listbox.curselection()
        if not selected or self.owner.busy:return
        if self.dirty and not messagebox.askyesno('Anotação não salva','Descartar alterações não salvas?',parent=self.root):return
        self.load(self.rows[selected[0]]['id'])

    def load(self,sid):
        def done(value):
            if not self.root.winfo_exists():return
            self.row,self.frame=value;self.boxes=[dict(o) for o in self.row['objects']]
            self.complete.set(self.row['state']=='LABELED');self.scope.set(','.join(map(str,self.row['class_ids'])))
            self.group.set(self.row['group']);self.dirty=False;self.drag=None;self.draw()
            self.info.set('Arraste para desenhar caixas. Não crie grupos diferentes para quadros da mesma gravação.')
        self.owner.task(lambda:self.store.load(sid),done)

    def draw(self):
        if not self.root.winfo_exists():return
        self.canvas.delete('all')
        if self.frame is None:return
        image=fit_image(self.frame,max(1,self.canvas.winfo_width()-8),max(1,self.canvas.winfo_height()-8))
        self.photo=ImageTk.PhotoImage(image)
        x=(self.canvas.winfo_width()-image.width)//2;y=(self.canvas.winfo_height()-image.height)//2
        self.canvas.create_image(x,y,anchor='nw',image=self.photo)
        self.bounds=(x,y,image.width/self.row['width'],image.height/self.row['height'])
        for i,obj in enumerate(self.boxes):
            a,b,c,d=obj['box'];sx,sy=self.bounds[2:]
            self.canvas.create_rectangle(x+a*sx,y+b*sy,x+c*sx,y+d*sy,outline='#6ce39b',width=2)
            self.canvas.create_text(x+a*sx+2,y+b*sy+2,anchor='nw',text=f"{i+1}: {NAMES[obj['class_id']]}",fill='#6ce39b')

    def point(self,e):
        if self.bounds is None:return None
        x,y,sx,sy=self.bounds
        a,b=(e.x-x)/sx,(e.y-y)/sy
        if 0<=a<=self.row['width'] and 0<=b<=self.row['height']:return a,b
        return None

    def down(self,e):
        if not self.owner.busy:self.drag=self.point(e)

    def move(self,e):
        p=self.point(e)
        if self.drag is None or p is None:return
        x,y,sx,sy=self.bounds;a,b=self.drag;c,d=p
        self.canvas.delete('drag');self.canvas.create_rectangle(x+a*sx,y+b*sy,x+c*sx,y+d*sy,outline='#ffcf61',width=2,tags='drag')

    def up(self,e):
        p=self.point(e)
        if self.drag is None or p is None:self.drag=None;self.canvas.delete('drag');return
        a,b=self.drag;c,d=p;self.drag=None
        if abs(a-c)<3 or abs(b-d)<3:self.draw();return
        cid=int(self.category.get().rsplit('[',1)[1][:-1])
        self.boxes.append({'class_id':cid,'box':[min(a,c),min(b,d),max(a,c),max(b,d)]})
        try:scope={int(t.strip()) for t in self.scope.get().split(',') if t.strip()}
        except ValueError:scope={0}
        scope.add(cid);self.scope.set(','.join(map(str,sorted(scope))))
        self.dirty=True;self.complete.set(False);self.draw()

    def undo(self):
        if self.boxes:self.boxes.pop();self.dirty=True;self.complete.set(False);self.draw()

    def clear(self):
        if self.boxes and messagebox.askyesno('Limpar caixas','Remover as caixas desta anotação? Ainda será necessário salvar.',parent=self.root):
            self.boxes=[];self.dirty=True;self.complete.set(False);self.draw()

    def save(self):
        if self.row is None or self.owner.busy:return
        try:classes=[int(x.strip()) for x in self.scope.get().split(',') if x.strip()]
        except ValueError:messagebox.showerror('Categorias','Use IDs inteiros separados por vírgula.',parent=self.root);return
        sid=self.row['id'];revision=self.row['revision'];boxes=[dict(o) for o in self.boxes];complete=self.complete.get();group=self.group.get()
        def done(row):
            self.row=row;self.dirty=False;self.info.set('Anotação salva: '+row['state']+'. Rascunhos não são exportados.');self.refresh()
        self.owner.task(lambda:self.store.annotate(sid,boxes,class_ids=classes,complete=complete,expected_revision=revision,group=group),done)

    def export(self):
        if self.owner.busy:return
        choice=messagebox.askyesnocancel('Exportar conjunto','Sim: separar treino/validação/teste por grupos (mínimo 3 gravações).\nNão: exportar um único conjunto para avaliação.\n\nSomente anotações completas entram no pacote.',parent=self.root)
        if choice is None:return
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.zip',initialfile='amostras-vision.zip',filetypes=[('ZIP','*.zip')])
        if path:self.owner.task(lambda:self.store.export(Path(path),split=choice),lambda _:self.info.set('Conjunto exportado em COCO, YOLO e manifesto de avaliação; nenhum modelo foi treinado.'))

    def close(self):
        if self.dirty and not messagebox.askyesno('Anotação não salva','Fechar sem salvar as alterações?',parent=self.root):return
        self.root.destroy()
