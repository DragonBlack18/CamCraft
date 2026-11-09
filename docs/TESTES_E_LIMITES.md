# CamCraft 4.2.0 — testes executados e limites

## Release Windows publicada

- Run: https://github.com/DragonBlack18/CamCraft/actions/runs/42661851964
- Código compilado: `283aaaf819d032437e6208f6cb0575cabdbe08a5`.
- Ambiente: GitHub Actions, Windows Server 2022 x64, Python 3.12.10.
- Regressão: **280 aprovados, zero ignorados, zero falhas**, em 78,456 s.
- Dependências instaladas em `.build-venv` limpa; `pip check` aprovado e somente `opencv-python-headless` fornecendo `cv2`.
- Modelo oficial YOLOX-S incluído: hash conferido e inferência neural real executada.
- Auditoria nativa: 187 arquivos PE examinados; nenhum runtime MSVC necessário ausente do pacote; Python, Tk, FFmpeg e modelo presentes.

## Testes dos executáveis

| Verificação | Onedir (base do Setup) | Portátil isolado | EXE instalado |
|---|---|---|---|
| Resultado | PASS | PASS | PASS |
| Python externo fora do PATH | Sim | Sim | Sim |
| Inferência com o modelo real | PASS | PASS | PASS |
| Resultados neurais recentes observados antes da pausa | 16 | 15 | 15 |
| Retomada da IA mantendo o PID da câmera | PASS | PASS | PASS |
| Janela nativa e prévia desenhadas | PASS | PASS | PASS |
| Decoder/encoder MJPG e FFmpeg | PASS | PASS | PASS |
| Foto, SQLite e ferramenta interna empacotada | PASS | PASS | PASS |
| Encerramento e limpeza dos temporários | PASS | PASS | PASS |

O portátil foi copiado sozinho para uma pasta nova com espaços no caminho. Não havia projeto, scripts Python ou modelo externo ao lado dele.

O Setup foi instalado silenciosamente e o aplicativo instalado foi executado. A desinstalação removeu o programa e preservou um arquivo-sentinela na pasta persistente de dados. Todas as verificações do instalador passaram.

Durante a validação foram corrigidos o bloqueio obrigatório de arquivos no Windows, a limpeza de temporários antes do fechamento do banco e uma amostragem pontual incorreta do autoteste. O teste agora exige dois resultados neurais distintos e recentes observados durante a execução, mantendo o descarte de resultados antigos.

## O que não foi validado

- Nenhuma câmera física do usuário foi conectada ao runner.
- Imagens sintéticas/neutras verificam execução, não precisão em pessoas ou objetos reais.
- Não houve treinamento com o quarto do usuário nem medição de acurácia dessa câmera.
- O runner possui Python instalado; os testes retiraram-no do PATH e verificaram a execução congelada. Não equivalem a uma VM doméstica sem qualquer software prévio.
- O autoteste bloqueia chamadas Python de conexão no processo principal; não é um bloqueio de rede de todos os processos pelo firewall. A aplicação empacotada exige o modelo incluído e não o baixa em execução.
- Não houve teste contínuo de dias, homologação de todo driver, CUDA ou assinatura Authenticode.

Os testes de integração duraram aproximadamente 21–25 segundos cada, com fonte sintética 640×480. Não apresentam uma promessa de FPS ou atraso na câmera do usuário. A inferência permanece em CPU.

## Evidências reproduzíveis

Release: https://github.com/DragonBlack18/CamCraft/releases/tag/v4.2.0

`CamCraft-4.2.0-validation.zip` contém XML da regressão, inventário de dependências, auditoria nativa e relatórios JSON dos três modos e do instalador, além dos logs do Setup.

SHA-256 do ZIP de validação:
`752ca871015f26e024d196a5880ddd3a92f2dd18213648e1ad73d931c66e49d7`.

Portátil: `6b2fa76ec5f63e5b18cc29a7ec885a671be74ba5913f1694fc36e6cccd73acc7`.

Setup: `1f26cc0534ab8a02681ba3c3a26d788d2ba9a248d1b129ee646c7747e8805790`.

Não confunda os relatórios históricos das fases anteriores com esta execução. Em Linux, a repetição final local teve 279 aprovados e um ignorado por ausência local do modelo; a aprovação Windows acima executou também esse teste.
