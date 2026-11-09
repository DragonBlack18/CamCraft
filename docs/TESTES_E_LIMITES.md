# CamCraft 4.2 — critérios de validação

Esta versão empacota a base 4.1 para Windows. Os números de versões anteriores estão nos documentos históricos, não são atribuídos automaticamente a este build.

## Gates do workflow Windows

1. Ambiente virtual isolado e dependências fixadas; `pip check` e exatamente uma distribuição que fornece `cv2`.
2. Obtenção do modelo oficial, tamanho/SHA-256 e inferência real antes de compilar. Modelo obrigatório: não se publica um EXE sem pesos para baixá-los depois.
3. Suíte de regressão, incluindo caminhos do modo portátil/instalado, subprocessos internos e funcionalidades anteriores.
4. Auditoria de payload nativo: Python, Tk, FFmpeg e DLLs MSVC app-local requeridas.
5. Executável onedir, portátil (copiado sozinho para uma pasta com espaços) e aplicativo instalado executados com PATH limitado ao Windows, sem PYTHONPATH/PYTHONHOME.
6. Self-test real do modelo, codecs, janela Tk, captura e análise em processos filhos, prévia, foto/SQLite, pausa/retomada, encerramento e comando interno de avaliação.
7. Instalação silenciosa, execução, desinstalação e preservação de arquivo sentinela na pasta de dados.
8. Hashes SHA-256 e relatório anexado à Release somente após todos os passos anteriores.

O runner contém ferramentas de desenvolvimento, mas os EXEs são testados com Python fora do PATH. Isso é evidência de empacotamento, não equivale a uma VM de consumidor sem nenhum runtime instalado. Há guarda de sockets Python no self-test; não é uma prova de isolamento de rede de todo o sistema operacional. A aquisição sintética não testa uma webcam física.

## Resultados por build

Consulte `CamCraft-4.2.0-validation.zip` na Release e o workflow correspondente. Ele contém JUnit dos testes, auditoria de DLLs, inventário de bibliotecas e os relatórios JSON dos executáveis/instalador. O workflow falha antes de publicar quando qualquer gate falha. Os logs do Actions registram também correções ou tentativas que não passaram.

## Não validado por esses gates

Acurácia em pessoas encobertas, gravações do quarto do usuário, todos os modelos de webcam/DVR, longa duração em produção, Windows 10/11 em todos os drivers, reconhecimento de autoria, CUDA/RTX e assinatura digital de executáveis. Compilação não altera os pesos nem treina o modelo.

## Referências técnicas

- PyInstaller: https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html
- PyInstaller operating mode: https://pyinstaller.org/en/stable/operating-mode.html
- Inno Setup: https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm
- Modelo: https://github.com/opencv/opencv_zoo/tree/main/models/object_detection_yolox

Relatórios são evidências de execução, não certificação de segurança/precisão.
