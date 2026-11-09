# Funcionamento e limites — Fase 3

## Escopo

Um observador temporal de posições fixas, não uma IA que conhece todo o inventário de uma sala. Detecção neural continua sendo YOLOX-S para as classes que ele conhece. A fase nova acrescenta referências visuais nomeadas que não dependem de o nome do objeto existir no COCO.

Cadastro de “Caixa de ferramentas” significa verificar a aparência da região cadastrada, não treinar uma categoria “caixa de ferramentas”. Para acompanhar esse item nas mãos de uma pessoa, ainda é preciso que exista uma trajetória de objeto compatível do detector. Ausência pode ser observada sem essa trajetória; autoria fica não atribuída.

## Calibração

Duas imagens alinhadas, uma vazia e outra ocupada. BGR suavizado e reduzido a 80×80 por referência; contexto da cena em 320×180. A máscara discriminativa destaca os pixels que realmente mudam entre vazio e ocupado. A diferença média deve ser suficiente, e a área fora dos objetos não pode ter mudado muito entre as fotos.

As imagens PNG e o JSON de cadastro têm persistência atômica no nível do arquivo de configuração. SHA-256 detecta corrupção/substituição acidental das imagens. Não protege contra um administrador malicioso que altere também o programa/manifesto. Falha de cadastro preserva as referências anteriores; arquivos gerados incompletos são removidos quando possível.

## Evidência de presença/ausência

Cada quadro é comparado às duas referências. O melhor resultado precisa satisfazer um teto de distância e uma margem sobre a outra referência. Não é uma probabilidade calibrada. Imagem diferente de ambas é inconclusiva; perda de detecção YOLO não é usada como sinal de ausência.

A decisão exige tempo e contagem mínima de observações consecutivas. Oclusão e observações inconclusivas interrompem a confirmação. Fotogramas repetidos/fora de ordem não contam. Pausas acima do intervalo permitido limpam a transição e a atribuição. Reinícios não inferem ações passadas.

As referências são fixas. Não existe atualização automática que “aprenda” um objeto retirado como o novo normal ocupado. O operador pode recalibrar deliberadamente.

## Proteções de cena

Verificação de resolução e assinatura de fonte, cobertura da área de análise, disponibilidade de fundo, mudança global de luminosidade, residual de aparência, desfoque acentuado e deslocamento translacional via `phaseCorrelate`. As pessoas detectadas e os locais cadastrados são excluídos da comparação de fundo.

Essas proteções são heurísticas conservadoras, não garantia contra toda rotação, zoom, reflexo ou sombra. Movimento permanente da câmera exige recalibração. Retorno a condições válidas inicia estado inicial: o programa não reconstrói o que ocorreu enquanto estava suspenso. Regiões uniformes, reflexos e baixa resolução podem impedir tanto a proteção quanto o reconhecimento correto.

O modo sem pessoas não possui máscaras de pessoas: movimento grande no fundo pode suspender o monitoramento. Ele é útil para testar referências com câmera fixa, não é um modo equivalente de associação de ações.

## Associação provável a pessoa

Apenas com YOLOX e categorias de objetos habilitadas. Condições conjuntas:

1. Objeto detectado, confirmado e vinculado à posição inicial em mais de uma observação.
2. Pessoa confirmada próxima por tempo/observações mínimos, com sobreposição geométrica recente na área do item.
3. A mesma trajetória do objeto observada fora do local, com aparência compatível com a referência.
4. Uma única pessoa candidata, sem múltiplas pessoas próximas/recentes que gerem ambiguidade.
5. Pelo menos três observações de movimento conjunto durante 0,4 s ou mais, deslocamento mínimo, direções compatíveis e posição relativa estável.
6. Região original posteriormente confirmada vazia, com prova de movimento ainda recente.

Uma caixa da pessoa sobrepondo a região não demonstra que uma mão a tocou. O texto “contato geométrico” descreve somente essa regra. Não há estimador de mãos/pose, reconhecimento facial, ReID entre câmeras, reconhecimento de identidade ou avaliação de intenção. Mesmo com todas as condições, o registro é `RETIRADA_PROVAVEL`, nunca “fulano roubou”.

Itens idênticos podem ser confundidos, tracks podem trocar e oclusões podem impedir a associação. O motor prefere `AUSENCIA_CONFIRMADA` sem autor a inventar uma atribuição. Retornos são mudança de aparência da posição; não garantem retorno da mesma unidade física.

## Evidências e revisão

Fotos antes/depois têm tempos distintos e verdadeiros no JSON. A anterior é a última imagem válida do estado anterior, não obrigatoriamente imediatamente anterior ao movimento. Se não houver anterior nesta sessão, o campo é nulo.

Clipes são amostrados, limitados a 3 fps, 32 amostras e 8 MiB por buffer/grupo, até 3 clipes ativos. Fila de imagens de clipe: 2. Fila de pedidos: 3. Fila de evidências fotográficas: 4. Saturação é sinalizada; nenhum limite é uma promessa de armazenamento sem perdas.

O evento textual e a confirmação de escrita são distintos. Um evento com `evidence_id` pode apontar para gravação ainda em andamento, removida por retenção ou que falhou; procure `EVIDENCIA_SALVA`, `CLIPE_SALVO`, `EVIDENCIA_FALHOU` e `CLIPE_FALHOU`.

Revisões humanas são eventos novos ligados ao ID original. Não há login de operador; esse parecer não autentica a pessoa que clicou. Revisões não treinam automaticamente o detector.

## Fora do escopo

Reconhecimento universal/sem cadastro; inventário por número de série; múltiplas câmeras simultâneas na janela; detecção especializada de mãos; aprendizagem contínua automática; gravação contínua, áudio ou NVR; inferência CUDA; identificação de rostos/nomes; garantias de precisão industrial. São extensões distintas, não opções escondidas já implementadas.
