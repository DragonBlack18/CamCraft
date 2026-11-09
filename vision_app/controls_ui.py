"""A small default screen, with explicit category selection and optional detailed controls."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from .settings import AnalysisConfig
from .preview import PreviewConfig
from .classes import NAMES, allowed

PROFILES = {'bedroom':'Quarto / escritório', 'people':'Somente pessoas',
            'indoor':'Ambiente interno', 'all':'Todas (inclui veículos)', 'custom':'Escolher categorias'}
ENGINES = {'yolox':'Pessoas e objetos (YOLOX)', 'regions':'Somente objetos cadastrados',
           'hog':'Diagnóstico HOG (não recomendado)'}


def scroll_panel(parent):
    outer=ttk.Frame(parent)
    canvas=tk.Canvas(outer,highlightthickness=0)
    bar=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set)
    bar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
    inner=ttk.Frame(canvas,padding=8)
    item=canvas.create_window((0,0),window=inner,anchor='nw')
    inner.bind('<Configure>',lambda _e:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
    def wheel(e):
        step=-int(e.delta/120) if e.delta else (-1 if e.num==4 else 1)
        canvas.yview_scroll(step,'units');return 'break'
    # Scoped bindings: do not leave bind_all callbacks attached to destroyed dialogs.
    for ev in ('<MouseWheel>','<Button-4>','<Button-5>'):canvas.bind(ev,wheel)
    outer.pack(fill='both',expand=True)
    return inner


class ControlsDialog:
    def __init__(self, window):
        self.window=window;self.cid=window.selected_id()
        self.old=window.controller.settings.get(self.cid)
        self.display=window.controller.display.config
        self.overrides=dict(self.old.class_thresholds)
        self.vars={};self.boxes=[]
        self.root=tk.Toplevel(window.root);self.root.title('Controles da câmera e da IA')
        self.root.geometry('680x600');self.root.minsize(600,510)
        self.root.transient(window.root);self.root.grab_set()
        notebook=ttk.Notebook(self.root);self.notebook=notebook;notebook.pack(fill='both',expand=True,padx=10,pady=10)
        basic=ttk.Frame(notebook,padding=14);categories=ttk.Frame(notebook);advanced=ttk.Frame(notebook)
        notebook.add(basic,text='Básico');notebook.add(categories,text='O que detectar');notebook.add(advanced,text='Ajustes finos')
        self.profile=tk.StringVar(value=PROFILES[self.old.classes])
        self.engine=tk.StringVar(value=ENGINES[self.old.engine])
        ttk.Label(basic,text='1. Onde a câmera está?').pack(anchor='w')
        profile=ttk.Combobox(basic,textvariable=self.profile,values=list(PROFILES.values()),state='readonly',width=42)
        profile.pack(anchor='w',pady=(0,10));profile.bind('<<ComboboxSelected>>',lambda _e:self.choose_profile())
        ttk.Label(basic,text='2. O que deve funcionar?').pack(anchor='w')
        ttk.Combobox(basic,textvariable=self.engine,values=list(ENGINES.values()),state='readonly',width=42).pack(anchor='w',pady=(0,10))
        ttk.Label(basic,text='3. Escolha um ponto de partida (depois pode ajustar)').pack(anchor='w')
        row=ttk.Frame(basic);row.pack(anchor='w',pady=(0,10))
        for name in ('Menos alarmes','Equilibrado','Mais sensível'):
            ttk.Button(row,text=name,command=lambda n=name:self.preset(n)).pack(side='left',padx=(0,5))
        self.summary=tk.StringVar()
        ttk.Label(basic,textvariable=self.summary,wraplength=600).pack(anchor='w',pady=(0,12))
        self.inset=tk.BooleanVar(value=self.display.show_inset)
        self.photos=tk.BooleanVar(value=self.old.save_evidence)
        ttk.Checkbutton(basic,text='Mostrar miniatura do último quadro analisado',variable=self.inset).pack(anchor='w')
        ttk.Checkbutton(basic,text='Salvar imagens dos eventos confirmados',variable=self.photos).pack(anchor='w')
        ttk.Label(basic,text=('O vídeo ao vivo não espera a IA. As caixas aparecem na miniatura ou em “Ver caixas”.\n'
            'Quarto exclui carros e outros veículos; não transforma uma coberta em pessoa.\n'
            'Uma pessoa encoberta pode não ser reconhecida. Ausência de rótulo não prova sala vazia.\n'
            'O score é um limiar do modelo, não uma porcentagem de certeza.'),wraplength=610).pack(anchor='w',pady=12)
        if window.controller.settings.migration_notice:
            ttk.Label(basic,text=window.controller.settings.migration_notice,wraplength=610).pack(anchor='w',pady=5)
        # Explicit class allow-list. Filtering never reclassifies a rejected winning category.
        bar=ttk.Frame(categories,padding=8);bar.pack(fill='x')
        ttk.Label(bar,text='Buscar:').pack(side='left');self.search=tk.StringVar()
        ttk.Entry(bar,textvariable=self.search,width=22).pack(side='left',padx=6)
        ttk.Button(bar,text='Só pessoas',command=lambda:self.set_profile('people')).pack(side='left',padx=3)
        ttk.Button(bar,text='Quarto',command=lambda:self.set_profile('bedroom')).pack(side='left',padx=3)
        area=scroll_panel(categories);self.class_vars={}
        chosen=self.old.class_ids()
        for c,name in enumerate(NAMES):
            var=tk.BooleanVar(value=c in chosen);self.class_vars[c]=var
            box=ttk.Checkbutton(area,text=name,variable=var,command=self.custom)
            self.boxes.append((c,box))
        self.search.trace_add('write',lambda *_:self.filter_boxes())
        self.filter_boxes()
        # Optional exact controls. None of these silently changes the model input resolution.
        adv=scroll_panel(advanced)
        specs=[('confidence','Limiar geral (0,25–0,95)',float),('max_fps','Máximo de análises/s (1–30)',int),
            ('threads','Threads da IA / CPU (1–8)',int),('duty_cycle','Ocupação-alvo da IA (0,30–1)',float),
            ('min_hits','Observações fortes para confirmar (2–10)',int),('confirm_seconds','Tempo mínimo observado, s (0,1–3)',float),
            ('class_margin','Separação entre categorias (0–0,9)',float),
            ('recovery_seconds','Tolerar score fraco após confirmação, s (0–5)',float),
            ('lost_seconds','Expirar rastreamento, s (0,5–10)',float),
            ('confirmation_gap','Maior intervalo para confirmação, s (0,2–5)',float),
            ('low_confidence','Limiar baixo para recuperar IDs (0,05–0,2)',float),
            ('nms_iou','Supressão de caixas sobrepostas (0,2–0,8)',float),
            ('max_frame_age','Idade máxima do resultado da IA, s (0,5–5)',float)]
        self.types={}
        for r,(key,label,typ) in enumerate(specs):
            self.vars[key]=tk.StringVar(value=str(getattr(self.old,key)));self.types[key]=typ
            ttk.Label(adv,text=label).grid(row=r,column=0,sticky='w',pady=3)
            ttk.Entry(adv,textvariable=self.vars[key],width=10).grid(row=r,column=1,sticky='w',padx=8)
        base=len(specs)
        self.preview_fps=tk.StringVar(value=str(self.display.fps))
        self.preview_width=tk.StringVar(value=str(self.display.max_width))
        self.preview_age=tk.StringVar(value=str(self.display.max_age))
        for r,(label,var) in enumerate([('Limite de atualização do vídeo (5–60 FPS)',self.preview_fps),
            ('Largura máxima da prévia (320–1920)',self.preview_width),('Idade máxima do vídeo, s (0,2–2)',self.preview_age)],base):
            ttk.Label(adv,text=label).grid(row=r,column=0,sticky='w',pady=3)
            ttk.Entry(adv,textvariable=var,width=10).grid(row=r,column=1,sticky='w',padx=8)
        self.adaptive=tk.BooleanVar(value=self.old.adaptive_pacing)
        self.tentative=tk.BooleanVar(value=self.old.show_tentative)
        self.positive=tk.BooleanVar(value=self.old.positive_is_entry)
        for r,(label,var) in enumerate([('Reservar folga de CPU (cadenciamento adaptativo)',self.adaptive),
            ('Mostrar candidatos NÃO confirmados (diagnóstico)',self.tentative),
            ('Entrada no sentido padrão da linha (desmarcar inverte)',self.positive)],base+3):
            ttk.Checkbutton(adv,text=label,variable=var).grid(row=r,columnspan=2,sticky='w',pady=3)
        group=ttk.LabelFrame(adv,text='Limiar específico por categoria',padding=8)
        group.grid(row=base+6,columnspan=2,sticky='ew',pady=12)
        self.override_class=tk.StringVar(value='pessoa [0]');self.override_value=tk.StringVar()
        self.override_combo=ttk.Combobox(group,textvariable=self.override_class,state='readonly',width=28,
            values=[f'{name} [{i}]' for i,name in enumerate(NAMES)])
        self.override_combo.grid(row=0,column=0,sticky='w');self.override_combo.bind('<<ComboboxSelected>>',lambda _e:self.refresh_override())
        ttk.Entry(group,textvariable=self.override_value,width=8).grid(row=0,column=1,padx=6)
        ttk.Button(group,text='Definir',command=self.set_override).grid(row=0,column=2)
        ttk.Label(group,text='Vazio remove a exceção e usa o limiar geral. Depois clique em Aplicar.',wraplength=530).grid(row=1,columnspan=3,sticky='w')
        self.refresh_override()
        for key in ('confidence','min_hits','confirm_seconds'):
            self.vars[key].trace_add('write',lambda *_:self.refresh_summary())
        self.refresh_summary()
        footer=ttk.Frame(self.root,padding=(10,0,10,10));footer.pack(fill='x')
        ttk.Label(footer,text='Aplicar reinicia só a IA; a câmera continua ligada.').pack(side='left')
        ttk.Button(footer,text='Cancelar',command=self.root.destroy).pack(side='right',padx=4)
        self.apply_button=ttk.Button(footer,text='Aplicar',command=self.apply);self.apply_button.pack(side='right',padx=4)

    def preset(self,name):
        params={'Menos alarmes':(.70,4,.8,.2),'Equilibrado':(.60,3,.55,.15),'Mais sensível':(.45,3,.35,.05)}[name]
        for key,val in zip(('confidence','min_hits','confirm_seconds','class_margin'),params):self.vars[key].set(str(val))
        self.refresh_summary()

    def refresh_summary(self):
        self.summary.set(f"Limiar {self.vars['confidence'].get()} · {self.vars['min_hits'].get()} observações · "
            f"{self.vars['confirm_seconds'].get()} s mínimo. Exceções por categoria: {len(self.overrides)}.\n"
            'Menos alarmes pode deixar passar mais pessoas/objetos. Não é melhoria automática do modelo.')

    def set_profile(self,key):
        self.profile.set(PROFILES[key]);self.choose_profile()

    def choose_profile(self):
        key=next(k for k,v in PROFILES.items() if v==self.profile.get())
        if key!='custom':
            values=allowed(key)
            for c,var in self.class_vars.items():var.set(c in values)

    def custom(self): self.profile.set(PROFILES['custom'])

    def filter_boxes(self):
        import unicodedata
        clean=lambda x:unicodedata.normalize('NFKD',x.lower()).encode('ascii','ignore').decode()
        term=clean(self.search.get());n=0
        for c,box in self.boxes:
            box.grid_forget()
            if term in clean(NAMES[c]):
                box.grid(row=n//3,column=n%3,sticky='w',padx=(4,12),pady=3);n+=1

    def selected_override(self): return int(self.override_class.get().rsplit('[',1)[1][:-1])

    def refresh_override(self):
        value=self.overrides.get(self.selected_override())
        self.override_value.set('' if value is None else str(value))

    def set_override(self):
        try:
            c=self.selected_override();text=self.override_value.get().strip().replace(',','.')
            if text:
                val=float(text)
                if not .25<=val<=.95:raise ValueError()
                self.overrides[c]=val
            else:self.overrides.pop(c,None)
            self.refresh_summary()
        except ValueError:messagebox.showerror('Limiar','Use um número entre 0,25 e 0,95 ou deixe vazio.',parent=self.root)

    def apply(self):
        if self.window.busy:return
        try:
            key=next(k for k,v in PROFILES.items() if v==self.profile.get())
            if key=='all' and not messagebox.askyesno('Todas as categorias',
                'Isso permite veículos, animais e categorias fora do quarto. Pode aumentar falsos positivos. Continuar?',parent=self.root):return
            values={k:typ(v.get().replace(',','.')) for k,v in self.vars.items() for typ in [self.types[k]]}
            cfg=AnalysisConfig.model_validate({**self.old.model_dump(),**values,'classes':key,
                'custom_classes':[c for c,v in self.class_vars.items() if v.get()],
                'class_thresholds':self.overrides,'engine':next(k for k,v in ENGINES.items() if v==self.engine.get()),
                'save_evidence':self.photos.get(),'adaptive_pacing':self.adaptive.get(),
                'positive_is_entry':self.positive.get(),'show_tentative':self.tentative.get()})
            display=PreviewConfig.model_validate({**self.display.model_dump(),'fps':int(self.preview_fps.get()),
                'max_width':int(self.preview_width.get()),'max_age':float(self.preview_age.get().replace(',','.')),
                'show_inset':self.inset.get()})
        except ValueError:
            messagebox.showerror('Controles','Confira os intervalos em Ajustes finos e selecione pelo menos uma categoria.',parent=self.root);return
        def done(_):
            self.window.last_render=None
            self.window.status.set('Controles aplicados. Nova sessão da IA; vídeo preservado.')
            self.root.destroy()
        self.window.task(lambda:self.window.controller.configure_analysis(self.cid,cfg,display),done)
