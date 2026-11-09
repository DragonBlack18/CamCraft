# Operação da Fase 4

## Arquitetura e sincronização

A fonte continua em processo isolado. A inferência tem no máximo uma solicitação em andamento e o transporte preserva o quadro mais recente. O resultado leva sequência, sessão, tempos e seu quadro original; a exibição utiliza a própria imagem analisada. Não há promessa de todos os quadros serem analisados: um consumidor lento pula intermediários em vez de construir uma fila atrasada. Movimento rápido pode ocorrer entre quadros.

Os módulos novos não executam redes neurais no event loop Tk. A avaliação offline exige câmera parada e roda em subprocesso independente, com cancelamento, timeout de 30 minutos e log limitado a 2 MiB. Leitura de evidências, backup, exportação e anotações são despachadas pelo trabalhador de operações da janela; widgets/PhotoImage só são atualizados na thread principal.

O cadenciamento adaptativo é opcional (padrão ligado, fração de trabalho 0,75): a próxima solicitação considera o custo da anterior e o limite de FPS. **Não é limitador rígido de CPU**, não altera confiança/NMS/resolução, e pode reduzir a quantidade de quadros analisados. Estatísticas p50/p95 usam no máximo 240 observações. “Idade do quadro” começa após decodificação; não mede atraso da câmera/DVR/rede.

O watchdog mantém limite de falhas consecutivas. Após período saudável de 30 segundos e dez quadros novos, a sequência de falhas é reiniciada; interrupções antigas não bloqueiam para sempre uma execução recuperada.

## Revisão de ocorrências

Histórico usa paginação keyset por ID e um teto de consulta: páginas não mudam de posição se novos eventos forem criados. Atualizar obtém um teto novo. Datas nos filtros são locais, inclusive o dia final. Desmarque “Só ocorrências” para estados/diagnóstico; eventos importantes são o padrão. Pesquisar texto não executa SQL arbitrário.

Uma revisão grava em uma única transação um snapshot do evento, decisão, observação, operador informado, data e encadeamento SHA-256, além do registro de compatibilidade `REVISAO_EVENTO`. O operador é **texto declarado**, não uma conta autenticada. Revisões antigas da Fase 3 permanecem consultáveis, sem lhes atribuir retroativamente assinatura/cadeia nova.

O encadeamento detecta alterações inconsistentes e ordenação inválida; **não resiste a um administrador que recalcule toda a cadeia**, nem prova que nenhum sufixo tenha sido removido. Não há ancoragem externa, assinatura digital ou relógio confiável remoto. Confirmar não transforma uma hipótese da câmera em prova de autoria.

## Arquivos e retenção

Estados: `VERIFIED` (hashes locais conferem), `PENDING` (gravação/trecho pendente), `MISSING` (arquivo/metadata ausente), `MODIFIED` (conteúdo divergente). Arquivos corrompidos não são mostrados como evidência conferida nem exportados como se estivessem íntegros.

O ZIP de ocorrência contém evento, revisões, resultado da verificação, fotos e clipe quando disponível. Se evidências sumiram pela retenção, exportação apenas do registro exige confirmação explícita; não fabrica imagens. Pacotes são criados com nomes inéditos e conferidos; não sobrescrevem destino existente. A publicação do arquivo não é transação de sistema de arquivos resistente a toda queda de energia.

A marca `.preservada` impede limpeza automática. Abrir clipe marca preservação antes de entregar o arquivo ao player. Preservar não duplica nem criptografa os dados e não impede exclusão manual. Se a quota ficar tomada por material preservado, o programa avisa; deve-se exportar/arquivar e só liberar a retenção após conferir a cópia. Ausência de espaço pode impedir novas gravações.

ZIPs usam manifesto SHA-256 com tamanhos. Validação rejeita caminhos absolutos, `..`, barras invertidas, dispositivos reservados Windows, links simbólicos, colisões sem distinção de caixa e membros extras/divergentes. Há limites de quantidade (30 mil), tamanho total descompactado (12 GiB) e por membro (1 GiB). Um backup que exceda esses limites é recusado; isto não é armazenamento ilimitado.

## Amostragem manual

O dataset fica em `data/dataset`, separado da retenção de evidências. Limites: 3.000 imagens e 2 GiB, sem limpeza automática das amostras. Repetições exatas são recusadas; quadros quase iguais ainda podem existir e devem ficar no mesmo grupo. Captura guarda PNG original, hora, fonte/sessão e hash; não exporta credenciais de fonte.

O anotador converte coordenadas do mouse da imagem redimensionada para pixels originais. Até 200 caixas/imagem; escopo explícito de categorias. Há desfazer, limpar caixas e histórico de revisão. “Anotação completa” é uma declaração humana de que **todos** os objetos das categorias selecionadas foram marcados. Sem caixas + completo significa negativo nesse escopo, não ausência de quaisquer coisas na cena.

Rascunhos não são exportados como verdade. Concorrência usa número de revisão: uma janela desatualizada precisa recarregar. Imagem com hash/dimensões divergentes é recusada.

Exportação agrupada requer no mínimo três grupos e usa grupos inteiros em cerca de 60% treino / 20% validação / 20% teste. Isso não garante balanceamento de classes. São necessários grupos suficientes **no teste** para o gate; três grupos totais não bastam para a exigência de três grupos só de teste. Com a distribuição padrão, quinze grupos permitem três para teste. O rótulo de grupo é responsabilidade do operador: separar a mesma gravação em sessões/nomes diferentes pode vazar informações.

Os formatos incluem COCO (IDs contíguos 1..N), YOLO (0..N-1), `data.yaml`, `dataset.json` com mapeamento e manifestos nativos com IDs fonte 0..79. Não confunda IDs COCO oficiais esparsos com esse mapeamento. Exportação “somente avaliação” não divide grupos e produz `evaluation.json`, útil para ensaio exploratório mas não passa o gate independente.

## Avaliar o detector

Extraia o ZIP mantendo os caminhos relativos. Prepare o YOLOX oficial. Pare monitoramento e escolha o manifesto em Validação. `val.json` permite comparação de confiança de 0,25 a 0,85; `test.json` usa um limiar fixo. As escolhas não são aplicadas automaticamente. Não escolha parâmetros vendo repetidamente o teste e depois declare independência.

O resultado compara caixas um-a-um por categoria e IoU (padrão 0,5), priorizando quantidade máxima de pares válidos antes da qualidade do encaixe. Precision, recall e F1 são calculados em um ponto de operação; denominadores sem dados retornam null. A ferramenta não calcula COCO mAP nem probabilidades calibradas.

Critério preliminar padrão: test independente; ≥100 imagens; ≥20 positivas/20 negativas; ≥3 grupos de teste; ≥5 instâncias verdadeiras por categoria; precision ≥0,95 e recall ≥0,90 no agregado e em cada categoria; p95 inferência ≤500 ms. O resultado `NOT_ACCEPTED` pode significar erros, desempenho insuficiente **ou falta de dados**. Limites são parâmetros da função `acceptance_gate`, não prescrição universal. Não há intervalos de confiança estatísticos nesta versão.

A avaliação registra hash do modelo e do manifesto. Qualidade da anotação humana/grupos não pode ser provada automaticamente. O modelo atual é genérico, 80 classes, sem atualização silenciosa. A aplicação usa OpenCV DNN para inferência, não treinamento. Exportar COCO/YOLO prepara dados para um pipeline de treinamento separado; não torna qualquer arquivo ONNX compatível com o adaptador existente.

## Backup, restauração e migração

Backup requer captura parada, filas concluídas e armazenamento saudável. Copia SQLite via API de backup, incluindo conteúdo comprometido em WAL, e confere integridade. Pacote inclui fontes, análise, referências, objetos, banco, revisões, mídias e dataset. Não inclui `.venv`, `.runtime`, modelo ONNX, caches ou logs/reports. Imagens e ZIP não são criptografados.

Restauração verifica hashes/limites antes e após extrair em estágio, valida SQLite/esquema e JSON, usa trava de instância e só instala em destino vazio. Se falhar, remove apenas itens recém-criados nessa transação, preservando a origem. Não faz merge de instalações. A versão tem limites de pacote; retenções muito grandes podem precisar arquivamento separado.

Migração direta também exige origem e destino independentes e aplicativos fechados. Prepare ambiente com `-Objetos -InstallOnly`, antes de abrir a janela na instalação nova. O inicializador pode criar `data/reports`; isso não substitui os dados importados. DPAPI é vinculada à conta/máquina; em outro ambiente recadastre as credenciais. Nome de conta do revisor não é transferido como identidade autenticada.

## Critério honesto para produção

O software oferece ferramentas para validar; não foi aprovado automaticamente na sua instalação. Faça teste físico, desempenho sob carga de uso, recuperação após desconexão e operação prolongada; acompanhe falsos eventos por hora e eventos perdidos. Para retiradas, anote vídeos e revise atribuição separadamente da métrica de caixas. Não baseie punições/segurança de pessoas em um único resultado automático.
