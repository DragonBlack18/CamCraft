"""Offline evaluation UI with a cancellable isolated child; no automatic model changes."""
from pathlib import Path
import json
from .runtime import tool_command
import time
import tkinter as tk
from tkinter import ttk,messagebox,filedialog


def evaluate_dialog(owner):
    if owner.busy:return
    if owner.controller.camera:
        messagebox.showinfo('Avaliação','Pare a câmera. A avaliação usa um processo separado e não compete com o monitoramento.');return
    manifest=filedialog.askopenfilename(title='Manifesto anotado extraído do ZIP: test.json / val.json / evaluation.json',filetypes=[('Manifesto','*.json')])
    if not manifest:return
    output=filedialog.asksaveasfilename(title='Novo relatório de avaliação',defaultextension='.json',initialfile='avaliacao-'+time.strftime('%Y%m%d-%H%M%S')+'.json',filetypes=[('JSON','*.json')])
    if not output:return
    if Path(output).exists():messagebox.showerror('Relatório','Escolha um nome que ainda não existe.');return
    dlg=tk.Toplevel(owner.root);dlg.title('Avaliação local — processo isolado');dlg.geometry('620x280');dlg.transient(owner.root)
    text=tk.StringVar(value='Executa o YOLOX oficial nas imagens anotadas. Não treina nem troca parâmetros automaticamente.\nAprovação exige conjunto test e quantidade mínima de exemplos.')
    ttk.Label(dlg,textvariable=text,padding=14,wraplength=580).pack(fill='x')
    confidence=tk.StringVar(value='0.45');sweep=tk.BooleanVar(value=False)
    form=ttk.Frame(dlg,padding=8);form.pack(fill='x')
    ttk.Label(form,text='Limiar fixo').pack(side='left');ttk.Entry(form,textvariable=confidence,width=10).pack(side='left',padx=8)
    ttk.Checkbutton(form,text='Comparar limiares (somente val.json)',variable=sweep).pack(side='left')
    running=[False]
    def cancel():
        if running[0]:
            owner.controller.jobs.cancel.set();text.set('Cancelamento solicitado; o processo será encerrado.')
        else:dlg.destroy()
    def start():
        if running[0] or owner.busy:return
        try:
            c=float(confidence.get())
            if not .25<=c<=.9:raise ValueError()
        except ValueError:messagebox.showerror('Limiar','Use 0,25 a 0,90, com ponto decimal.',parent=dlg);return
        command=tool_command('validate-dataset','--manifest',manifest,'--output',output,'--model-dir',owner.controller.model_dir,'--confidence',str(c))
        if sweep.get():command+=['--sweep']
        log=owner.controller.directory/'reports'/('avaliacao-'+time.strftime('%Y%m%d-%H%M%S')+'.log')
        running[0]=True;text.set('Avaliação em execução. Cancelar encerra o processo; a interface continua disponível.');button.configure(state='disabled')
        def run():
            try:
                owner.controller.jobs.run(command,log)
                return {'ok':True}
            except Exception as exc:
                return {'ok':False,'error':str(exc)}
            finally:running[0]=False
        def complete(result):
            if not dlg.winfo_exists():return
            if not result['ok']:
                button.configure(state='normal')
                text.set('Avaliação não concluída: '+result['error']+'\nNenhuma aprovação foi registrada.')
                return
            report=json.loads(Path(output).read_text(encoding='utf-8'))
            text.set('Relatório salvo. Resultado do critério de aceitação: '+report['acceptance']['decision']+'\nO relatório distingue erros, acertos e falta de dados; não certifica retiradas/autoria.')
        owner.task(run,complete)
    buttons=ttk.Frame(dlg,padding=8);buttons.pack(fill='x')
    button=ttk.Button(buttons,text='Executar avaliação',command=start);button.pack(side='left',padx=4)
    ttk.Button(buttons,text='Cancelar / fechar',command=cancel).pack(side='left',padx=4)
    dlg.protocol('WM_DELETE_WINDOW',cancel)
