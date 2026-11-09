# Vision Local — Fase 3 · v3.0.0

**Janela simples de câmera, objetos cadastrados, alterações temporais e evidências locais.** Sem dashboard, navegador, servidor web obrigatório, nuvem, chave de API ou reconhecimento facial.

Esta entrega inclui as bases das Fases 1 e 2. Não é necessário executar os pacotes anteriores. É **código-fonte + inicializador Windows**, não um EXE pré-compilado.

A Fase 3 monitora **até 8 objetos/locais cadastrados em uma câmera fixa**, com referências do local vazio e ocupado. Não identifica automaticamente qualquer peça da sala nem comprova quem retirou um item. A associação a uma pessoa é **provável**, só quando várias condições adicionais são observadas.

## Começar no Windows

1. Extraia o ZIP inteiro numa **pasta nova**, fora da pasta da versão anterior.
2. Abra `INICIAR.cmd`. A primeira preparação precisa de internet para instalar dependências fixadas e obter/verificar o modelo YOLOX-S. Não executa de dentro do ZIP.
3. Selecione **Webcam 0 → Iniciar**. Use **Fonte...** para webcam USB, RTSP/DVR, HTTP/MJPEG ou arquivo.
4. Clique em **Objetos... → Novo** e siga o cadastro abaixo.

Windows 10/11 x64 é o alvo. O inicializador procura CPython x64 3.11–3.14 com Tk; quando necessário, tenta instalar um Python oficial privado em `.runtime`, com hash e assinatura verificados, sem alterar o PATH global. **Windows, driver de webcam, GPU e RTSP físico não foram executados neste ambiente de validação.**

### Alternativa sem baixar o modelo neural

`OBJETOS_SEM_MODELO.cmd` abre o **modo de referências locais**, com a webcam selecionada. Também exige a instalação inicial das bibliotecas, mas não baixa os pesos YOLOX. Depois da instalação, funciona offline com webcam/arquivo.

Esse modo monitora somente os locais que você cadastrar. **Não detecta pessoas e nunca atribui uma retirada a alguém.** Uma pessoa grande atravessando a cena pode suspender a comparação por alteração do fundo. Não é um substituto equivalente ao modo completo.

O modo escolhido fica salvo. Para voltar à análise de pessoas, pare a câmera, abra **Análise...**, selecione **YOLOX — pessoas e objetos** e inicie novamente com o modelo preparado. HOG continua disponível apenas como diagnóstico de pedestres; não é fallback silencioso.

## Cadastrar um objeto — duas referências

**A câmera precisa ficar imóvel.** Escolha um local onde o objeto e a superfície vazia sejam distinguíveis.

1. Retire o objeto e afaste as mãos/pessoas da região. Clique **Objetos... → Novo**.
2. Arraste um retângulo pequeno sobre o **local vazio**. Mantenha a mesma posição da câmera, foco e iluminação.
3. Na janela aberta, dê um nome, por exemplo `Notebook da mesa` ou `Caixa de ferramentas`. A categoria COCO é opcional: ela restringe a associação de movimento, não cria uma nova classe neural.
4. Coloque o objeto nesse local e afaste-se. A janela mostra o recorte vazio capturado e o recorte atual. Clique **Capturar presente e salvar objeto**.
5. O aplicativo verifica as referências, salva o cadastro e reinicia a sessão. Aguarde o estado inicial aparecer sobre o vídeo.

O cadastro recusa áreas menores que **24 × 24 pixels reais**, áreas maiores que 35% do quadro, sobreposição importante com outro cadastro, mudanças de cena entre as referências e referências visualmente semelhantes demais. Esses limites são proteções de entrada, **não uma garantia de precisão a partir de 24 pixels**.

Cada cadastro representa um **objeto/aparência num local fixo**. Uma mudança de ângulo, superfície, foco, posição do objeto ou iluminação pode exigir **Recalibrar**. Não amplie a região para cobrir a sala inteira. Em **Objetos...**, também é possível ativar/pausar, excluir ou ajustar os tempos e os clipes. Excluir cadastro não apaga as evidências anteriores.

### Teste inicial recomendado

Com apenas um objeto cadastrado, confirme `PRESENTE`, retire-o, deixe o local desobstruído e aguarde a confirmação. Recoloque-o e aguarde `RETORNO_OBSERVADO`. Depois cubra a região sem retirar o objeto: o sistema deve ficar ocluído/inconclusivo ou suspenso, em vez de atribuir uma retirada. Faça o teste na imagem real, com diferentes distâncias e iluminação.

## O que os registros significam

| Registro | Significado implementado |
|---|---|
| `OBJETO_PRESENTE_INICIAL` | A aparência ocupada foi confirmada no início da sessão; não é uma devolução inferida. |
| `OBJETO_AUSENTE_INICIAL` | A região estava vazia no início. Não houve retirada observada nesta sessão. |
| `INTERACAO_POSSIVEL` | Pessoa permaneceu próxima; não comprova toque, posse ou autoria. |
| `OBJETO_OCULTO` | Pessoa ou objeto grande detectado cobre a região. A confirmação de ausência é interrompida. |
| `AUSENCIA_CONFIRMADA` | A região passou de presente para correspondência persistente com o vazio; autoria não atribuída. |
| `RETIRADA_PROVAVEL` | Ausência mais vínculo visual/temporal do objeto e movimento conjunto com uma única pessoa. Exige revisão. |
| `RETORNO_OBSERVADO` | A aparência cadastrada voltou ao local. Não comprova ser a mesma unidade física nem quem a devolveu. |
| `ALTERACAO_INCONCLUSIVA` | A região não corresponde suficientemente a nenhuma das duas referências. |
| `MONITORAMENTO_SUSPENSO` | Cena/câmera/luz/resolução/visibilidade inadequadas. Não conclui retirada. |
| `MONITORAMENTO_RETOMADO` | Condições recuperadas ou lacuna observada; confirma novo estado inicial, sem inferir ações na interrupção. |
| `REVISAO_EVENTO` | Parecer do operador acrescentado ao histórico, sem alterar o evento original. |

**“Retirada provável” nunca é produzida apenas porque alguém estava perto.** É necessário vincular uma trajetória do objeto na posição inicial, manter esse ID fora do local, verificar aparência, contato geométrico recente, movimento conjunto medido em pelo menos três observações e ausência de ambiguidade entre pessoas. Mudança de ID, objeto não detectado pelo modelo, duas pessoas ou evidência insuficiente levam à abstenção de autoria. Não há rastreamento de mãos, biometria nem conclusão de furto.

Padrões: presença por **1 s**, ausência por **1,5 s**, pelo menos **3 observações** e intervalo máximo entre análises de **1,5 s**. O tempo de confirmação depende da frequência real; não é prazo garantido. Uma lacuna maior reinicia a confirmação e o estado inicial, em vez de deduzir o que aconteceu fora de vista.

## Fotos, clipes e revisão

**Registros** abre uma lista simples. Dê dois cliques no evento para consultar as medidas, os IDs temporários e **Abrir evidência**. Eventos importantes permitem marcar **Confirmar observação**, **Falso positivo** ou **Inconclusivo**. Essa revisão é uma opinião do operador local, sem autenticação pessoal; não transforma o evento em prova de autoria.

Os grupos em `data/evidence/e_<id>/` contêm:

- `quadro.jpg` e `anotado.jpg`: o mesmo quadro analisado, sem/com marcações.
- `antes_o_<id>.jpg`: última imagem válida do estado anterior, quando disponível, com seu próprio horário/seqüência em `evento.json`. Não é apresentada como imagem simultânea ao evento.
- `evento.json`: estados, medidas, contexto da sessão e SHA-256 das imagens.
- `clip.avi` + `clip.json`, quando a gravação é possível: vídeo **amostrado**, até 6 s antes e 2 s depois da confirmação, a até 3 amostras/s, teto de 640 × 360, sem áudio. O JSON lista o horário real de cada amostra, hash e completude da cauda.

Os clipes não são gravação contínua nem arquivos originais do sensor. Lacunas podem ser comprimidas pela reprodução em FPS fixo. Um evento ocorrido pouco depois de iniciar pode ter menos pré-histórico; encerramento/falha pode gerar uma cauda parcial. Fotos são confirmadas por `EVIDENCIA_SALVA`; clipes por `CLIPE_SALVO`. Falhas e descartes são registrados separadamente.

Retenção das evidências: padrão **512 MiB ou 1.000 grupos**, removendo os mais antigos. Até três clipes pendentes ficam temporariamente protegidos da limpeza; a limpeza é reaplicada na próxima gravação de evidência ou ao encerrar. Registros SQLite: até 50.000 eventos e 100.000 amostras. **Guarde externamente arquivos importantes**; armazenamento é finito. Hashes verificam integridade, não autoria/autenticidade jurídica.

## Desempenho e sincronização

Captura isolada → último quadro → uma inferência pendente → rastreamento e comparação local → janela. As caixas/estados correspondem ao **mesmo quadro analisado**. Sem fila crescente de imagens antigas. A comparação usa recortes reduzidos e referências fixas, sem reajustar automaticamente o vazio depois de uma retirada.

JPEG, AVI e SQLite são gravados fora do thread da interface. Há filas limitadas, limite de objetos, ring buffer de clipes limitado por tempo/bytes e reinício de processos travados. Resultados de sessões antigas são rejeitados. Laços de arquivos, reconexões, novas fontes e mudanças de resolução não preservam suposta identidade de pessoas.

Esta versão usa **CPU**. Não ativa a RTX/CUDA automaticamente. Os números de ensaio em `docs/TESTES_E_LIMITES.md` são de vídeo gerado e modo de referências, não uma previsão de YOLOX nem do seu notebook. A idade do quadro é medida após o decoder; atrasos internos do DVR/câmera podem existir antes desse ponto.

## Aproveitar os dados da Fase 2

Use a instalação nova. Não sobrescreva a pasta anterior nem copie a `.venv`.

Com ambos os programas fechados, prepare só o ambiente e importe os dados. O modo `-Objetos` evita baixar pesos durante essa preparação opcional:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INICIAR.ps1 -InstallOnly -Objetos
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\MIGRAR_DADOS.ps1 -Origem "C:\caminho\vision-detection-antigo"
```

O importador exige destino sem cadastros/banco/evidências existentes, trava origem/destino, usa a API de backup do SQLite e preserva a origem. Não copia ambientes nem pesos. Uma falha não autoriza sobrescrever dados existentes. Os pesos verificados podem ser copiados separadamente para `models`, ou baixados ao abrir `INICIAR.cmd`.

As credenciais protegidas por DPAPI precisam da conta/computador compatíveis. Banco, imagens, clipes e referências **não são criptografados pelo aplicativo**. A pasta precisa de permissões adequadas. Diagnóstico não inclui imagens ou URL completa da câmera, mas contém nomes dos objetos, horários e IDs; revise antes de compartilhar.

## Validar e diagnosticar

```powershell
# Testes locais (observe skips e os limites do relatório):
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INICIAR.ps1 -Test

# Verificar o modelo já baixado, sem download:
.\.venv\Scripts\python.exe .\tools\prepare_model.py --offline

# Diagnóstico de bibliotecas:
.\.venv\Scripts\python.exe .\tools\doctor.py
```

Para medir eventos reais, leia **`docs/FASE3_AVALIACAO.md`**. Ferramentas de avaliação calculam métricas a partir de rótulos fornecidos, sem inventar resultados. Nenhuma taxa de acerto na sua câmera foi medida aqui.

### Linux

CPython x64 3.11–3.14 com Tk e sessão gráfica. Instale `requirements.txt` em um ambiente isolado. `python run.py --regions` executa somente referências; `python tools/prepare_model.py` prepara YOLOX; `python run.py` reutiliza a configuração salva. Não há homologação de macOS.

## Arquivos principais

`vision_app/object_registry.py`: cadastro/validação/hash de referências. `interactions.py`: estados, proteção de cena e associação conservadora. `clips.py`: ring buffer/clipes amostrados. `object_ui.py`: cadastro simples e parâmetros. `service.py`: integração sincronizada. `evidence.py`: fotos/antes/depois. `event_evaluation.py`: métricas por evento. `vision_foundation/`: captura e armazenamento da base anterior.

Consulte `docs/FUNCIONAMENTO_FASE3.md`, `docs/TESTES_E_LIMITES.md`, `docs/REFERENCIAS.md` e `THIRD_PARTY_NOTICES.md`. Documentação e testes históricos da Fase 2 estão identificados em `docs/history/`, não são apresentados como homologação desta versão.
