# Testes e limites — Vision Local Fase 3 v3.0.0

## Resultado registrado

**163 testes aprovados; 1 ignorado.** Log e JUnit: `docs/validation/all-tests-final.txt` e `all-tests-final.xml`. A suíte preserva os 114 testes aprovados da Fase 2 e adiciona 49 testes de cadastro, comparação de imagens, associação, evidências, integração, avaliação e importação.

O teste ignorado é a execução real do **YOLOX ONNX**. O download não pôde ser realizado por restrição de rede/DNS deste ambiente; os pesos não estão no ZIP. Nenhum resultado sintético é apresentado como inferência neural ou precisão na câmera do usuário. O inicializador verifica hash e executa inferência local antes de abrir o modo YOLOX.

## O que foi executado

| Área | Verificação real |
|---|---|
| Regressão | Captura, IPC, arquivos/rede local, timeouts, locks, rastreamento, armazenamento e exportações da base. |
| Calibração | Persistência/hash PNG, referências indistinguíveis, mudança de cena, sobreposição, erro de escrita, pausa/exclusão. |
| Estado do objeto | Presente, vazio, retorno, ausência inicial, oclusão com pessoa fraca, alteração inconclusiva, câmera deslocada, luz alterada, lacunas e quadros repetidos. Comparações OpenCV executadas sobre imagens geradas. |
| Atribuição | Movimento conjunto com caixas controladas, múltiplas pessoas, troca de ID e bloqueio de autoria em modos sem YOLOX. Não é teste de acerto do detector. |
| Evidências | JPEG antes/depois, horários distintos, SHA-256, gravação/leitura real de AVI, sessões não misturadas, cauda parcial e falta de amostras. |
| Fluxo integrado | BGR real do teste → comparação → SQLite → JPEG/JSON → AVI. Saídas neurais controladas/vazias, sem fingir detecção. |
| Revisão/avaliação | Revisão persistida sem alterar original; métricas por evento, duplicações, abstenção, associação máxima um a um, entradas inválidas. |
| Migração | SQLite backup, origem preservada, destino existente recusado, processo ativo recusado, symlinks recusados no Linux. |

## Interface nativa

`tools/validate_phase3_gui.py` foi executado em Tk sobre Xvfb/Linux. **Arquivo AVI gerado + decoder real + HOG real + comparação de referências real.** O HOG não encontrou pessoas no material desse teste; não é validação neural.

Fluxo: iniciar, capturar vazio/presente pelo diálogo real, persistir cadastro/reiniciar, exibir estados, gerar ausência e dois retornos observados, salvar clipes, abrir histórico/gerenciador de objetos, exportar CSV/diagnóstico e parar. Sem exceções de callback. Resoluções de janela: 1100×760 e 800×560, controles principais dentro da janela.

Duração: 22.62 s. Heartbeat da interface: p95 40.5 ms; máximo 521.7 ms. A amostra inclui screenshots/exportações do ensaio; não é garantia de ausência de pausas no Windows.

Arquivos: `fase3-gui.json`, `fase3-janela.png`, `fase3-compacta.png` e `fase3-retorno.png`. São screenshots do aplicativo, não mockups.

## Ensaio com oito objetos

`tools/soak_phase3.py --seconds 45`: captura de AVI gerado 640×360, **modo de referências locais**, oito cadastros e interrupção intencional de um processo de análise.

- Duração observada: 45.68 s; 404 quadros analisados.
- Uma interrupção injetada; 1 reinício com recuperação.
- Frequência mediana observada: 9.53 análises/s.
- Comparação dos oito objetos: p95 29.17 ms por quadro aceito.
- Idade **após decodificação**: p95 204.6 ms; não é sensor→tela.
- Pico de RSS somado: 520.7 MiB. Soma processos e pode contar memória compartilhada mais de uma vez.
- 32 ausências e 24 retornos nos ciclos controlados; 11 grupos fotográficos e 7 clipes salvos.
- Nenhum descarte de registros, fotos ou amostras de clipes; nenhuma falha de gravação nesse ensaio.

**Não é teste de longa duração de produção**, benchmark de YOLOX, prova de precisão, medida em RTX nem previsão de desempenho no notebook do usuário. A suíte e este ensaio rodaram em parte simultaneamente no ambiente Linux. Relatório completo: `soak-8-objects.json`.

## O que continua dependendo do teste local

Windows PowerShell/instalador e execução completa em Windows 10/11; hardware de webcam; DVR/RTSP real; inferência YOLOX com os pesos oficiais; aparência/iluminação/oclusões do local; identificação das classes desejadas; falsos eventos por hora e precisão/recall de eventos e autoria. Não houve conjunto de vídeos reais anotados do usuário.

O modo explícito de referências permite executar a comparação sem baixar YOLOX, mas **não detecta pessoas** e não substitui a avaliação do modo completo. `tools/doctor.py` e um modelo que carrega não comprovam acurácia.

## Limites operacionais

Uma câmera ativa, até 8 cadastros, CPU. Cadastro/posição fixos; no mínimo 24×24 pixels para aceitar uma referência, sem promessa de acerto nessa dimensão. Mudança de câmera/luz ou evidência incompleta pode suspender ou abster-se. Itens idênticos não são individualizados. Retirada provável exige revisão humana e não é acusação nem prova.

Clipes amostrados não são gravação contínua; horários reais ficam no sidecar. Discos/filas têm limites; retenção remove dados antigos. Evidências, banco e referências não são criptografados pelo programa. Os hashes não impedem adulteração coordenada de arquivos e metadados por alguém com acesso de escrita.

Não foi feita publicação no GitHub nem alteração de repositório remoto. Esta entrega é o ZIP local, com testes e limitações registrados.

## Conferência final da distribuição

A cópia final do código foi testada novamente numa pasta independente com espaços no caminho: **163 aprovados, 1 ignorado, 0 falhas**, em 61,32 s. O teste ignorado continua sendo a inferência com o modelo YOLOX oficial ausente. Resultado bruto: `validation/packaged-tests.txt` e `validation/packaged-tests.xml`. O manifesto SHA-256 confere os arquivos distribuídos; não é assinatura digital do autor.
