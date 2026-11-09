# Testes e limites — Vision Local 4.0.0

Data de execução: 06/11/2026. Base recebida: `Vision_Local_Fase3_v3.0.0.zip`. Este relatório descreve o que foi **executado**, não somente planejado.

## Resultado final

- **233 testes aprovados, 1 ignorado, 0 falhas/erros**, 62.22 segundos. Arquivos `validation/final-tests.txt` e `final-tests.xml`.
- Baseline Fase 3: 163 aprovados, 1 ignorado. A Fase 4 acrescenta 70 casos ao total aprovado e corrige a expectativa de um teste antigo de fila após fechamento.
- Ignorado: `test_real_yolox_execution_when_weights_installed`. Os pesos ONNX não estão presentes neste ambiente; inferência real/precisão YOLOX **não foram executadas**. O download estava indisponível por restrições de rede/DNS. A consulta aos metadados/hash oficial não conta como execução do modelo.
- Checagem de dependências do host: **FAIL** por duas distribuições do namespace cv2, conforme `doctor-final.txt`; instalação limpa **BLOCKED** por indisponibilidade dos pacotes na rede do ambiente. Isto é separado dos testes do código e não foi contabilizado como sucesso.
- Janela Tk nativa exercitada: **PASS**, 15.19 s, sem exceções registradas. `native-gui.json/txt` e screenshots `fase4-*.png`.
- Ensaio de oito objetos: **PASS**, 300.52 s, uma interrupção forçada do processo de análise e recuperação. `soak-300s.json/txt`.
- Novo diretório com espaços: 233 aprovados, 1 ignorado, 0 falhas, 62.73 s; fresh-path-tests.txt/xml.

## Ambiente

Python 3.13.5 (main, Jul 15 2026, 20:25:40) [GCC 14.2.0]; `Linux-6.18.57-x86_64-with-glibc2.41`; OpenCV 4.13.0. Dependências completas em `validation/environment.json`. Sem GPU/CUDA. Xvfb fornece display para Tk; não é Windows. **Importante:** o `cv2` efetivamente carregado era da distribuição `opencv-python 4.13.0.92` (Qt5); o host também tinha metadados de `opencv-python-headless`, e a ferramenta doctor corretamente recusou essa mistura. O alvo do pacote continua sendo somente `opencv-python-headless` numa `.venv` nova. A tentativa de instalação limpa não obteve as wheels neste ambiente (`isolated-install.txt`), portanto a variante headless exata/instalação do requirements **não foi validada**. Não foram alteradas dependências do usuário nem removidos pacotes globais para mascarar a falha. O uso de arquivos e vídeo gerados evita tratar dados inventados como imagens de câmera real.

## Cobertura nova

Revisões transacionais e encadeamento local, preservação do evento original, paginação estável e filtros, legado da Fase 3, detecção de alterações na cadeia; leitura/verificação/retencão/preservação de evidências; exportação sem sobrescrever; arquivos ZIP com traversal, nomes reservados, links/colisões/manifestos divergentes; backup consistente do SQLite e restauração em destino vazio; integridade/rollback e preservação da origem; amostras, duplicação, limites, revisões concorrentes, rascunhos/negativos, grupos sem sobreposição e formatos COCO/YOLO; avaliação de caixas/matching, denominadores sem dados, conjunto sem anotação, caminhos inválidos, calibração recusada no teste; gate por classe e falta de exemplos; percentis limitados, cadenciamento, jobs separados, falhas/timeout/cancelamento; rejeição de logs após encerrar o writer.

Os testes de avaliação usam detector controlado para verificar **a aritmética e os limites**, não resultados neurais reais. Os testes de decodificação YOLOX usam tensores construídos para verificar contrato/coordenação, não imagens reais inferidas. Os ensaios HOG executam o HOG real, que não substitui YOLOX.

Na primeira regressão, um teste antigo esperava que o banco aceitasse eventos depois de fechar seu trabalhador; isso produziria confirmação de fila sem persistência. O código agora recusa, há um teste dedicado, e o teste de fila foi corrigido para pausar um trabalhador vivo. `full-tests.txt/xml` registram esse resultado intermediário, **já resolvido**; o resultado válido final é `final-tests.*`.

## Fluxo visual executado

A ferramenta `tools/validate_phase4_gui.py` criou vídeo AVI de padrões (não pessoas), abriu captura/engine de referências de produção, mostrou estado, validou controles em 1100×760 e 800×560, abriu histórico e antes/depois, salvou revisão e observação, preservou evidência, exportou ocorrência, capturou amostra, desenhou caixa por eventos de mouse Tk, confirmou anotação, exportou dataset, parou câmera, fez backup e restaurou em nova pasta. Reabriu revisão, imagem preservada e anotação no destino.

Os screenshots mostram a interface **real sobre dados gerados**, não uma demo YOLOX reconhecendo objetos reais. A categoria garrafa desenhada sobre um padrão é somente teste da ferramenta de anotação; esse conjunto de uma imagem não foi usado para declarar precisão/treinar modelo. ZIPs `gui-*` são artefatos sintéticos desse ensaio, não dados do usuário.

Heartbeat do teste de UI: p95 44.57 ms; maior intervalo 2046.72 ms. Inclui exportações/verificações síncronas feitas **pelo próprio script de teste**, além do aplicativo. Não é garantia de latência máxima nem medição isolada da thread visual em operação humana.

## Ensaio contínuo de 300 segundos

Fonte: AVI gerado; OpenCV decodificando de fato; oito referências de objetos; **engine regions, sem rede neural**. Interrupção do worker no meio do ensaio. A gravação dá loop e cada loop pode abrir uma sessão nova; contagens de presença/ausência do padrão não constituem falsos eventos da câmera real.

| Medição | Resultado observado |
|---|---:|
| Duração | 300.52 s |
| Quadros analisados acumulados | 2825 |
| Reinícios após falha injetada | 1 |
| Maior soma RSS dos processos | 535.93 MiB |
| p95 comparação das oito regiões | 24.93 ms |
| p95 idade interna após decodificação | 219.19 ms |
| Mediana da frequência informada de análise | 9.48 análises/s |
| Registros descartados / erros de escrita | 0 / 0 |
| Evidências gravadas / falhas / descartes | 74 / 0 / 0 |
| Clipes gravados / falhas | 48 / 0 |

A soma RSS pode contar páginas compartilhadas mais de uma vez. O ensaio ocorreu no ambiente do assistente, com outras validações em parte do intervalo. Não é um benchmark de hardware do usuário nem comparação controlada com a versão anterior. Cinco minutos são ensaio de integração, **não validação de dias/semanas**. A idade interna não inclui atraso prévio do sensor/DVR/decoder. Há descarte deliberado de quadros intermediários por projeto; zero perda de logs não significa que todos os quadros de vídeo foram analisados.

## O que não foi validado

Execução de `INICIAR.ps1`/DPAPI/driver Windows, webcam/RTSP/DVR físico, RTX/CUDA, desempenho do modelo neural, precision/recall real, comportamento com operadores reais, múltiplos dias contínuos, garantias diante de qualquer falta de energia/corrupção de disco. O wrapper PowerShell e a integração foram fornecidos, não certificados. O modelo não está no ZIP nem houve treinamento com dados pessoais.

O gate de detecção faz uma checagem preliminar em dados anotados; não aprova rastreamento ou autoria e não constitui certificação. Assinatura digital, ancoragem externa da auditoria, autenticação/RBAC, criptografia de fotos/banco/ZIP e treinamento customizado não estão implementados. Modelos externos não são automaticamente compatíveis com o adapter oficial de hash fixo.

## Reproduzir

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INICIAR.ps1 -Test
.\.venv\Scripts\python.exe .\tools\verify_release.py
.\.venv\Scripts\python.exe .\tools\soak_phase3.py --seconds 300 --output .\data\reports\soak.json
```

O nome `soak_phase3.py` foi mantido por compatibilidade; ele importa os componentes da Fase 4 presentes na pasta. Este ensaio é sintético, não mede YOLOX. A execução nativa GUI exige display e bibliotecas de teste: `python tools/validate_phase4_gui.py --output <pasta-vazia>`. O teste usa importações em `tests` para construir padrões controlados; não deve ser confundido com operação da câmera real.

## Integridade da distribuição

`MANIFEST.sha256.json` identifica cada arquivo distribuído; `tools/verify_release.py` confere. Isso detecta alteração acidental mas **não autentica o autor**. Bibliotecas/runtime/modelo são obtidos na preparação, não fazem parte do hash deste código-fonte. O ZIP final é conferido após extração. Os artefatos de validação descritos estão incluídos nesta distribuição.
