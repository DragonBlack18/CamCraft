# Revisão 4.1 — gargalos e falsos positivos

## Causas identificadas no código 4.0

1. `Window.tick()` desenhava apenas `AnalysisService.latest()`. A captura já era separada, mas a tela continuava subordinada à inferência.
2. `after(45, tick)` ocorria depois de todo o trabalho de renderização; a atualização tinha um teto abaixo de 22,3 Hz mesmo antes do custo de desenho.
3. `AnalysisConfig.classes` iniciava em `all`, incluindo veículos. `render()` desenhava candidatos ainda não confirmados.
4. O tracker podia recuperar uma caixa confirmada com scores fracos repetidamente, sem expirar a validade do último score forte.
5. A janela de confirmação usava o tempo desde a criação do ID, mesmo após perda de suporte. A tolerância a intervalo era derivada do FPS solicitado, não do comportamento real.
6. O worker calculava uma imagem de prévia reduzida mesmo com a codificação JPEG desligada.

Nenhuma dessas observações prova qual foi a causa exclusiva da câmera física do usuário travar. Exposição, driver, fonte e CPU continuam relevantes. Não houve acesso ao vídeo com a pessoa sob coberta.

## Implementação

`vision_app/preview.py` cria uma thread de prévia limitada: só guarda a imagem RGB mais recente, redimensiona fora dos callbacks Tk, evita recópia quando a sequência não mudou e rejeita imagens antigas. Não executa IA e não grava em disco.

A interface reutiliza o item de imagem no Canvas e o buffer ImageTk quando o tamanho é o mesmo. O agendamento desconta o custo de renderização, em vez de dormir 45 ms adicionais. Estatísticas e verificações de saúde atualizam a 4 Hz, não em todo quadro.

O quadro principal ao vivo não recebe retângulos de outro instante. A miniatura contém a imagem exata analisada, com idade explícita. Câmera, geração, repetição de arquivo e resolução precisam corresponder antes de mostrar a miniatura. Sem correspondência, sem resultado recente ou com IA pausada, ela desaparece.

Categorias proibidas são excluídas no decode e novamente no tracker. O argmax continua sendo calculado nas 80 categorias originais: um “carro” não é transformado em “pessoa” pelo filtro. A margem entre as duas melhores classes rejeita candidatos ambíguos. Limiar por categoria e confirmação temporal são aplicados antes dos eventos.

Mudanças da análise pausam só o worker da IA e reiniciam IDs em nova sessão, preservando o PID da captura. Mudanças físicas da webcam continuam exigindo parada explícita.

## Escopo que não mudou

Modelo, input 640×640 e motor OpenCV CPU permanecem. Sem CUDA, treinamento, rede neural diferente ou reconstrução de detalhes perdidos. A versão não transforma 2 análises/s em 30 análises/s e não inventa movimento de caixas entre quadros.

## Fontes primárias consultadas nesta revisão

- OpenCV Zoo, demo YOLOX (BGR→RGB, letterbox e uso sequencial): https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/object_detection_yolox/demo.py
- OpenCV Zoo, pós-processamento YOLOX: https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/object_detection_yolox/yolox.py
- OpenCV, propriedades e dependência de hardware/backend: https://docs.opencv.org/4.x/d4/d15/group__videoio__flags__base.html
- Python, Tkinter/event loop: https://docs.python.org/3/library/tkinter.html

A correção foi escrita sobre o ZIP da Fase 4 fornecido na conversa. Nenhum repositório remoto do usuário foi alterado. Não foi alegada leitura de livros ou vídeos não consultados.
