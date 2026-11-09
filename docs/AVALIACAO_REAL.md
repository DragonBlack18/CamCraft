# Avaliação real — Fase 4

## O que já é automático e o que ainda é manual

Há captura e anotação manual de imagens na janela, exportação em grupos e execução offline do YOLOX com TP/FP/FN, precision/recall/F1 geral e por categoria. Sem pesos/imagens reais, não existe percentual de acerto medido nesta entrega.

Não há treinamento automático. A avaliação de trajetórias/trocas de ID, eventos por hora e atribuição de retirada permanece um ensaio de vídeo com conferência humana. Métricas de caixas não aprovam essas funções por consequência.

## Ensaio físico antes de qualquer conclusão

Use a fonte de melhor qualidade disponível sem prometer recuperação de detalhe inexistente. Grave diferentes horários, distâncias, pessoas paradas/em movimento, cruzamentos, oclusão, reflexos, luz acendendo/apagando e períodos sem atividade. Para objetos, inclua presença, retirada real, devolução, mão cobrindo sem retirar, deslocamento do objeto, duas pessoas e mudança da câmera.

Guarde a gravação original e marque os eventos reais antes de olhar os logs. Compare horário/tipo/objeto/autor observável. Separe ausência de associação com pessoa; “inconclusivo” não equivale a retirada errada. Defina previamente tolerância de tempo e critérios. Registre duração observada, falsos eventos/hora, eventos perdidos, trocas de ID, duplicações e latência câmera→tela com relógio visível. A captura registra tempo após decodificação, não o instante do sensor.

## Criar o conjunto de imagens

1. **Validação → Capturar amostra**, em momentos/sessões diversos.
2. **Amostras e anotação manual**: marque todos os objetos das categorias selecionadas e confirme anotação completa. Salve também negativos reais (completo, sem caixas).
3. Mantenha a mesma gravação no mesmo grupo. Exporte o conjunto com separação agrupada. Não mova manualmente quadros entre splits para melhorar resultado.
4. Extraia em uma pasta, mantendo `images/`, JSONs e mapeamento.
5. Use somente `val.json` para explorar limiares; escolha o limiar antes de avaliar `test.json`.

Um grupo padrão corresponde à câmera + sessão. Isso ajuda, mas não comprova independência: reiniciar a mesma gravação exige manter o mesmo grupo manualmente. O sistema bloqueia duplicação exata, não todas as imagens visualmente próximas. As amostras exportadas contêm imagens e devem permanecer em local restrito.

## Executar pelo terminal

```powershell
# Modelo preparado previamente; calibração somente na validação.
.\.venv\Scripts\python.exe .\tools\validate_dataset.py `
  --manifest "C:\amostras\val.json" --output "C:\amostras\calibracao.json" --sweep

# Ensaio independente com limiar definido antes de olhar o teste.
.\.venv\Scripts\python.exe .\tools\validate_dataset.py `
  --manifest "C:\amostras\test.json" --output "C:\amostras\teste-final.json" `
  --confidence 0.45 --iou 0.5 --threads 2
```

O exemplo 0,45 não é um limiar “ideal” medido. Não sobrescreve um relatório existente. A avaliação pela janela oferece cancelamento/timeout isolado; pelo terminal, Ctrl+C encerra a execução.

## Interpretar os resultados

`[PASS] Avaliação executada` significa que o programa concluiu o cálculo. **Não significa que o detector foi aprovado**: confira `acceptance.decision`. `NOT_ACCEPTED` inclui falta de amostras, classes ausentes, erro de precisão/recall ou tempo elevado. O JSON detalha cada critério e cada classe.

A política padrão exige test, 100 imagens, 20 positivas/20 negativas, três grupos, cinco instâncias anotadas por categoria e precision/recall ≥0,95/0,90 no agregado e nas categorias, com p95 ≤500 ms. Essa é uma política inicial configurável no código, não garantia nem certificação; pode ser inadequada para uma tarefa/risco concreto. Não há intervalo estatístico ou avaliação COCO mAP.

São medições de detecção em imagens, sem confirmação temporal do vídeo. Nenhum teste sobre vídeo gerado, mock de detector ou HOG pode ser apresentado como precisão medida do YOLOX na câmera real. Pesos treinados externamente necessitam adaptação/validação antes de uso; o SHA-256 impede troca silenciosa por outro grafo.
