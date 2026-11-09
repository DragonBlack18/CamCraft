# CamCraft

Visão computacional local, com janela simples de câmera — sem dashboard, navegador ou serviços de IA externos.

**Versão 4.2.0: Windows independente.** Evolução do Vision Local 4.1, preservando captura fluida, detecção/rastreamento, objetos por referências, registros, evidências, revisão, anotação, avaliação e backup.

## Usar sem instalar dependências

Baixe uma distribuição em **[Releases](https://github.com/DragonBlack18/CamCraft/releases)**. Não use o botão Code → Download ZIP para obter o aplicativo pronto: esse botão entrega código-fonte.

| Distribuição | Como usar | Local dos seus dados |
|---|---|---|
| `CamCraft-Portable-4.2.0-x64.exe` | Salvar em uma pasta gravável e abrir | Pasta `CamCraft-data` ao lado do EXE |
| `CamCraft-Setup-4.2.0-x64.exe` | Instalar por usuário; abrir pelo atalho | `%LOCALAPPDATA%\CamCraft\data` |

Python, bibliotecas nativas, Tk, codecs OpenCV/FFmpeg e o modelo YOLOX verificado já vêm incluídos. Não precisa de Python, pip, terminal, Docker, Node, chave de API ou download de modelo ao iniciar. Instalação e detecção local funcionam offline; uma câmera de rede naturalmente precisa de conexão com a rede dela.

O portátil é um EXE único: extrai seu runtime para a pasta temporária ao abrir, mas **não instala Python** e **nunca grava suas evidências nessa pasta temporária**. A primeira abertura pode demorar mais do que as seguintes. O Setup instala os mesmos componentes em uma pasta permanente, sem extração integral a cada abertura.

Requer Windows 10/11 x64 e o driver da câmera funcionando. Builds produzidos e testados no runner Windows Server 2022 x64; isso não substitui homologação com todas as câmeras/edições de Windows. A execução continua em CPU, sem CUDA automática. Executáveis sem certificado Authenticode; confira a origem e os hashes em `SHA256SUMS.txt`. Não desative proteções de segurança.

## Começar

Abra CamCraft, selecione **Webcam 0** e clique em **Iniciar**. Para USB diferente, RTSP/DVR, HTTP/MJPEG ou arquivo, use **Mais → Configurações → Nova fonte**. Use **Ao vivo — fluido** para não prender o vídeo à velocidade da IA. A miniatura mostra exatamente o último quadro analisado e sua idade; não são sobrepostas caixas antigas em imagens novas.

No quarto: **Controles → Quarto / escritório → Menos alarmes**. Veículos são excluídos antes dos registros; isso não reclassifica uma coberta como pessoa. Uma pessoa encoberta pode não ser detectada. **Pausar IA** mantém o vídeo ligado.

## Recursos preservados

Captura em processo separado, supervisão e reconexão, quadro mais recente com memória limitada, prévia independente, detector YOLOX-S com 80 categorias e filtros, IDs temporários, confirmação temporal, área/linha pelo mouse, cadastro vazio/presente de até oito objetos com câmera fixa, ausência/retorno/oclusão, hipóteses conservadoras de retirada, SQLite, imagens antes/depois, clipes amostrados, revisão auditável, preservação de evidências, exportações, anotação COCO/YOLO, avaliação e backup/restauração verificados.

Não há reconhecimento facial, identificação civil, garantia de autoria, detecção de intenção/furto, treinamento automático nem promessa de precisão universal. Logs de retirada provável precisam de revisão humana. Embalar o software não melhora automaticamente a acurácia do modelo.

## Atualizar preservando dados

Feche a versão antiga. O instalador não apaga seus dados ao atualizar ou desinstalar. O portátil novo pode reutilizar a mesma pasta `CamCraft-data`, com a versão anterior fechada. Faça backup antes de atualizar.

Para importar o `data` do Vision Local para um destino ainda vazio, use o comando **interno** do EXE, sem Python externo. Veja [instalação e migração](docs/WINDOWS.md). A origem é preservada; o importador não sobrescreve um destino com dados. Endereços RTSP protegidos por DPAPI permanecem vinculados à conta/PC compatível.

## Código e builds

Todo o código funcional, testes, scripts de desenvolvimento e documentação foram importados. Arquivos pessoais, `.venv`, caches, pesos baixáveis e relatórios/imagens gerados de ensaios antigos não são commitados. Documentos históricos permanecem em `docs/history/`; novos relatórios completos acompanham o artefato de validação de cada build.

- `vision_foundation/`: aquisição, supervisão, IPC, configuração e armazenamento.
- `vision_app/`: interface, detecção, rastreamento, objetos, evidências, revisão e validação.
- `tests/` e `tools/`: regressão e ferramentas de desenvolvimento.
- `packaging/`: PyInstaller, Inno Setup, auditoria nativa e testes dos executáveis.
- `.github/workflows/`: preparação e build/publicação Windows.

Os scripts `INICIAR.cmd`/`INICIAR.ps1` são mantidos **para desenvolvimento a partir do código-fonte**. Usuários das Releases não precisam executá-los.

Em uma máquina Windows de desenvolvimento com Python 3.12 x64 e Inno Setup 6.3+:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\build_windows.ps1
```

O build obtém/verifica o modelo, testa o código, coleta licenças, gera as duas distribuições, executa cada EXE sem Python no PATH e verifica instalação/desinstalação. Um build com falha não publica executáveis. O código-fonte sozinho não é uma instalação offline; **os EXEs da Release são**.

Veja [critérios de teste e limites](docs/TESTES_E_LIMITES.md) e [segurança](SECURITY.md).
