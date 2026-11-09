# Validação efetivamente executada — Vision Local 2.0.0

Data: **06/11/2026**. Ambiente Linux x64, CPython 3.13.5. Este relatório diferencia teste de software, integração e acurácia visual. Não é uma certificação de produção.

## Resultado da suíte

**114 testes aprovados, 1 ignorado, 0 falhas, 0 erros**, em 35,37 segundos na execução final. Arquivos reais: `validation/all-tests.txt` e `validation/all-tests.xml`.

O teste ignorado foi explicitamente o de **inferência real YOLOX**, porque o peso não estava disponível e a rede deste ambiente não permitiu seu download. Não existe, nesta entrega, resultado medido de precisão/recall para YOLOX ou para a câmera do usuário. Não foi usado um detector fictício como substituto silencioso do modelo real.

A suíte cobre:

| Área | O que foi exercitado |
|---|---|
| Captura reaproveitada | Fonte sintética, arquivo real codificado, HTTP/MJPEG local, reconexão, timeout, trabalhador interrompido, troca de locks e buffers. |
| Pré/pós-processamento neural | RGB, escala/padding, grade de saída, coordenadas/ROI, NMS por classe, limiares, saídas inválidas e limites, usando tensores controlados. |
| Download do modelo | Cache, tamanho/hash, arquivo incorreto preservado, falha/retry e modo offline, com transporte simulado. Não comprova acesso real à CDN. |
| Rastreamento | Confirmação temporal, baixa confiança sem criar presença, associação por classe, oclusão curta, expiração, sessões e estado do filtro. |
| Eventos | Observação única, perda distinta de saída, cruzamento do segmento finito, direções, histerese e rejeição de saltos após lacuna. |
| Sincronização | Resultado desenhado sobre o mesmo input, rejeição de geração antiga/quadro vencido, um pedido pendente, watchdog de inferência. |
| Integração da análise | Captura real sintética + processo de análise controlado para verificar coordenação; encerramento forçado e recuperação com nova sessão. As detecções desse teste são explicitamente um test double. |
| HOG | Execução real do detector OpenCV em processo separado. Não é YOLOX nem comprova acurácia em pessoas reais. |
| Evidências | Escrita assíncrona, hashes das imagens, metadados, retenção e falha por pouco espaço. |
| Dados | SQLite, paginação/CSV, proteção contra fórmulas na exportação e omissão de credenciais no diagnóstico. |
| Avaliação | Contagem TP/FP/FN, duplicatas, classe errada, sobreposição, negativos e denominador zero. |

Os relatórios `baseline-tests` e `new-unit-tests` são execuções intermediárias, não testes adicionais para somar aos 114. O relatório `all-tests` é o resultado consolidado final.

## Interface nativa executada

A janela Tk foi realmente aberta em **Xvfb**, um display Linux virtual. Não é mockup ou imagem gerada. O fluxo utilizou **fonte sintética + detector HOG real**, sem pessoas no padrão de teste.

O ensaio concluiu: vídeo atual; foto salva; CSV e ZIP de diagnóstico; layout 1100×760 e 800×560; ROI pelo mouse; linha pelo mouse; reinício após alteração; histórico lido de SQLite; parar/liberar; iniciar novamente. Zero exceções de callback registradas. A última revisão corrigiu corte de botões em 800×560 e passou a verificar também se todos os botões da barra cabem na janela.

Repetição final: **7,42 s**. Intervalo entre chamadas de verificação do loop da interface: **p95 48,1 ms**, máximo **330,2 ms**, incluindo capturas de tela de teste. Isso não é medição de tempo de resposta Windows nem câmera→tela.

Arquivos: `validation/gui-smoke.json`, `gui-smoke.txt`, `janela-desktop.png`, `janela-compacta.png` e `janela-configurada.png`. As imagens não comprovam detecção neural de pessoas/objetos. **Foram observados falsos positivos do HOG no texto do padrão sintético** em uma das repetições; isso reforça que esse modo é somente diagnóstico e que confirmação temporal, sozinha, não transforma uma detecção errada persistente em correta. A inscrição “SEM PESSOAS” e o backend HOG permanecem visíveis de propósito.

## Ensaio de execução contínua — HOG, não YOLOX

Fonte sintética 640×480, CPU, limite de 10 análises/s, duração **60,14 s**, com outras verificações deste trabalho concorrendo no ambiente.

- **477 quadros analisados**, aproximadamente 7,93/s em média ao longo do ensaio (inclui a abertura).
- **0 erros**, **0 reinícios** da análise e **0 descartes por resultado vencido**.
- Idade interna após decodificação: **p95 591,0 ms**.
- Tempo de inferência HOG nas amostras: **p95 213,73 ms**.
- Pico da soma de RSS dos processos: **301,3 MiB**. A soma pode contar páginas compartilhadas mais de uma vez.
- A janela móvel de FPS ao final registrou **5,49/s**, diferente da média global. O ensaio não sustenta promessa de 10 FPS fixos.

Arquivos: `validation/soak-hog-60s.json`, `soak-summary.json` e `soak.txt`. Não extrapolar esses números para YOLOX, RTX, webcam/DVR reais ou funcionamento durante dias. O mecanismo evita fila crescente, mas não elimina o custo de inferência nem o atraso anterior ao decoder.

## Dependências e instalação: limite importante

As bibliotecas disponíveis neste ambiente foram reutilizadas em um venv local de verificação. Não foi possível refazer a instalação limpa pela internet. O `cv2` pré-instalado possui suporte Qt compilado; a aplicação NÃO utiliza `cv2.imshow`, e o pacote entregue solicita somente `opencv-python-headless` no ambiente novo. Portanto, **não foi validada aqui uma instalação limpa do wheel headless nem os wheels Windows**. Versões/método em `validation/environment.json`.

O bootstrap PowerShell e a instalação privada do Python foram implementados, mas **não executados em Windows**. Não há PowerShell/Windows neste ambiente. Não foi realizada assinatura de EXE, build Nuitka ou publicação GitHub.

## O que a primeira execução na sua máquina valida

O inicializador normal baixa o modelo, confere o SHA-256 oficial e executa uma inferência em um quadro neutro. Só abre a aplicação normal depois desse teste. O relatório local fica em `data/reports/model-smoke.json`.

Isso valida carregamento/execução do modelo no computador de destino; **não mede precisão**. O botão `DIAGNOSTICO_SEM_MODELO.cmd` deliberadamente ignora YOLOX e não substitui esse teste.

Para repetir os testes depois de preparar o modelo:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INICIAR.ps1 -Test
```

Com o peso presente, o teste antes ignorado deve executar. Trate erro, falha ou SKIP explícito como tal; não converta tudo em PASS.

## Pendências de homologação

**Pendente:** webcam física, RTSP/DVR real, Windows 10/11, bootstrap/download real, DPAPI nesta nova entrega, YOLOX real, comportamento com várias pessoas/objetos do ambiente, vídeo ruim, latência sensor→tela e ensaio prolongado de memória/estabilidade.

O código da fase de detecção/rastreamento está entregue. A precisão operacional ainda precisa ser medida. Não há garantia de 100%, identificação civil, reidentificação entre câmeras ou atribuição de retirada de objetos. Retenção é finita; evidências podem ser removidas automaticamente e existem modos explícitos de degradação quando disco/filas falham.

## Execução em uma pasta nova

Uma cópia separada do código foi iniciada por 10 segundos em caminho com espaços (`Vision Local clean launch`), com dados novos, fonte sintética e HOG. A execução concluiu com 72 quadros analisados, sem erros de análise. Arquivos `validation/fresh-path.txt` e `fresh-path.json`. Esse teste reutilizou o interpretador/bibliotecas de verificação; não comprova a instalação Windows.
