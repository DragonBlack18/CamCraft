# Vision Local — Fase 2 · v2.0.0

Aplicativo de câmera com **janela nativa simples**, detecção local de pessoas/objetos, IDs temporários, confirmação temporal, cruzamento de linha e registros com evidências. Não há dashboard, servidor HTTP, navegador obrigatório, API de IA, conta ou telemetria.

**Entrega: código-fonte + inicializador Windows. Não é um EXE pré-compilado.** A captura da Fase 1 foi reaproveitada; não é necessário instalar nem executar o pacote antigo. Extraia em uma pasta nova, sem sobrescrever sua instalação anterior.

## Começar no Windows

1. Extraia o ZIP inteiro. Abra a pasta `vision-detection` e execute **`INICIAR.cmd`**. Não execute de dentro do ZIP.
2. A primeira preparação precisa de internet: cria `.venv`, instala as versões fixadas, baixa o modelo oficial YOLOX-S (~35,9 MB), verifica tamanho/SHA-256 e executa uma inferência de teste antes de abrir a janela. Não há chaves de API.
3. Selecione **Webcam 0 → Iniciar**. Feche outros aplicativos que estejam usando a câmera. Deixe uma pessoa ou objeto compatível visível por alguns instantes.

Se não houver CPython compatível com Tk, o inicializador tenta uma instalação oficial privada na pasta `.runtime`, sem alterar o PATH. Windows 10/11 x64 é o alvo; Windows físico e o bootstrap PowerShell **não foram executados neste ambiente de desenvolvimento**.

**Validação aqui:** testes automatizados e janela nativa executados em Linux. O modelo YOLOX não pôde ser baixado neste ambiente; inferência neural e precisão real permanecem pendentes. Consulte `docs/TESTES_E_LIMITES.md` antes de interpretar a entrega como homologada.

Depois da preparação, o processamento é local. Um stream RTSP/HTTP depende da rede da câmera; o aplicativo não envia imagens a serviços externos.

### Trocar a câmera

Pare a câmera antes de editar. Use **Fonte...** para ajustar o perfil selecionado ou **Configurações → Nova fonte** para adicionar um perfil. Até quatro perfis salvos, **um ativo por vez** nesta interface.

| Fonte | Campo de origem |
|---|---|
| Webcam / USB | Índice `0`, `1`, `2` etc. |
| RTSP / DVR | URL RTSP fornecida pelo equipamento, com canal/stream corretos. |
| HTTP / MJPEG | URL de vídeo, não página HTML de configuração da câmera. |
| Arquivo de vídeo | Escolha um arquivo local compatível com o decoder. |
| Teste de captura | Padrão sintético em movimento; não contém pessoas e não simula detecções. |

Resolução e FPS do formulário são pedidos ao driver da webcam, não garantias. No RTSP, configure o stream principal no DVR. Câmeras com SDK proprietário ou protocolos não suportados precisam de adaptador. O programa não promete compatibilidade com qualquer câmera.

## O que aparece na janela

**Fonte, Iniciar, Parar, Foto e Registros** são os controles principais. O vídeo mostra categoria, score e ID local. Caixas cinzas são candidatas; verdes passaram pela confirmação temporal. O score não é probabilidade calibrada de acerto.

A linha inferior mostra estado, frequência real de análise e idade do quadro após decodificação. Quando não há resultado atual, o vídeo antigo é retirado em vez de continuar parecendo ao vivo. Em **Arquivo**, exporte CSV/diagnóstico ou abra a pasta de evidências.

### Área e linha pelo mouse

**Área:** com o vídeo ativo, clique em Área e arraste um retângulo. A tela congela somente para selecionar; a captura continua. A área é usada como recorte antes da inferência, sem deformar a proporção. Ela pode concentrar os pixels relevantes, mas não recria detalhes ausentes. `Esc` cancela.

**Linha:** clique em Linha e arraste de A para B. A seta perpendicular indica o sentido configurado como entrada. A inversão fica em **Análise...** com a câmera parada. A passagem considera o ponto inferior central da caixa da pessoa, cruza o segmento desenhado e exige estabilidade temporal. Não é necessário reconhecimento facial.

Salvar área/linha reinicia a análise com uma nova sessão de IDs. Não conte a primeira aparição dentro da sala como entrada pela porta. A configuração deve ser adequada ao ângulo da câmera e validada com travessias reais. Movimentos rápidos, oclusões e baixa frequência de análise podem causar perdas.

### Configurar a análise

Padrão: **YOLOX-S**, todas as classes, limiar `0,45`, até `10` análises/s e `2` threads de CPU. O limite de análises/s não é uma promessa de desempenho.

Escolha somente pessoas ou o subconjunto de ambiente interno para reduzir registros desnecessários; isso filtra os resultados, **não reduz proporcionalmente o custo da rede neural**. Alterar a quantidade de threads precisa de medição no computador. Não baixe o limiar indiscriminadamente: isso pode aumentar falsos positivos.

Esta versão usa **OpenCV DNN em CPU**. Não usa automaticamente a RTX, CUDA, DirectML, TensorRT ou ONNX Runtime. Não há dependência de Torch/Ultralytics no runtime.

## Escopo real da detecção

O modelo treinado no COCO possui **80 categorias**, incluindo pessoa, mochila, garrafa, copo, cadeira, notebook, mouse, teclado, celular e livro. Lista completa em `docs/CATEGORIAS.md`. Não é um detector universal: caixas genéricas, peças industriais ou ferramentas específicas não são automaticamente classes do modelo.

O rastreador é uma implementação independente, com filtro de Kalman, atribuição parcial húngara e duas passagens de associação por confiança, inspirada no princípio do ByteTrack. **Não é a biblioteca oficial ByteTrack**, nem reconhecimento de identidade. IDs valem apenas para a câmera e a sessão corrente; podem mudar por oclusões, reconexão, cruzamento de pessoas ou reinício.

| Evento | Significado |
|---|---|
| `PESSOA_OBSERVADA` | Pessoa confirmada em observações temporais. |
| `OBJETO_OBSERVADO` | Categoria do modelo confirmada em observações temporais. |
| `ENTRADA_LINHA` / `SAIDA_LINHA` | Cruzamento observado na direção configurada. |
| `RASTREAMENTO_PERDIDO` | Trajetória deixou de ser acompanhada; não comprova saída, retirada ou furto. |
| `EVIDENCIA_SALVA` | Arquivos foram gravados; o evento anterior apenas solicitava a gravação. |

**Não implementado nesta fase:** atribuir retirada/devolução de objeto a uma pessoa, identificar rostos/nomes, reidentificação entre câmeras, treinar classes novas, detectar mãos/gestos, gravar áudio, gravação contínua ou clipes automáticos de ações. A biblioteca de clipes da Fase 1 permanece no código reaproveitado, mas não é uma função exposta nesta janela.

## Sincronização e limites de recursos

Captura em processo separado → último quadro em memória limitada → uma inferência pendente em outro processo → rastreamento/eventos → último quadro anotado → janela.

As caixas são desenhadas **sobre o mesmo quadro que gerou a inferência**. Quando a análise demora, quadros intermediários são pulados; não há uma fila crescente de imagens antigas. Fotos e SQLite usam trabalhadores separados com filas limitadas. JPEG de prévia é desativado no caminho desktop; evidências JPEG são codificadas apenas quando solicitadas.

O supervisor reinicia trabalhadores que pararam de responder, substituindo também buffers e locks compartilhados. Depois de falhas repetidas, mostra erro em vez de reiniciar indefinidamente. Resultados antigos ou de outra geração da câmera são descartados. Uma mudança de fonte/resolução ou repetição de arquivo inicia nova sessão.

O timestamp é medido **após o decoder**, não na exposição do sensor. Atrasos do DVR, rede e buffers do driver podem existir antes desse ponto. Para medir câmera→tela, filme um relógio/contador na cena e compare-o com o vídeo mostrado.

A imagem de trabalho tem teto padrão de 1920×1080; fontes maiores são reduzidas. A entrada do modelo é 640×640 com preenchimento, mantendo a proporção. O teto de detecções é 100 e há limite de trajetórias. Esta entrega não promete cobertura de multidões nem precisão industrial sem validação.

## Registros, evidências e privacidade

Tudo fica dentro de `data/`. Banco: `events.sqlite3`, com WAL. Configuração de captura: `cameras.json`; análise: `analysis.json`. Evidências: `data/evidence/e_<id>/`.

Cada grupo contém `quadro.jpg` sem caixas, `anotado.jpg` com marcações e `evento.json` com sessão, horário do quadro, parâmetros, eventos e SHA-256 das imagens. `quadro.jpg` é o frame decodificado recodificado em JPEG, não o sinal original do sensor. Hash de integridade não autentica quem gerou a evidência.

Retenção padrão: **512 MiB ou 1.000 grupos** de imagens, removendo os mais antigos. Banco retém até 50.000 eventos e 100.000 amostras de métricas. Copie externamente arquivos importantes. Falta de espaço, falha de escrita e fila cheia aparecem nos registros/estado; nenhuma solução com armazenamento finito garante retenção ilimitada.

A URL da fonte é protegida com DPAPI no Windows pela base reaproveitada; em outros sistemas usa restrição de arquivo, não criptografia equivalente. **Banco e imagens não são criptografados pelo aplicativo.** A pasta precisa de permissões adequadas. O diagnóstico não inclui fotos nem a URL completa/credenciais, mas contém horários, categorias, nomes de perfis e IDs; revise antes de compartilhar.

Não há API pública de rede. Conexões externas: instalação de pacotes/modelo e acesso à câmera configurada. Não exponha credenciais de DVR em mensagens, screenshots ou repositórios.

## Diagnóstico e testes

Sem baixar o modelo, `DIAGNOSTICO_SEM_MODELO.cmd` abre fonte sintética + HOG. **HOG é um diagnóstico explícito de pedestres, não um substituto equivalente do YOLOX nem detector de objetos.** O sintético não contém pessoas. O botão não comprova precisão; inclusive foram observados falsos positivos do HOG no texto da fonte sintética durante os ensaios.

```powershell
# Dentro da pasta extraída:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INICIAR.ps1 -Test

# Após a instalação, validar a inferência neural local, sem novo download:
.\.venv\Scripts\python.exe .\tools\prepare_model.py --offline

# Procurar webcams 0 a 3, isolando cada tentativa:
.\.venv\Scripts\python.exe .\tools\probe_webcams.py --max-index 3

# Reabrir offline após dependências e modelo preparados:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INICIAR.ps1 -Offline
```

`-Test` pode indicar um teste ignorado se o modelo ainda não existir. Isso **não** significa que o YOLOX foi homologado. O resultado real de execução do modelo fica em `data/reports/model-smoke.json`; esse teste usa imagem neutra e não mede acurácia.

`-Repair` reinstala as dependências na `.venv`, sem apagar dados. `-PythonPath "C:\...\python.exe"` permite uma instalação existente. Não desative antivírus/firewall para contornar restrições corporativas. Em erro de DLL, veja a documentação oficial do pacote OpenCV e os pré-requisitos do Windows, preservando o log.

Para medir detecção em imagens da sua câmera, há `tools/evaluate_images.py` e o contrato de anotações em `docs/AVALIACAO_REAL.md`. Ele calcula precisão/recall/F1 num limiar fixo, **não inventa resultados sem imagens rotuladas**.

### Linux

CPython x64 3.11–3.14 com Tk instalado. `bash start.sh` prepara o ambiente/modelo e abre a janela; o script Linux usa pip e precisa de acesso aos pacotes na preparação. Depois, `.venv/bin/python run.py` reutiliza tudo offline. Sem display, use `--headless` e uma fonte configurada, ou `--demo --hog --headless --seconds 30` para diagnóstico. Não há homologação de macOS nesta entrega.

## Estrutura

- `vision_foundation/`: captura/IPC/supervisor/SQLite reaproveitados, sem servidor web no pacote.
- `vision_app/`: detector, rastreamento, eventos, inferência isolada, evidências, janela e avaliação.
- `tools/`: preparação verificada do modelo, diagnóstico, avaliação e ensaio da interface.
- `tests/`: regressão da captura e testes novos da análise, sincronização, falhas e registros.
- `docs/validation/`: resultados reais dos testes, screenshots nativos e relatório de ensaio HOG.
- `models/`: manifesto do modelo; os pesos são obtidos na primeira preparação.

Referências técnicas e distinção entre reutilização e implementação própria em `docs/REFERENCIAS.md`. Avisos de licença em `THIRD_PARTY_NOTICES.md`.
