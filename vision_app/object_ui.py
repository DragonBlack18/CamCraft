"""Small object-registration dialogs; the main window remains a camera viewer."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk,messagebox
from PIL import Image,ImageTk
import cv2
from .classes import NAMES
from .object_registry import InteractionConfig,roi_pixels


def manager(window):
    if window.busy:return
    cid=window.selected_id()
    dialog=tk.Toplevel(window.root);dialog.title('Objetos monitorados');dialog.geometry('690x410')
    dialog.transient(window.root)
    frame=ttk.Frame(dialog,padding=12);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Cadastre o local vazio e depois com o objeto. Câmera fixa; até 8 locais por fonte.',wraplength=640).pack(anchor='w',pady=(0,8))
    tree=ttk.Treeview(frame,columns=('name','enabled','state'),show='headings',height=8)
    for key,title,width in [('name','Objeto / local',260),('enabled','Monitorar',80),('state','Estado atual',270)]:
        tree.heading(key,text=title);tree.column(key,width=width)
    tree.pack(fill='both',expand=True)
    def refresh():
        if not dialog.winfo_exists():return
        selection=tree.selection();tree.delete(*tree.get_children())
        states={}
        service=window.controller.analysis
        if service and window.controller.camera.config.id==cid:
            states={o['id']:o['state'] for o in service.snapshot().get('objects',[])}
        for obj in window.controller.objects.all(cid):
            tree.insert('',tk.END,iid=obj.id,values=(obj.name,'Sim' if obj.enabled else 'Pausado',states.get(obj.id,'Aguardando análise')))
        if selection and tree.exists(selection[0]):tree.selection_set(selection)
        dialog.after(600,refresh)
    def selected():
        ids=tree.selection()
        if not ids:messagebox.showinfo('Objeto','Selecione um cadastro.',parent=dialog);return None
        return next((o for o in window.controller.objects.all(cid) if o.id==ids[0]),None)
    def add(old=None):
        if window.busy:return
        if not window.controller.camera or window.controller.camera.config.id!=cid:
            messagebox.showinfo('Câmera','Inicie a fonte antes de cadastrar objetos.',parent=dialog);return
        dialog.destroy()
        messagebox.showinfo('Referência vazia — 1/2',
            'Retire o objeto do local, mantenha a câmera imóvel e deixe a área livre.\n\nDepois de fechar esta mensagem, arraste um retângulo pequeno sobre o local vazio no vídeo.\n\nNa próxima janela você colocará o objeto no local e salvará a referência ocupada.',parent=window.root)
        window.calibration_replace=old
        window.select_geometry('object')
    def redo():
        obj=selected()
        if obj:add(obj)
    def toggle():
        obj=selected()
        if obj:window.task(lambda:window.controller.object_enabled(cid,obj.id,not obj.enabled))
    def remove():
        obj=selected()
        if obj and messagebox.askyesno('Excluir cadastro','Excluir '+obj.name+'? As evidências e o histórico serão preservados.',parent=dialog):
            window.task(lambda:window.controller.remove_object(cid,obj.id))
    buttons=ttk.Frame(frame);buttons.pack(fill='x',pady=8)
    for label,fn in [('Novo',add),('Recalibrar',redo),('Ativar / pausar',toggle),('Excluir',remove)]:ttk.Button(buttons,text=label,command=fn).pack(side='left',padx=3)
    ttk.Button(frame,text='Tempos, monitoramento e clipes...',command=lambda:settings(window,cid)).pack(anchor='w')
    ttk.Label(frame,text='Ausência não identifica quem retirou. Itens visualmente iguais não têm identidade física verificada.',wraplength=640).pack(anchor='w',pady=5)
    refresh()
    return dialog,tree


def calibration(window,roi,empty_result):
    old=getattr(window,'calibration_replace',None)
    dialog=tk.Toplevel(window.root);dialog.title('Objeto — referência ocupada · 2/2')
    dialog.geometry('660x530');dialog.transient(window.root)
    frame=ttk.Frame(dialog,padding=14);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Coloque o objeto no local marcado e afaste-se. Não mova a câmera.',wraplength=620).pack(anchor='w')
    form=ttk.Frame(frame);form.pack(fill='x',pady=10)
    name=tk.StringVar(value=old.name if old else '')
    ttk.Label(form,text='Nome do objeto:').grid(row=0,column=0,sticky='w')
    ttk.Entry(form,textvariable=name,width=42).grid(row=0,column=1,padx=10)
    options={'Sem categoria fixa (comparação visual)':None}
    options.update({f'{NAMES[i]} [{i}]':i for i in range(1,len(NAMES))})
    default=next((k for k,v in options.items() if old and v==old.class_id),next(iter(options)))
    category=tk.StringVar(value=default)
    ttk.Label(form,text='Categoria opcional:').grid(row=1,column=0,sticky='w',pady=8)
    ttk.Combobox(form,values=list(options),textvariable=category,state='readonly',width=40).grid(row=1,column=1,padx=10)
    previews=ttk.Frame(frame);previews.pack(fill='both',expand=True)
    left=ttk.Label(previews,text='Vazio capturado',compound='top');left.pack(side='left',fill='both',expand=True)
    right=ttk.Label(previews,text='Presente — vídeo atual',compound='top');right.pack(side='right',fill='both',expand=True)
    note=tk.StringVar(value='Referências são locais. O sistema recusará mudanças fortes de cena ou pouca diferença visual.')
    ttk.Label(frame,textvariable=note,wraplength=620).pack(anchor='w',pady=8)
    def thumbnail(result):
        a,b,c,d=roi_pixels(roi,result.original.shape)
        crop=result.original[b:d,a:c]
        rgb=cv2.cvtColor(crop,cv2.COLOR_BGR2RGB)
        image=Image.fromarray(rgb);image.thumbnail((260,220))
        return ImageTk.PhotoImage(image)
    left.image=thumbnail(empty_result);left.configure(image=left.image)
    def update():
        if not dialog.winfo_exists():return
        result=window.controller.analysis.latest() if window.controller.analysis else None
        if result:
            right.image=thumbnail(result);right.configure(image=right.image,text='Presente — vídeo atual')
        else:right.configure(text='Sem quadro atual. Aguarde a câmera.')
        dialog.after(200,update)
    def save():
        if window.busy:return
        try:
            current=window.controller.calibration_frame()
            if not name.get().strip():raise ValueError('Dê um nome ao objeto.')
        except ValueError as exc:messagebox.showwarning('Calibração',str(exc),parent=dialog);return
        label=name.get().strip();cls=options[category.get()]
        def done(_):
            if dialog.winfo_exists():dialog.destroy()
            window.status.set('Objeto cadastrado. A análise inicia uma nova sessão e confirma o estado inicial.')
        window.task(lambda:window.controller.register_object(label,roi,empty_result,current,cls,old.id if old else None),done)
    ttk.Button(frame,text='Capturar presente e salvar objeto',command=save).pack(side='right',pady=5)
    ttk.Button(frame,text='Cancelar',command=dialog.destroy).pack(side='left',pady=5)
    update()
    # Returned controls are also exercised by the native UI test, not a mock dashboard.
    return dialog,{'name':name,'category':category,'save':save}


def settings(window,cid):
    old=window.controller.objects.config(cid)
    dialog=tk.Toplevel(window.root);dialog.title('Monitoramento de objetos');dialog.transient(window.root)
    frame=ttk.Frame(dialog,padding=14);frame.pack()
    enabled=tk.BooleanVar(value=old.enabled);clips=tk.BooleanVar(value=old.clips)
    ttk.Checkbutton(frame,text='Monitorar os objetos cadastrados nesta fonte',variable=enabled).grid(row=0,columnspan=2,sticky='w')
    ttk.Checkbutton(frame,text='Clipes amostrados (6 s antes / até 2 s depois; sem áudio)',variable=clips).grid(row=1,columnspan=2,sticky='w',pady=6)
    fields={}
    for row,(key,label) in enumerate([('present_seconds','Confirmar presença por (s)'),('absent_seconds','Confirmar ausência por (s)'),('unknown_seconds','Avisar alteração inconclusiva após (s)'),('max_gap_seconds','Maior intervalo permitido entre análises (s)')],2):
        ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',padx=(0,16),pady=5)
        fields[key]=tk.StringVar(value=str(getattr(old,key)));ttk.Entry(frame,textvariable=fields[key],width=12).grid(row=row,column=1)
    ttk.Label(frame,text='São exigidas pelo menos 3 observações, além do tempo.\nTempos maiores reduzem eventos rápidos e também atrasam a confirmação.\nAumentar o intervalo não recupera ações que a câmera não viu.',wraplength=560).grid(row=6,columnspan=2,sticky='w',pady=10)
    def save():
        try:cfg=InteractionConfig.model_validate({**old.model_dump(),'enabled':enabled.get(),'clips':clips.get(),**{k:float(v.get()) for k,v in fields.items()}})
        except ValueError:messagebox.showwarning('Valores','Confira os limites: presença 0,5–10 s; ausência 0,8–15 s; inconclusivo 1–20 s; intervalo 0,4–5 s.',parent=dialog);return
        window.task(lambda:window.controller.configure_interactions(cid,cfg),lambda _:dialog.destroy())
    ttk.Button(frame,text='Salvar e reaplicar',command=save).grid(row=7,column=1,pady=8)
