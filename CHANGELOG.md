# Alterações

## 4.2.0 — CamCraft / distribuição Windows

- Importação do aplicativo completo Vision Local 4.1, mantendo captura fluida e todas as funcionalidades das fases 1–4.
- Portátil único e Setup por usuário, ambos com runtime, bibliotecas e modelo ONNX verificado incluídos.
- Separação entre recursos imutáveis e dados persistentes; dados nunca na pasta temporária do portátil.
- Entrada segura para multiprocessing e subprocessos internos no programa congelado.
- Avaliação offline sem depender de arquivos `.py` ou Python instalado no computador do usuário.
- Self-tests dos executáveis, auditoria nativa, licenças e checagem de instalação/desinstalação.
- Builds Windows e publicação condicionada aos testes, com hashes e relatórios.

Modelo, categorias e lógica de detecção continuam os da 4.1. Não há nova promessa de acurácia ou aceleração CUDA.
