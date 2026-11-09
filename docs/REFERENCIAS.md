# Referências e decisões verificadas — 06/11/2026

Estas são fontes primárias efetivamente consultadas. Não foi alegada revisão de livros inteiros, vídeos ou fóruns não lidos.

## Detector e modelo

- OpenCV Zoo, diretório YOLOX-S: https://github.com/opencv/opencv_zoo/tree/main/models/object_detection_yolox
- README do modelo e categorias/resultados: https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/object_detection_yolox/README.md
- Implementação de referência consultada: https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/object_detection_yolox/yolox.py
- Demo oficial (inclui conversão BGR→RGB): https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/object_detection_yolox/demo.py
- Ponteiro LFS/tamanho/hash: https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/object_detection_yolox/object_detection_yolox_2022nov.onnx
- Tutorial DNN: https://docs.opencv.org/4.x/da/d9d/tutorial_dnn_yolo.html

O adaptador entregue é escrito para o export exato do Zoo: RGB float32 0..255, padding 114 alinhado ao topo/esquerda, 640×640, saída 1×8400×85 e decodificação de grades no adaptador. Outros exports podem incluir a decodificação no grafo ou usar outros canais/escalas; não os renomeie para este arquivo. O hash impede substituição silenciosa.

O gráfico/benchmark COCO do fornecedor não mede o acerto na câmera do usuário. Não foi reproduzido neste projeto.

## Rastreamento

- Artigo ByteTrack: https://arxiv.org/abs/2110.06864
- Código primário consultado: https://github.com/FoundationVision/ByteTrack

A implementação local NÃO incorpora a biblioteca ByteTrack nem pretende reproduzir suas métricas. Usa o princípio de associar primeiro detecções fortes e depois tentar recuperar trajetórias confirmadas com candidatos mais fracos. Filtro de Kalman temporal, associação por classe/IoU/distância, atribuição parcial húngara e regras de eventos foram implementados no projeto. Não há ReID ou descritores faciais.

## Execução, interface e empacotamento

- Tkinter/event loop: https://docs.python.org/3/library/tkinter.html
- Multiprocessing e locks/processos terminados: https://docs.python.org/3/library/multiprocessing.html
- OpenCV headless, CPU-only, uma distribuição cv2 por ambiente: https://pypi.org/project/opencv-python-headless/4.13.0.92/
- Propriedades de captura/timeouts: https://docs.opencv.org/4.x/d4/d15/group__videoio__flags__base.html
- SQLite WAL: https://www.sqlite.org/wal.html
- Python oficial usado pelo bootstrap: https://www.python.org/downloads/release/python-31410/
- SciPy/atribuição: https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html

As dependências são fixadas, não necessariamente as mais novas. A instalação isolada evita misturar bibliotecas com o projeto anterior. Recursos nativos ficam em processos encerráveis; o código não depende apenas do suporte do driver a CAP_PROP_BUFFERSIZE ou timeouts. UI no thread principal, inferência em processo separado, SQLite/evidência em trabalhadores próprios.

## Origem da base

Os módulos `vision_foundation` vieram do ZIP da Fase 1 fornecido nesta conversa. A alteração do caminho de captura permite desativar JPEG quando o consumidor desktop utiliza BGR. Nenhum repositório do usuário foi modificado, publicado ou enviado ao GitHub nesta entrega.


# Fontes consultadas para a Fase 3 — 06/11/2026

- OpenCV, comparação de templates: https://docs.opencv.org/4.13.0/d4/dc6/tutorial_py_template_matching.html
- OpenCV, `phaseCorrelate`: https://docs.opencv.org/4.13.0/d7/df3/group__imgproc__motion.html
- OpenCV, subtração de fundo em câmera fixa: https://docs.opencv.org/4.13.0/d1/dc5/tutorial_background_subtraction.html
- OpenCV Zoo, modelo YOLOX-S: https://github.com/opencv/opencv_zoo/blob/main/models/object_detection_yolox/README.md
- Instalador oficial de Python 3.14.10 e SHA-256 do Windows x64 reconferidos: https://www.python.org/downloads/release/python-31410/

O código da Fase 3 foi implementado sobre a base fornecida. Não incorpora um pacote pronto de “detecção de furto”. `matchTemplate` é usado na comparação de aparência para associação do objeto; `phaseCorrelate` é uma proteção de deslocamento da câmera. A decisão de ocupado/vazio usa distância entre duas referências fixas, não o simples desaparecimento de uma caixa neural.

A documentação de subtração de fundo foi consultada como referência conceitual; **MOG2 não é o motor de decisão entregue**. Atualizar automaticamente um fundo durante a ausência poderia apagar a distinção entre ocupado/vazio. Não houve alegação de leitura de livros completos, vídeos ou fóruns não acessados.

Nenhum repositório do usuário foi alterado. O pacote permanece local, sem API de IA nem upload de cenas. A execução do YOLOX real permaneceu pendente: o arquivo ONNX não pôde ser obtido neste ambiente (rede/DNS restritos). A falha não foi escondida por um modelo de mentira. Os modos de referência/HOG são explicitamente identificados.


# Fontes consultadas para a Fase 4 — 06/11/2026

- Python `sqlite3`, conexão/backup: https://docs.python.org/3/library/sqlite3.html
- SQLite, API oficial de backup: https://www.sqlite.org/backup.html
- SQLite, `integrity_check`/`quick_check`: https://www.sqlite.org/pragma.html
- SQLite WAL e limites de concorrência: https://www.sqlite.org/wal.html
- Tkinter/event loop e tarefas demoradas: https://docs.python.org/3/library/tkinter.html
- OpenCV DNN 4.13 (inferência; não treinamento): https://docs.opencv.org/4.13.0/d6/d0f/group__dnn.html
- scikit-learn, armadilhas de avaliação e vazamento de dados: https://scikit-learn.org/stable/common_pitfalls.html
- scikit-learn, grupos e separação de amostras: https://blog.scikit-learn.org/updates/update-on-metadata-routing/
- OpenCV Zoo, repositório primário e migração de hospedagem dos modelos: https://github.com/opencv/opencv_zoo
- Mirror oficial do arquivo ONNX/tamanho/SHA-256: https://huggingface.co/opencv/opencv_zoo/blob/main/models/object_detection_yolox/object_detection_yolox_2022nov.onnx
- Python 3.14.10, release/instalador oficial: https://www.python.org/downloads/release/python-31410/

Essas fontes sustentam decisões de implementação, não acurácia da aplicação. O agrupamento/exportação, motor de avaliação, UI e arquivos de revisão foram implementados localmente; scikit-learn não foi adicionado como dependência. A documentação DNN não oferece treinamento no aplicativo. Não houve leitura alegada de livros/vídeos/fóruns não acessados nem alterações em repositórios do usuário. O arquivo neural continua não incluído no ZIP; consulta ao tamanho/hash oficial não equivale a executar inferência.
