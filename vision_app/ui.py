"""One native window. Tk calls only on the main thread; model/disk/network elsewhere."""
from __future__ import annotations
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox,filedialog
from PIL import Image,ImageTk
import cv2
from pydantic import ValidationError
from vision_foundation.config import CameraConfig
from .settings import AnalysisConfig
from .model import ensure_model,MODEL_FILE
from .classes import NAMES
from .preview import compatible
from collections import deque

TYPE_LABELS={'webcam':'Webcam / USB','rtsp':'RTSP / DVR','http':'HTTP / MJPEG','file':'Arquivo de vídeo','demo':'Teste de captura (sem pessoas)'}
from .controls_ui import PROFILES as CLASS_LABELS

class Window:
    def __init__(self,root,controller):
        self.root=root;self.controller=controller
        self.root.title('CamCraft 4.2 — câmera ao vivo')
        self.root.geometry('1100x760');self.root.minsize(760,480)
        self.start_without_analysis=False
        self.last_status_at=0.;self.next_tick=0.;self.painted=deque(maxlen=180);self.painted_frames=0
        self.inset_image=None;self.inset_key=None
        self.closed=False;self.closing=False;self.busy=False;self.messages=queue.Queue();self.poll_busy=False
        self.selected=tk.StringVar();self.status=tk.StringVar(value='Selecione a fonte e clique em Iniciar.')
        self.detail=tk.StringVar(value='Processamento local • IDs temporários • Sem reconhecimento facial')
        self.last_result=None;self.last_render=None;self.photo_image=None;self.display_bounds=None
        self.selection=None;self.selection_frame=None;self.start_point=None;self.event_rows=[]
        self.history_window=None;self.history_tree=None
        style=ttk.Style(root)
        if 'clam' in style.theme_names():style.theme_use('clam')
        style.configure('TButton',padding=(10,6));style.configure('TLabel',padding=(0,2))
        menubar=tk.Menu(root);root.config(menu=menubar)
        menu=tk.Menu(menubar,tearoff=False);menubar.add_cascade(label='Mais',menu=menu)
        filemenu=tk.Menu(menu,tearoff=False)
        filemenu.add_command(label='Salvar foto',command=self.photo)
        for label,func in [('Exportar registros CSV',self.export_csv),('Exportar diagnóstico',self.export_diagnostic),('Abrir pasta de evidências',self.open_evidence_folder)]:filemenu.add_command(label=label,command=func)
        filemenu.add_separator();filemenu.add_command(label='Sair',command=self.close);menu.add_cascade(label='Arquivo',menu=filemenu)
        config=tk.Menu(menu,tearoff=False)
        config.add_command(label='Nova fonte...',command=lambda:self.source_dialog(new=True))
        config.add_command(label='Editar fonte...',command=self.source_dialog)
        config.add_command(label='Excluir fonte...',command=self.delete_source)
        config.add_command(label='Configurar análise...',command=self.analysis_dialog)
        config.add_command(label='Objetos monitorados...',command=self.object_manager)
        config.add_separator();config.add_command(label='Preparar / verificar modelo YOLOX',command=self.prepare_model)
        config.add_separator()
        config.add_command(label='Definir área de análise',command=lambda:self.select_geometry('roi'))
        config.add_command(label='Definir linha de entrada/saída',command=lambda:self.select_geometry('line'))
        config.add_command(label='Limpar área/linha',command=self.clear_geometry)
        menu.add_cascade(label='Configurações',menu=config)
        validation=tk.Menu(menu,tearoff=False)
        validation.add_command(label='Capturar amostra para anotação',command=self.capture_sample)
        validation.add_command(label='Amostras e anotação manual...',command=self.dataset_window)
        validation.add_command(label='Avaliar conjunto anotado...',command=self.evaluate_dataset)
        menu.add_cascade(label='Validação',menu=validation)
        maintenance=tk.Menu(menu,tearoff=False)
        maintenance.add_command(label='Verificar banco e revisões',command=self.check_integrity)
        maintenance.add_command(label='Criar backup completo...',command=self.create_backup)
        maintenance.add_command(label='Verificar pacote ZIP...',command=self.verify_package)
        menu.add_cascade(label='Manutenção',menu=maintenance)
        helpmenu=tk.Menu(menu,tearoff=False)
        helpmenu.add_command(label='Como usar e limites',command=lambda:messagebox.showinfo('CamCraft',
            'Iniciar: câmera + detector.\nÁrea: recorte para concentrar a análise.\nLinha: cruzamento pelos pés da pessoa; a seta mostra entrada.\nIDs valem somente na sessão atual.\n\nScore não é garantia de acerto. Rastreamento perdido não é saída.\nObjetos: cadastre vazio/presente com câmera fixa. Ausência não comprova autoria.\nRetirada PROVÁVEL exige associação temporal adicional; revise as evidências.\nO sistema não identifica rostos, intenção ou furto.\n\nYOLOX precisa do modelo oficial (35,9 MB) na primeira preparação. HOG é apenas diagnóstico de pedestres.\n\nConfira README.md e docs/TESTES_E_LIMITES.md.'))
        menu.add_cascade(label='Ajuda',menu=helpmenu)
        top=ttk.Frame(root,padding=8);top.pack(fill='x')
        ttk.Label(top,text='Fonte:').pack(side='left')
        self.sources=ttk.Combobox(top,textvariable=self.selected,width=20,state='readonly');self.sources.pack(side='left',padx=6)
        self.buttons=[]
        for label,func in [('Iniciar',self.start),('Parar',self.stop),('Pausar IA',self.toggle_analysis),('Controles',self.analysis_dialog),('Registros',self.history)]:
            button=ttk.Button(top,text=label,command=func,width=9);button.pack(side='left',padx=2);self.buttons.append(button)
            if label=='Pausar IA':self.ai_button=button
        self.canvas=tk.Canvas(root,bg='#111318',highlightthickness=0);self.canvas.pack(fill='both',expand=True,padx=8)
        self.canvas.bind('<ButtonPress-1>',self.mouse_down);self.canvas.bind('<B1-Motion>',self.mouse_move);self.canvas.bind('<ButtonRelease-1>',self.mouse_up)
        bottom=ttk.Frame(root,padding=(8,5));bottom.pack(fill='x')
        self.view_mode=tk.StringVar(value=self.controller.display.config.mode)
        ttk.Radiobutton(bottom,text='Ao vivo (fluido)',variable=self.view_mode,value='live',command=self.change_view).pack(side='left',padx=(0,10))
        ttk.Radiobutton(bottom,text='Ver caixas (quadro da IA)',variable=self.view_mode,value='analysis',command=self.change_view).pack(side='left')
        ttk.Button(bottom,text='Objetos...',command=self.object_manager).pack(side='right',padx=4)
        ttk.Button(bottom,text='Foto',command=self.photo).pack(side='right',padx=4)
        self.status_label=ttk.Label(root,textvariable=self.status,wraplength=1060,padding=(10,3));self.status_label.pack(fill='x')
        self.detail_label=ttk.Label(root,textvariable=self.detail,wraplength=1060,padding=(10,3));self.detail_label.pack(fill='x')
        root.bind('<Configure>',lambda e:self.resize_text(e))
        self.recent=tk.Text(root,height=3,wrap='word',state='disabled',font=('TkDefaultFont',9),borderwidth=0)
        # Detailed events remain in Registros; do not clutter the live image with a log console.
        self.refresh_sources()
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.bind('<Escape>',lambda e:self.cancel_selection())
        root.after(30,self.tick);root.after(400,self.poll_events)

    def resize_text(self,event):
        if event.widget is self.root:
            width=max(100,event.width-24)
            self.status_label.configure(wraplength=width);self.detail_label.configure(wraplength=width)

    def refresh_sources(self,select=None):
        values=self.controller.configs.all();self.profiles={c.name+' ['+c.id+']':c.id for c in values}
        self.sources['values']=list(self.profiles)
        pick=next((k for k,v in self.profiles.items() if v==select),None)
        if pick:self.selected.set(pick)
        elif self.selected.get() not in self.profiles:self.selected.set(next(iter(self.profiles),''))
    def selected_id(self):
        cid=self.profiles.get(self.selected.get())
        if not cid:raise ValueError('Selecione uma fonte.')
        return cid
    def task(self,fn,done=None):
        if self.busy or self.closed or self.closing:return
        self.busy=True
        self.status.set('Executando operação...')
        def run():
            try:self.messages.put(('done',done,fn()))
            except Exception as exc:
                message='Configuração inválida. Revise os campos e os limites.' if isinstance(exc,ValidationError) else str(exc)
                self.messages.put(('error',None,message))
        threading.Thread(target=run,daemon=True).start()
    def start(self):
        cid=self.selected_id();self.cancel_selection()
        self.task(lambda:self.controller.start(cid,analyze=not self.start_without_analysis),lambda _:self.status.set('Abrindo câmera; a IA não bloqueia o vídeo.'))
    def stop(self):
        self.cancel_selection();self.task(self.controller.stop,lambda _:self.status.set('Câmera e análise encerradas.'))
    def photo(self):self.task(self.controller.photo,lambda _:self.status.set('Foto enviada para gravação. Confira EVIDENCIA_SALVA nos registros.'))
    def prepare_model(self):
        from .runtime import is_frozen
        if is_frozen():
            from .model import MODEL_FILE, verified
            def check():
                if not verified(self.controller.model_dir/MODEL_FILE):
                    raise RuntimeError('Modelo incluído ausente ou corrompido. Reinstale a distribuição íntegra; nenhum download será feito pelo EXE.')
                return True
            self.task(check, lambda _:self.status.set('Modelo incluído verificado. Nenhum download necessário.'))
            return
        self.task(lambda:ensure_model(self.controller.model_dir,lambda msg:self.messages.put(('progress',None,msg))),
                  lambda _:self.status.set('Modelo verificado. Clique em Iniciar.'))
    def export_csv(self):
        path=filedialog.asksaveasfilename(defaultextension='.csv',initialfile='registros.csv',filetypes=[('CSV','*.csv')])
        if path:self.task(lambda:self.controller.export_csv(Path(path)),lambda n:self.status.set(f'{n} registros exportados.'))
    def export_diagnostic(self):
        path=filedialog.asksaveasfilename(defaultextension='.zip',initialfile='diagnostico_vision.zip',filetypes=[('ZIP','*.zip')])
        if path:self.task(lambda:self.controller.diagnostic(Path(path)),lambda _:self.status.set('Diagnóstico exportado, sem imagens ou credenciais.'))
    def open_path(self,path):
        if not path.exists():messagebox.showwarning('Arquivo indisponível','Arquivo não encontrado; pode ter sido removido pela retenção.');return
        if os.name=='nt':os.startfile(str(path))
        else:subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def open_evidence_folder(self):self.open_path(self.controller.directory/'evidence')

    def object_manager(self):
        from .object_ui import manager
        return manager(self)

    def delete_source(self):
        if self.busy or self.closing:return
        if self.controller.camera:
            messagebox.showinfo('Fonte','Pare a câmera antes de excluir o cadastro.');return
        if len(self.controller.configs.all())<=1:
            messagebox.showinfo('Fonte','Mantenha pelo menos uma fonte cadastrada.');return
        cid=self.selected_id()
        if messagebox.askyesno('Excluir fonte','Excluir somente o cadastro selecionado? As evidências e os registros serão preservados.'):
            self.task(lambda:self.controller.configs.delete(cid),lambda _:self.refresh_sources())

    def source_dialog(self,new=False):
        if self.busy:return
        if self.controller.camera:
            messagebox.showinfo('Fonte','Pare a câmera antes de alterar a fonte.');return
        old=None if new else self.controller.configs.get(self.selected_id())
        dlg=tk.Toplevel(self.root);dlg.title('Fonte de vídeo');dlg.transient(self.root);dlg.grab_set();dlg.resizable(False,False)
        form=ttk.Frame(dlg,padding=14);form.pack(fill='both')
        fields={}
        values={'name':old.name if old else 'Nova câmera','source':old.source if old and old.kind not in ('rtsp','http') else '',
                'width':str(old.width if old else 1280),'height':str(old.height if old else 720),'fps':str(old.fps if old else 30)}
        for i,(key,label) in enumerate([('name','Nome'),('source','Índice, URL ou caminho'),('width','Largura solicitada (webcam)'),('height','Altura solicitada (webcam)'),('fps','FPS solicitado (webcam)')]):
            ttk.Label(form,text=label).grid(row=i,column=0,sticky='w',padx=(0,10),pady=4)
            var=tk.StringVar(value=values[key]);entry=ttk.Entry(form,textvariable=var,width=55 if key=='source' else 26)
            entry.grid(row=i,column=1,sticky='ew',pady=4);fields[key]=(var,entry)
        kind=tk.StringVar(value=TYPE_LABELS[old.kind if old else 'webcam'])
        ttk.Label(form,text='Tipo').grid(row=5,column=0,sticky='w')
        kindbox=ttk.Combobox(form,textvariable=kind,values=list(TYPE_LABELS.values()),state='readonly',width=38);kindbox.grid(row=5,column=1,sticky='w',pady=4)
        def update(*_):
            network=kind.get() in (TYPE_LABELS['rtsp'],TYPE_LABELS['http'])
            fields['source'][1].configure(show='*' if network else '')
        kindbox.bind('<<ComboboxSelected>>',update);update()
        def browse():
            path=filedialog.askopenfilename(parent=dlg,filetypes=[('Vídeos','*.mp4 *.avi *.mkv *.mov *.webm *.mjpeg *.ts'),('Todos','*.*')])
            if path:kind.set(TYPE_LABELS['file']);fields['source'][0].set(path);update()
        ttk.Button(form,text='Escolher vídeo...',command=browse).grid(row=6,column=1,sticky='w',pady=4)
        backend=tk.StringVar(value=old.backend if old else 'auto')
        ttk.Label(form,text='Backend da webcam').grid(row=7,column=0,sticky='w')
        ttk.Combobox(form,textvariable=backend,values=['auto','dshow','msmf','v4l2','avfoundation'],state='readonly',width=20).grid(row=7,column=1,sticky='w')
        loop=tk.BooleanVar(value=old.loop if old else True)
        ttk.Checkbutton(form,text='Repetir arquivo (reinicia IDs a cada volta)',variable=loop).grid(row=8,columnspan=2,sticky='w',pady=6)
        ttk.Label(form,text='Rede: deixe o endereço vazio para manter a URL já cadastrada.\nA resolução/FPS de RTSP é configurada no DVR, não neste formulário.',wraplength=570).grid(row=9,columnspan=2,sticky='w',pady=6)
        fourcc=tk.StringVar(value=old.fourcc if old else 'MJPG')
        pubfps=tk.StringVar(value=str(old.publish_fps if old else 30))
        ttk.Label(form,text='Formato USB / publicação FPS').grid(row=10,column=0,sticky='w')
        extra=ttk.Frame(form);extra.grid(row=10,column=1,sticky='w')
        ttk.Combobox(extra,textvariable=fourcc,values=['MJPG','auto','YUY2'],state='readonly',width=10).pack(side='left')
        ttk.Spinbox(extra,textvariable=pubfps,from_=5,to=30,width=6).pack(side='left',padx=8)
        def save():
            try:
                k=next(k for k,v in TYPE_LABELS.items() if v==kind.get())
                source=fields['source'][0].get().strip()
                if not source and old and old.kind==k:source=old.source
                if k=='demo':source='demo'
                values={'name':fields['name'][0].get(),'kind':k,'source':source,'width':int(fields['width'][0].get()),'height':int(fields['height'][0].get()),'fps':int(fields['fps'][0].get()),'backend':backend.get() if k=='webcam' else 'auto','loop':loop.get(),'fourcc':fourcc.get(),'publish_fps':int(pubfps.get())}
                base=old.model_dump() if old else {}
                cfg=CameraConfig.model_validate({**base,**values})
                self.controller.configs.put(cfg);self.refresh_sources(cfg.id);dlg.destroy()
            except (ValueError,OSError):messagebox.showerror('Fonte inválida','Confira tipo, índice/URL/arquivo, resolução e FPS. Nenhuma configuração anterior foi apagada.',parent=dlg)
        ttk.Button(form,text='Salvar',command=save).grid(row=11,column=1,sticky='e',pady=8)

    def analysis_dialog(self):
        if self.busy:return
        from .controls_ui import ControlsDialog
        self.controls=ControlsDialog(self)

    def toggle_analysis(self):
        if self.busy or not self.controller.camera:return
        if self.controller.analysis:
            self.task(self.controller.pause_analysis,lambda _:self.status.set('IA pausada; câmera continua ao vivo.'))
        else:
            self.task(self.controller.resume_analysis,lambda _:self.status.set('IA retomada em nova sessão.'))

    def change_view(self):
        self.painted.clear()
        cfg=self.controller.display.config.model_copy(update={'mode':self.view_mode.get()})
        try:
            self.controller.display.put(cfg)
            if self.controller.preview:self.controller.preview.configure(cfg)
            self.last_render=None
        except OSError:messagebox.showerror('Exibição','Não foi possível salvar a preferência de exibição.')

    def select_geometry(self,mode):
        if self.busy:return
        result=self.controller.analysis.latest() if self.controller.analysis else None
        if result is None:messagebox.showinfo('Vídeo necessário','Inicie a câmera e aguarde um quadro analisado atual.');return
        self.selection=mode;self.selection_frame=result;self.start_point=None;self.last_render=None
        self.canvas.delete('inset');self.inset_key=None
        self.status.set('Seleção: imagem congelada apenas na tela. Arraste para definir '+('o local VAZIO do objeto.' if mode=='object' else 'a área.' if mode=='roi' else 'a linha A → B. A seta indicará entrada.')+' Esc cancela.')
    def cancel_selection(self):
        self.selection=None;self.selection_frame=None;self.start_point=None;self.last_render=None
        self.canvas.delete('selection')
    def normalized(self,x,y):
        if self.display_bounds is None:return None
        a,b,w,h=self.display_bounds
        if not a<=x<=a+w or not b<=y<=b+h:return None
        return ((x-a)/w,(y-b)/h)
    def mouse_down(self,event):
        if self.selection:self.start_point=self.normalized(event.x,event.y)
    def mouse_move(self,event):
        if not self.selection or self.start_point is None:return
        point=self.normalized(event.x,event.y)
        if point is None:return
        a,b,w,h=self.display_bounds;x,y=self.start_point;p,q=point
        self.canvas.delete('selection')
        coords=(a+x*w,b+y*h,a+p*w,b+q*h)
        if self.selection in ('roi','object'):self.canvas.create_rectangle(*coords,outline='#ffd25a',width=2,tags='selection')
        else:self.canvas.create_line(*coords,fill='#ffd25a',width=3,arrow='last',tags='selection')
    def mouse_up(self,event):
        if not self.selection or self.start_point is None:return
        point=self.normalized(event.x,event.y)
        if point is None:self.start_point=None;return
        mode=self.selection;x,y=self.start_point;p,q=point
        value=(min(x,p),min(y,q),max(x,p),max(y,q)) if mode in ('roi','object') else (x,y,p,q)
        if mode=='object':
            from .object_registry import roi_pixels
            a,b,c,d=roi_pixels(value,self.selection_frame.original.shape)
            if c-a<24 or d-b<24 or (value[2]-value[0])*(value[3]-value[1])>.35:
                messagebox.showwarning('Área do objeto','Use pelo menos 24 × 24 pixels e no máximo 35% da imagem. Arraste novamente.');return
            empty=self.selection_frame
            self.cancel_selection()
            from .object_ui import calibration
            calibration(self,value,empty)
            return
        cid=self.selected_id();cfg=self.controller.settings.get(cid)
        try:cfg=AnalysisConfig.model_validate({**cfg.model_dump(),mode:value})
        except ValueError:messagebox.showwarning('Seleção','Área/linha pequena demais. Arraste uma região maior.');return
        self.cancel_selection()
        def apply():
            self.controller.configure_analysis(cid,cfg,self.controller.display.config)
        self.task(apply,lambda _:self.status.set('Configuração aplicada. Nova sessão de IDs iniciada.'))
    def clear_geometry(self):
        if self.busy:return
        cid=self.selected_id();cfg=self.controller.settings.get(cid);cfg.roi=None;cfg.line=None
        running=self.controller.camera is not None;self.cancel_selection()
        def apply():
            self.controller.configure_analysis(cid,cfg,self.controller.display.config)
        self.task(apply,lambda _:self.status.set('Área e linha removidas.'))

    def history(self):
        if self.history_window and self.history_window.winfo_exists():self.history_window.lift();return
        from .review_ui import ReviewWindow
        self.review_browser=ReviewWindow(self)
        self.history_window=self.review_browser.root;self.history_tree=self.review_browser.tree

    def fill_history(self):
        # Stable pagination is intentional: live events must not move the operator's selection.
        return

    def event_detail(self,event=None):
        if hasattr(self,'review_browser'):self.review_browser.details()

    def capture_sample(self):
        self.task(self.controller.capture_sample,lambda row:self.status.set('Amostra '+row['id'][-10:]+' salva como rascunho. Abra Validação > Amostras para anotar.'))

    def dataset_window(self):
        if self.busy:return
        from .dataset_ui import DatasetWindow
        self.dataset_browser=DatasetWindow(self)

    def check_integrity(self):
        self.task(self.controller.integrity,lambda result:messagebox.showinfo('Integridade local',json.dumps(result,ensure_ascii=False,indent=2)))

    def create_backup(self):
        if self.busy:return
        if self.controller.camera:
            messagebox.showinfo('Backup','Pare a câmera antes de criar um snapshot consistente.');return
        if not messagebox.askyesno('Backup local','O pacote contém imagens, horários e configurações de câmera, incluindo credenciais na proteção original. O ZIP não é criptografado. Guardar em local restrito?'):return
        path=filedialog.asksaveasfilename(defaultextension='.zip',initialfile='vision-backup-'+time.strftime('%Y%m%d-%H%M%S')+'.zip',filetypes=[('ZIP','*.zip')])
        if path:self.task(lambda:self.controller.backup(Path(path)),lambda _:self.status.set('Backup criado e verificado. Restauração somente em pasta vazia.'))

    def verify_package(self):
        if self.busy:return
        path=filedialog.askopenfilename(filetypes=[('Pacote Vision','*.zip')])
        if not path:return
        from .safe_archive import verify_archive
        self.task(lambda:verify_archive(Path(path)),lambda report:messagebox.showinfo('Pacote verificado',str(len(report['files']))+' arquivos íntegros contra o manifesto. Tipo: '+report['kind']+'\nHashes não são assinatura digital.'))

    def evaluate_dataset(self):
        from .validation_ui import evaluate_dialog
        evaluate_dialog(self)

    def poll_events(self):
        if self.closed:return
        if not self.poll_busy:
            self.poll_busy=True
            def read():
                try:self.messages.put(('events',None,self.controller.events.events(limit=100)))
                except Exception:self.messages.put(('events',None,[]))
            threading.Thread(target=read,daemon=True).start()
        self.root.after(700,self.poll_events)

    def tick(self):
        if self.closed:return
        try:
            while True:
                kind,callback,value=self.messages.get_nowait()
                if kind=='done':
                    self.busy=False
                    if callback:callback(value)
                elif kind=='error':self.busy=False;self.status.set(value);messagebox.showerror('Operação não concluída',value)
                elif kind=='progress':self.status.set(value)
                elif kind=='events':
                    self.poll_busy=False
                    if value!=self.event_rows:
                        self.event_rows=value;self.fill_history()
                        lines=[time.strftime('%H:%M:%S',time.localtime(r['utc']))+'  '+r['code']+'  '+r['payload'].get('object_name',r['payload'].get('class_name','')) for r in value[:3]]
                        self.recent.configure(state='normal');self.recent.delete('1.0','end');self.recent.insert('1.0','\n'.join(lines));self.recent.configure(state='disabled')
                elif kind=='closed':self.closed=True;self.root.destroy();return
        except queue.Empty:pass
        service=self.controller.analysis
        preview=self.controller.preview
        result=self.selection_frame if self.selection else (service.latest() if service else None)
        cw,ch=max(1,self.canvas.winfo_width()),max(1,self.canvas.winfo_height())
        if preview:preview.resize(cw,ch)
        live=preview.latest() if preview else None
        now=time.monotonic()
        cfg=self.controller.display.config
        mode='analysis' if self.selection else cfg.mode
        if mode=='live' and live is not None:
            image=live.image;key=('live',live.key)
        elif mode=='analysis' and result is not None:
            key=('analysis',id(result),cw,ch)
            image=None
            if key!=self.last_render:
                h,w=result.frame.shape[:2];scale=min(cw/w,ch/h,1.)
                rw,rh=max(1,int(w*scale)),max(1,int(h*scale))
                resized=cv2.resize(result.frame,(rw,rh),interpolation=cv2.INTER_AREA) if (rw,rh)!=(w,h) else result.frame
                image=Image.fromarray(cv2.cvtColor(resized,cv2.COLOR_BGR2RGB))
        else:
            key=('empty',mode,cw,ch,bool(service));image=None
        if key!=self.last_render:
            self.last_render=key
            self.canvas.delete('empty')
            if image is not None:
                rw,rh=image.size;x,y=(cw-rw)//2,(ch-rh)//2
                if self.photo_image is not None and (self.photo_image.width(),self.photo_image.height())==image.size:
                    self.photo_image.paste(image)
                else:self.photo_image=ImageTk.PhotoImage(image)
                ids=self.canvas.find_withtag('frame')
                if ids:
                    self.canvas.itemconfigure(ids[0],image=self.photo_image,state='normal');self.canvas.coords(ids[0],x,y)
                else:self.canvas.create_image(x,y,anchor='nw',image=self.photo_image,tags='frame')
                self.canvas.tag_lower('frame');self.display_bounds=(x,y,rw,rh)
                self.last_result=result
                self.painted.append(now);self.painted_frames+=1
            else:
                self.canvas.itemconfigure('frame',state='hidden');self.display_bounds=None
                message=('Aguardando vídeo atual.' if mode=='live' else 'Sem análise atual. O vídeo ao vivo continua disponível.')
                if not self.controller.camera:message='Selecione a câmera e clique em Iniciar.'
                self.canvas.create_text(cw/2,ch/2,text=message,fill='#d3d7df',font=('TkDefaultFont',13),justify='center',width=max(100,cw-80),tags='empty')
        # Never put old boxes on a new raw frame. A labelled inset contains the exact analysed frame.
        inset_ok=(not self.selection and mode=='live' and cfg.show_inset and live is not None
            and compatible(result,live.metadata,now,service.cfg.max_frame_age if service else 0))
        inset_key=(id(result),cw,ch) if inset_ok else None
        if inset_key!=self.inset_key:
            self.canvas.delete('inset');self.inset_key=inset_key
            if inset_ok:
                h,w=result.frame.shape[:2];width=min(300,max(150,cw//3));height=max(1,int(h*width/w))
                if height>ch//2:height=max(1,ch//2);width=max(1,int(w*height/h))
                small=cv2.resize(result.frame,(width,height),interpolation=cv2.INTER_AREA)
                self.inset_image=ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(small,cv2.COLOR_BGR2RGB)))
                x,y=cw-width-10,34
                self.canvas.create_rectangle(x-3,y-25,cw-7,y+height+3,fill='#161a20',outline='#808a96',tags='inset')
                self.canvas.create_image(x,y,anchor='nw',image=self.inset_image,tags='inset')
                self.canvas.create_text(x+3,y-13,anchor='w',text=f"Quadro da IA · {(now-result.metadata['received_monotonic'])*1000:.0f} ms atrás",fill='white',tags=('inset','inset_label'))
        if now-self.last_status_at>=.25:
            self.last_status_at=now
            if inset_ok:
                age=(now-result.metadata['received_monotonic'])*1000
                self.canvas.itemconfigure('inset_label',text=f'Quadro da IA · {age:.0f} ms atrás')
            cap=self.controller.camera.snapshot() if self.controller.camera else {}
            s=service.snapshot() if service else {}
            painted_fps=((len(self.painted)-1)/(self.painted[-1]-self.painted[0])) if len(self.painted)>1 and now-self.painted[-1]<1 else 0.
            if not self.busy and not self.selection and self.controller.camera:
                state='IA pausada' if service is None else s['state']
                self.status.set(f"Vídeo {painted_fps:.1f} FPS exibidos | Câmera {cap.get('decoded_fps',0):.1f} FPS | "
                    f"IA {s.get('analysis_fps',0):.1f} análises/s | {state}")
                health=self.controller.events.health();eh=self.controller.evidence.health()
                warning=' ATENÇÃO: falha/descarte em registros ou evidências.' if not health['healthy'] or not eh['healthy'] else ''
                if eh.get('retention_blocked_by_preserved'):warning+=' Evidências preservadas excedem a cota.'
                names=[]
                if result:
                    names=[NAMES[t['class_id']] for t in result.tracks if t['confirmed']]
                recent=', '.join(names[:6]) if names else 'nenhuma categoria confirmada'
                if service and s.get('state') not in ('RUNNING',):warning+=' '+s.get('reason','')
                age=(now-live.metadata['received_monotonic'])*1000 if live else None
                age_label=f'{age:.0f} ms' if age is not None else 'sem quadro recente'
                self.detail.set(f"Vídeo após decodificação: {age_label}. Última análise: {recent}.{warning}")
            self.sources.configure(state='disabled' if self.busy or self.controller.camera else 'readonly')
            self.ai_button.configure(text='Pausar IA' if service else 'Ativar IA',
                state='normal' if self.controller.camera and not self.busy else 'disabled')
        # Subtract render cost rather than sleeping a fixed 45 ms AFTER each render.
        period=1/max(5,cfg.fps);self.next_tick=max(self.next_tick+period,now)
        self.root.after(max(1,int((self.next_tick-time.monotonic())*1000)),self.tick)

    def close(self):
        if self.closed or self.closing:return
        self.closing=True
        self.status.set('Encerrando captura, análise e gravações...')
        def shut():
            try:self.controller.close();self.messages.put(('closed',None,None))
            except Exception as exc:
                self.closing=False
                self.messages.put(('error',None,'Falha no encerramento: '+str(exc)))
        threading.Thread(target=shut,daemon=True).start()
