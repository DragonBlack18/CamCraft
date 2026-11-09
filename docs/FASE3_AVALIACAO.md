# Avaliar a Fase 3 na câmera real

A suíte testa regras, recuperação e armazenamento. Não mede precisão visual em uma câmera que não foi fornecida. Para aceitar a etapa no ambiente real, grave e anote sequências separadas das usadas para calibração.

## Casos mínimos

Objeto presente sem ninguém; pessoa passa sem tocar; pessoa cobre e se afasta; retirada e retorno; item substituído por outro; duas pessoas junto da região; objeto parcialmente deslocado; apagamento de luz; câmera movida; interrupção da fonte. Inclua períodos longos sem eventos. Registre falsos eventos por hora, perdas e atribuições erradas. Não valide apenas a cena mais fácil.

Uma confirmação temporal tem atraso deliberado. Ajustar tempos usando o mesmo vídeo depois chamado “teste” vicia a avaliação. Separe calibração/ajuste e avaliação independente. Use a mesma origem de tempo e IDs nos dois arquivos.

## Exportar previsões

O programa já exporta CSV pela janela. Para a ferramenta por evento, com a execução encerrada:

```powershell
.\.venv\Scripts\python.exe .\tools\export_events.py --db .\data\events.sqlite3 --origin-utc 0 --output .\data\reports\previsoes.json
```

`--origin-utc 0` mantém timestamps Unix do quadro em `time_s`; um outro valor subtrai uma origem comum. A verdade manual precisa usar a mesma referência. O horário após decodificação não é necessariamente o timestamp original do sensor. O comando exporta mudanças relevantes; limite o banco/arquivo ao período avaliado antes de calcular métricas.

Formato de previsões e verdade manual (exemplo de esquema, NÃO resultados medidos):

```json
[
  {
    "camera_id": "webcam0",
    "object_id": "o_0123456789abcdef",
    "code": "AUSENCIA_CONFIRMADA",
    "time_s": 12.5,
    "actor_track_id": null
  }
]
```

Use o ID real do cadastro. Separe ausência (`AUSENCIA_CONFIRMADA`) de atribuição provável (`RETIRADA_PROVAVEL`) de forma consistente na anotação. Para avaliar apenas detecção de retirada, normalize ambos para um código comum **nos dois arquivos** e registre essa transformação no relatório. Não misture essa métrica com precisão de autoria. O avaliador compara códigos literalmente.

## Calcular

```powershell
.\.venv\Scripts\python.exe .\tools\evaluate_events.py --predictions .\data\reports\previsoes.json --truth .\verdade_manual.json --seconds 3600 --tolerance 2 --output .\data\reports\avaliacao_eventos.json
```

`--seconds` é a duração total efetivamente monitorada do período avaliado, inclusive sem eventos, não a soma das durações dos clipes salvos. Ajuste a tolerância à definição de horário de referência: início da ação versus momento de confirmação são diferentes. A ferramenta não pode validar se essa duração ou os rótulos são verdadeiros.

Associação um a um por câmera, objeto e código, maximizando primeiro o número de pares temporais válidos. Duplicações viram falsos positivos. Calcula TP, FP, FN, precisão, recall, F1, falsos eventos por hora e mediana do atraso. Sem previsões, precisão é `null`, não 100%.

Autoria é avaliada apenas quando a verdade fornece um ID temporário da mesma sessão: acertos, erros e abstenções ficam separados. Não compare IDs locais de sessões diferentes como se fossem identidade real.

A ferramenta de imagens da Fase 2 (`tools/evaluate_images.py`) continua disponível para avaliar o detector isoladamente. Precisão de caixas e precisão dos eventos são métricas diferentes.
