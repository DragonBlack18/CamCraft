# Vision Local — Fase 4 / v4.0.0

**Janela nativa de câmera, detecção local e objetos cadastrados; agora com revisão de ocorrências, evidências verificáveis, anotação manual, avaliação independente e backup restaurável. Sem dashboard, navegador ou serviço de nuvem obrigatório.**

Esta distribuição inclui as bases das fases 1–3. É **código-fonte com inicializadores**, não um EXE compilado. Não sobrescreva instalações anteriores.

> A implementação está disponível para teste local. A inferência YOLOX real, a precisão na sua câmera e a execução em Windows **não foram verificadas neste ambiente Linux**. O relatório distingue os testes executados dos limites. Não foi treinado um modelo com dados do usuário. A instalação limpa das dependências também ficou bloqueada neste ambiente; a suíte rodou com OpenCV 4.13 disponível, não valida por si a preparação da variante headless no seu PC.

## 1. Começar no Windows

1. Extraia o ZIP em uma **pasta nova**, por exemplo `C:\VisionLocal4`.
2. Abra **INICIAR.cmd**. A primeira preparação usa internet para bibliotecas e modelo oficial; o inicializador preserva dados/ambiente existentes.
3. Na janela, selecione **Webcam 0 → Iniciar**. Para RTSP/DVR, HTTP/MJPEG ou vídeo gravado, pare a câmera e use **Fonte...**.
4. Feche pela janela; mantenha o terminal aberto enquanto estiver usando o programa.

Há CPython x64 suportado pelo inicializador de 3.11 a 3.14 (com GIL). Se não existir Python compatível, ele tenta preparar o instalador oficial em `.runtime`, conferindo SHA-256 e assinatura do fornecedor; não altera o PATH global. Essa execução Windows permanece pendente. Para informar um Python já instalado:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INICIAR.ps1 -PythonPath "C:\caminho\python.exe"
```

Primeira instalação precisa de internet. Depois de bibliotecas e pesos preparados, use `-Offline` para impedir download. Não desative antivírus/firewall corporativo; resolva bloqueios com a TI.

**Alternativa explícita:** `OBJETOS_SEM_MODELO.cmd` usa as referências vazio/presente dos objetos cadastrados, **sem detecção de pessoas e sem associação de retirada a pessoas**. Dispensa o modelo neural, mas não a instalação inicial das bibliotecas. Não é fallback silencioso para o YOLOX.

`DIAGNOSTICO_SEM_MODELO.cmd` é demonstração técnica com HOG, não modo de precisão. A versão usa CPU, sem CUDA/RTX automática.

## 2. O que mudou na Fase 4

| Área | Implementado |
|---|---|
| Histórico | Filtros por câmera, evento, data local, texto e revisão; páginas de 100 registros, sem limite de navegação a apenas 100. Novos eventos não deslocam a página atual. |
| Revisão | Imagens antes/depois/anotadas, metadados, nome declarado do operador, observação e decisões Confirmado/Falso positivo/Inconclusivo. O evento original não é reescrito. |
| Evidências | Conferência de SHA-256, detecção de ausência/alteração/pendência, preservação contra retenção, exportação de ocorrência em ZIP verificável. Clipe abre no reprodutor do sistema. |
| Amostras | Captura original sem caixas, anotação manual com mouse, categorias, negativos explicitamente confirmados, revisões e agrupamento por gravação/sessão. |
| Exportação de dados | COCO, YOLO e manifesto nativo; divisão por grupos inteiros para treino/validação/teste, sem transformar previsões em rótulos. |
| Avaliação | Detector em processo isolado/cancelável; precision, recall e F1 gerais/por classe, contagem TP/FP/FN, tempos; comparação de limiares somente em validação. Critério de aprovação recusa dados insuficientes e classes sem exemplos. |
| Continuidade | Backup consistente do SQLite/configuração/referências/mídias/anotações; restauração apenas em pasta vazia; verificação contra corrupção e caminhos ZIP perigosos. |
| Desempenho | Estatística limitada p50/p95 e cadenciamento opcional conforme custo real, sem reduzir limiar/resolução silenciosamente. Recuperação não acumula falhas antigas indefinidamente após operação saudável. |

As telas extras são diálogos de operação. A janela principal continua centrada no vídeo, controles de câmera e estado. Uma câmera ativa por vez; até oito objetos cadastrados por fonte fixa.

## 3. Cadastrar e monitorar objetos

Com câmera imóvel, escolha **Objetos... → Novo**. Retire o objeto, marque uma região pequena do local vazio. Depois coloque o objeto, tire as mãos da frente e capture a referência presente. As referências precisam mostrar uma diferença observável e a mesma cena/sessão.

O sistema distingue presença, oclusão/inconclusivo, ausência persistente e retorno. Mudanças de iluminação, posição, resolução e cena podem suspender a análise e exigir recalibração.

- `AUSENCIA_CONFIRMADA`: o local passou a corresponder à referência vazia. **Não atribui autoria**.
- `RETIRADA_PROVAVEL`: exige evidências adicionais da trajetória do objeto e movimento associado a uma única pessoa; continua sendo hipótese sujeita a revisão.
- `RETORNO_OBSERVADO`: aparência voltou ao local; não prova a mesma unidade física nem quem devolveu.

O modelo genérico tem 80 categorias, não reconhece qualquer peça/objeto arbitrário. IDs são temporários por sessão, não nomes/identidades reais. O aplicativo não reconhece rostos nem conclui furto. A revisão “Confirmado” é a opinião registrada do operador, não uma verdade validada pelo software.

## 4. Revisar e preservar uma ocorrência

Clique em **Registros**, aplique filtros e dê duplo clique. Confira abas Antes/Depois/Anotado e o estado dos arquivos; escreva uma observação e selecione a decisão adequada. Revisões antigas continuam disponíveis.

Use **Preservar evidência** para excluí-la da retenção automática; **Liberar retenção** permite limpeza futura. Abrir clipe também o preserva para evitar remoção enquanto o reprodutor estiver usando o arquivo. Exportar uma ocorrência cria uma cópia verificável; não equivale a preservar os originais.

O armazenamento de evidências tem padrão 512 MiB/1.000 conjuntos, ajustável em Análise. Se mídias preservadas ultrapassarem a quota, elas não serão apagadas silenciosamente; o diagnóstico mostra retenção bloqueada. O limite não é um disco virtual rígido: deixe espaço livre e arquive dados importantes. Imagens amostradas/clipes sem áudio não substituem gravação contínua de vigilância.

## 5. Medir em vez de supor precisão

Use **Validação → Capturar amostra para anotação** e **Amostras e anotação manual...**. Desenhe caixas e anote **todos** os objetos das categorias escolhidas. Uma imagem sem caixas só vira negativo quando você confirma que a anotação está completa; amostras incompletas ficam como rascunho e não entram no conjunto exportado.

Não invente grupos diferentes para quadros da mesma gravação. Exporte dados agrupados, reserve `val.json` para escolher limiares e `test.json` para ensaio final. **Pare a câmera** antes de **Validação → Avaliar conjunto anotado...**; escolha o JSON já extraído, não o ZIP. A inferência roda em processo separado, com cancelamento e sem mudar configuração/modelo automaticamente.

O critério preliminar exige, por padrão, teste independente, ≥100 imagens, ≥20 positivas, ≥20 negativas, ≥3 grupos no teste, ≥5 objetos anotados de cada categoria, precision ≥0,95 e recall ≥0,90 **gerais e por categoria**, e p95 de inferência ≤500 ms. São parâmetros de ensaio, **não promessa de atingir essas metas, certificação ou probabilidade de um evento estar correto**. Com dados insuficientes, o resultado é `NOT_ACCEPTED`. Estes mínimos não asseguram significância estatística.

Há exportação para treinar externamente, **mas treinamento e troca por um modelo customizado não estão implementados/validados nesta entrega**. O adaptador verifica um grafo YOLOX específico; renomear outro ONNX não o torna compatível. Medir detecção em imagens não mede rastreamento, entradas/saídas nem atribuição de retiradas. Veja `docs/AVALIACAO_REAL.md`.

## 6. Migrar dados da Fase 3 (opcional, sem sobrescrever)

Feche o aplicativo antigo. Na nova pasta, prepare **somente** o ambiente, sem abrir a janela, e importe:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INICIAR.ps1 -Objetos -InstallOnly
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\MIGRAR_DADOS.ps1 -Origem "C:\VisionLocal3\data"
```

Depois abra `INICIAR.cmd`. Banco, fontes, referências, evidências e eventual dataset são copiados; a origem permanece intacta. Credenciais protegidas com DPAPI dependem da conta/PC compatíveis. `.venv`, runtime e pesos não são importados. Se a nova pasta já tiver dados, a importação recusa sobrescrever: extraia outra pasta nova, não apague seus dados para forçar.

## 7. Backup e recuperação

Pare o monitoramento e escolha **Manutenção → Criar backup completo...**, fora de `data`. O backup contém informações sensíveis; **não é criptografado**. Guarde em local restrito. O programa confere o SQLite e os arquivos, mas hashes locais não provam autoria nem impedem alguém com controle dos arquivos de reescrever tudo.

Para restaurar, feche todos os aplicativos e use um **destino vazio**:

```powershell
.\.venv\Scripts\python.exe .\tools\restore_backup.py `
  --archive "D:\backups\vision.zip" --destination "C:\VisionRecuperado\data"
```

Nenhuma instalação existente é mesclada/sobrescrita. Prepare o programa em `C:\VisionRecuperado` e use essa pasta `data`; não abra a instalação antes de restaurar. Também existe `RESTAURAR_BACKUP.ps1 -Arquivo ... -Destino ...` usando o ambiente preparado. Confirme uma recuperação com seus dados antes de depender do backup como único meio de continuidade.

## 8. Testes e diagnóstico

```powershell
# Suíte local; o teste neural pode ficar SKIP sem pesos.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INICIAR.ps1 -Test

# Integridade dos arquivos desta distribuição.
.\.venv\Scripts\python.exe .\tools\verify_release.py

# Verificar ZIP de ocorrência, dataset ou backup criado na Fase 4.
.\.venv\Scripts\python.exe .\tools\verify_bundle.py "D:\backups\vision.zip"
```

Em Linux, com Python/Tk disponíveis, prepare venv e requirements; `python run.py --regions` abre sem exigir pesos. `start.sh` prepara o modo YOLOX e exige download inicial. Não trate os screenshots sintéticos como medida de acurácia.

Consulte `docs/TESTES_E_LIMITES.md` para resultados executados, `docs/FASE4_OPERACAO.md` para o contrato de uso e `docs/REFERENCIAS.md` para as fontes técnicas. Se ocorrer erro, **Arquivo → Exportar diagnóstico** coleta informações de estado, sem imagens nem URL de credenciais, mas inclui nomes dos perfis/objetos: revise antes de compartilhar.

## 9. Limites importantes

Interface/captura/regras foram exercitadas em Linux; Windows e câmera física permanecem pendentes. Os pesos não puderam ser baixados neste ambiente; o inicializador verifica integridade e executa smoke test local, mas isso ainda não é teste de precisão. Não houve treinamento no seu ambiente nem aceleração CUDA. Há uma fonte ativa e oito regiões cadastradas, não reconhecimento multicâmera/multi-identidade. A aplicação não é um sistema corporativo de autenticação/RBAC, não criptografa banco/fotos/vídeos, e não possui uma cadeia de custódia assinada externa. Use controle de acesso do sistema operacional e políticas locais de retenção; não utilize as observações como única base para atribuir culpa a alguém.
