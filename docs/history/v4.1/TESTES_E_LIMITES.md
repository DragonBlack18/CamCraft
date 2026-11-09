# Vision Local 4.1.0 — testes executados e limites

Data da entrega: 9 de novembro de 2026. Base: Fase 4 v4.0.0.

## Resultado final reproduzível

**267 testes aprovados, 1 ignorado, 0 falhas**, em **74,49 segundos**. A execução final foi feita em uma cópia nova com espaços no caminho (`verify v4.1 fresh path`), usando Python 3.13.5 em Linux. Evidências: `validation/fresh-path-tests.txt` e `validation/fresh-path-tests.xml`.

O teste ignorado é `tests/test_detection.py`: inferência com os pesos oficiais reais de YOLOX. O arquivo ONNX não estava disponível e o acesso para obtê-lo falhou neste ambiente. Portanto, NÃO foi medida a precisão neural, a classificação de alguém de coberta, nem o desempenho do YOLOX na CPU/GPU do usuário.

A suíte anterior a esta correção tinha 233 testes aprovados e um ignorado. Durante a revisão, uma asserção esperava o padrão antigo de confiança 0,45: ela foi atualizada para o padrão deliberadamente novo de 0,60, mantendo a verificação de cópia defensiva. O primeiro resultado permanece em `validation/tests-first.txt`, identificado como intermediário. Os resultados de 265 testes em `tests-final.txt` são anteriores aos dois testes adicionais de reaproveitamento seguro do modelo; o resultado definitivo é `fresh-path-tests.txt` (267).

### Cobertura nova e preservada

A suíte exercita política Quarto/personalizada, migração e cópia original da configuração, descarte de veículos antes do rastreamento, não promover a segunda categoria quando a primeira é proibida, rejeição de pontuações ambíguas, limiares por categoria, confirmação temporal, expiração do suporte fraco, ocultação de candidatos não confirmados e acompanhamento com análise lenta.

Exercita também prévia independente com análise lenta ou reiniciada, pausa/retomada da IA sem desligar a câmera, descarte de quadros antigos, restrição por sessão, formato/tamanho da prévia, fonte atualizada sem fila crescente, captura e evidências, registros, revisão, anotações, avaliação, exportações, backups e funções das fases anteriores.

As saídas do detector nos testes de política são controladas: não são previsões feitas pelo modelo real. Os testes de reaproveitamento do modelo usam conteúdo simulado e verificador injetado para testar a cópia/recusa; em produção a checagem exige tamanho e SHA-256 oficiais.

## Janela nativa e medição de fluidez

A janela real Tkinter foi aberta via Xvfb. A fonte era um vídeo sintético 1280×720 a 30 FPS. Foram verificadas a janela compacta 760×480, a janela de controles, aplicação sem reconectar a fonte, pausa da IA, manutenção do vídeo, alternância das duas visualizações, fotografia sem análise e encerramento dos processos.

Não houve câmera física, navegador ou imagem de pessoas. Os screenshots são capturas reais da janela de teste, identificada como teste sintético.

### Ensaio com trabalho real de CPU, sem rede neural

Em `tools/validate_v41_gui.py --cpu-stress --measure-seconds 45`, o worker de validação executa repetidamente GaussianBlur do OpenCV por aproximadamente 450 ms por análise, com duas threads. A injeção está somente no validador; não é um detector fictício disponibilizado no fluxo normal.

| Métrica | Resultado |
|---|---:|
| Janela de medição após aquecimento | 45.015 s |
| FPS efetivamente desenhados no vídeo ao vivo | 28.257 |
| FPS preparados no worker da prévia | 29.124 |
| Análises artificiais por segundo | 1.400 |
| Erros de prévia | 0 |
| Capacidade da fila de prévia | 1 quadro |
| P95 da idade interna amostrada do quadro | 78.790 ms |
| Pico da soma de RSS dos processos | 557.77 MiB |
| P95 do intervalo do callback de teste | 19.669 ms |
| Duração do fluxo completo de interface | 55.961 s |

Fonte dos números: `validation/cpu-stress/v41-native-gui.json`. Há aproximadamente 90 amostras. RSS somado pode contabilizar páginas compartilhadas mais de uma vez e não representa memória privada exclusiva. A idade começa após a decodificação: não mede exposição, transporte, buffers do DVR nem câmera→tela.

Esse resultado demonstra separação dos fluxos e comportamento sob a carga artificial utilizada. NÃO garante 28 FPS na máquina do usuário, estabilidade de dias, precisão ou capacidade de análise de todos os quadros. Uma carga neural/hardware diferentes podem produzir outros resultados.

Um segundo teste, com espera artificial de 450 ms em vez de carga CPU, mediu 28,696 FPS pintados e 1,398 análise/s durante 15,019 s. Evidência: `validation/v41-native-gui.json`.

## Ambiente e instalação

- Linux x86_64; Python 3.13.5; OpenCV 4.13.0; NumPy 2.3.5; SciPy 1.17.0; Pillow 12.3.0; Pydantic 2.13.5; psutil 7.2.2; Tk 8.6.
- O ambiente fornecido contém metadados de **opencv-python e opencv-python-headless simultaneamente**. `tools/doctor.py` sinalizou **FAIL** para esse conflito; resultado em `validation/environment-check.txt`. Aprovação dos testes de código não elimina esse problema de empacotamento.
- O pacote prevê instalação em `.venv` própria com uma única variante headless. A instalação limpa Windows não foi executada/homologada aqui. O PowerShell e dispositivos físicos do usuário não estão disponíveis neste ambiente.
- Um smoke headless de câmera sintética, sem IA, foi executado e encerrou normalmente: `validation/headless-camera-only.txt`.
- O modelo continua sendo YOLOX-S CPU, sem mudança dos pesos. Não há treinamento novo nem CUDA/RTX ativados.

## O que mudou e o que não se pode concluir

A imagem principal agora independe da inferência; ela não recebe caixas antigas. A miniatura e o modo Ver caixas mostram exatamente o quadro analisado e sua idade. Aplicar controles reinicia somente a análise. O vídeo não para por opção de pausa da IA.

Quarto exclui veículos. Isso resolve a autorização para exibir/logar a classe carro nesse perfil, mas **não comprova que a pessoa de coberta será reconhecida**. Pode não haver detecção. Confiança e margem não são probabilidades calibradas. Configurações mais conservadoras podem reduzir falsos alarmes e também perder pessoas verdadeiras, sobretudo encobertas ou pequenas.

As fontes migradas mantêm seu limite de publicação (por exemplo, 15 FPS); ele pode ser alterado em Mais → Configurações → Editar fonte, com a fonte parada. O programa não pode obrigar uma câmera/driver a produzir uma taxa que não aceita. O perfil antigo Todas muda para Quarto na migração de schema 2, com cópia original; limiares e geometrias preexistentes são preservados.

## Verificação sugerida no hardware real

1. Extraia em pasta nova e teste `CAMERA_FLUIDA.cmd`. Compare Vídeo FPS com Câmera FPS, sem IA. Isso isola fonte/driver da análise.
2. Prepare o modelo com `INICIAR.cmd`. Em Controles, escolha Quarto, YOLOX e Menos alarmes. Observe Ao vivo, e compare também a velocidade na miniatura da IA.
3. Teste pessoa visível, pessoa parcialmente encoberta e quarto sem pessoas, separadamente. Marque erros/inconclusivos; não avalie só exemplos fáceis.
4. Alterne Pausar IA e retomar. A câmera deve continuar aberta. Ajuste só um parâmetro por vez e exporte o diagnóstico para comparar.
5. Para medir precisão, use amostras anotadas manualmente, incluindo negativos. Uma ausência de alarmes com o detector desativado não é precisão alta.

## Integridade da entrega

`MANIFEST.sha256.json` descreve os arquivos distribuídos. `tools/verify_release.py` confere os hashes. O ZIP não inclui ambiente virtual, dados pessoais, credenciais, vídeos do usuário nem pesos ONNX. O hash ajuda a detectar alterações, mas não autentica o autor nem constitui assinatura digital.

Os resultados de fases anteriores foram movidos para `docs/history/phase4/` e não devem ser confundidos com a validação da 4.1.
