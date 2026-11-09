# CamCraft 4.2.0 — Windows independente

## Downloads

- **CamCraft-Portable-4.2.0-x64.exe**: arquivo único, sem instalação. Dados em `CamCraft-data` ao lado do executável.
- **CamCraft-Setup-4.2.0-x64.exe**: instalação por usuário; dados em `%LOCALAPPDATA%\CamCraft\data`.
- **SHA256SUMS.txt**: hashes dos dois executáveis.
- **CamCraft-4.2.0-validation.zip**: resultados dos testes do código, EXEs e instalador, mais inventário de dependências.

Os dois EXEs incluem Python, bibliotecas nativas, Tk/FFmpeg e o modelo ONNX verificado. Não precisam de Python instalado, pip, API key ou download de modelo no primeiro uso. Funcionam offline com webcam/arquivo; RTSP requer acesso à rede da câmera.

## O que foi preservado

Captura fluida independente da IA, controles simples, detecção e rastreamento, objetos por referências, ausência/retorno e oclusão, registros/evidências, revisão, anotação, avaliação offline, exportações e backup.

## Validação

Esta Release só é criada após os gates Windows: instalação limpa de dependências, regressão com modelo real, auditoria de DLLs, execução dos EXEs com Python fora do PATH, fonte sintética com análise neural em processo separado, codecs/GUI/banco/evidências, instalação e desinstalação preservando dados. Consulte o ZIP de validação para resultados exatos.

Isso não mede acurácia na câmera do usuário nem equivale a homologação de todo hardware/driver. O runner é Windows Server 2022 x64. O alvo de uso é Windows 10/11 x64. A inferência continua em CPU; não foi implementado treinamento novo ou CUDA.

Sem assinatura Authenticode nesta versão. Confira a origem e os hashes. Não desative proteções de segurança. O portátil pode demorar mais na abertura por extrair o runtime temporariamente; seus dados ficam fora dessa extração.

A desinstalação do Setup preserva registros. Feche a versão anterior e faça backup antes de migrar. Guia de importação em `docs/WINDOWS.md`.
