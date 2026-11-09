# Vision Local 4.1.0 — vídeo fluido e detecção conservadora

Correção sobre a Fase 4. Interface nativa, sem dashboard, navegador ou API de IA.

## Começar no Windows

Extraia em uma pasta nova e abra **INICIAR.cmd**. A primeira preparação instala as bibliotecas fixadas e verifica/obtém o modelo oficial. Selecione sua webcam e clique em **Iniciar**.

Para testar a fluidez sem modelo, use **CAMERA_FLUIDA.cmd**. Esse modo abre a câmera sem IA; o botão **Ativar IA** inicia a análise quando o modelo estiver preparado. Esse modo não cria detecções de mentira. A primeira instalação das bibliotecas ainda requer internet.

Para o problema de classificar uma pessoa de coberta como carro: abra **Controles**, escolha **Quarto / escritório**, **Pessoas e objetos (YOLOX)** e **Menos alarmes**, depois **Aplicar**. Isso exclui veículos, exige confirmação e rejeita candidatos ambíguos; NÃO transforma automaticamente a coberta em pessoa. Uma pessoa encoberta pode ficar sem detecção. O score não é uma probabilidade calibrada de acerto.

## O que mudou na fluidez

Antes, a tela grande só recebia o quadro depois da inferência. Agora a captura publica para uma prévia independente, com fila de capacidade um. Uma análise lenta não determina a atualização do vídeo.

- **Ao vivo (fluido)**: imagem recente da câmera. Não recebe caixas antigas.
- **Miniatura da IA**: último quadro realmente analisado, com suas caixas e a idade em milissegundos. Oculta-se se ficar antiga ou pertencer a outra sessão/fonte.
- **Ver caixas (quadro da IA)**: amplia exatamente a imagem analisada. Nesse modo, a atualização acompanha a velocidade da IA, não a câmera.
- **Pausar IA**: suspende detecção, acompanhamento e eventos de visão, sem desligar a câmera.

Nenhum quadro intermediário é inventado, interpolado ou repetido para inflar FPS. A tela informa FPS efetivamente desenhados, FPS recebidos da câmera e análises/s separadamente. A idade é medida após decodificação; NÃO inclui o atraso já introduzido por câmera, DVR, rede ou exposição.

O alvo padrão da prévia é 30 FPS. Isso não obriga o hardware a fornecer 30 FPS. Em fontes migradas, o limite de publicação antigo é preservado: em **Mais → Configurações → Editar fonte**, com a câmera parada, defina publicação 30 se o perfil antigo estava em 15. Resolução, FPS solicitado, formato USB (MJPG/auto/YUY2) e backend também ficam nessa janela. RTSP é configurado no DVR; o aplicativo não muda automaticamente o stream.

## Controles simples, ajustes opcionais

Na tela principal: fonte, iniciar, parar, pausar/ativar IA, controles e registros. Foto e objetos continuam acessíveis. As ferramentas de cadastro, área, linha, amostras, avaliação, backup e exportação permanecem em **Mais**, sem uma segunda tela de dashboard.

**Controles → Básico:** ambiente, detector e presets Menos alarmes / Equilibrado / Mais sensível. Esses presets mudam limiares e confirmação; não alteram o modelo, nem garantem melhor recall.

**Controles → O que detectar:** seleção explícita dentre as 80 categorias, busca e perfil personalizado. Uma categoria rejeitada é descartada ANTES do rastreamento e dos registros. O sistema não escolhe a segunda categoria só porque a primeira foi desabilitada.

**Controles → Ajustes finos:** limiar geral e por categoria, análises/s, threads CPU, folga de processamento, observações e duração para confirmar, separação entre categorias concorrentes, tolerância a score fraco, tempo para expirar IDs, limite de idade da análise, atualização e largura da prévia, visibilidade de candidatos não confirmados.

Aplicar esses controles reinicia apenas a análise em nova sessão. Não reconecta a câmera. Alterações físicas da fonte (resolução, backend, codec) ainda exigem parar/iniciar a fonte.

## Identificação mais conservadora, não identidade civil

O padrão novo é Quarto / escritório, limiar geral 0,60, três observações fortes e pelo menos 0,55 s de suporte temporal. As caixas não confirmadas ficam ocultas por padrão; a opção de diagnóstico permite vê-las explicitamente.

Foi acrescentada uma margem relativa entre a melhor e a segunda categoria: `(melhor - segunda) / melhor`. O valor padrão é 0,15. Se a disputa é ambígua, o candidato é descartado, sem renomeá-lo. Detecções fracas só recuperam IDs confirmados durante um intervalo limitado (1,25 s por padrão), em vez de manter um rótulo errado indefinidamente.

A duração de confirmação reinicia quando o suporte é perdido. Quadros lentos mas regulares não são tratados automaticamente como falhas só porque ficaram abaixo do FPS máximo solicitado.

O modelo continua sendo o mesmo YOLOX-S oficial, com entrada 640×640. Não há novo treinamento, reconhecimento facial, garantia de identificar pessoas sob coberta nem execução automática na RTX. Todos os modos desta entrega continuam em CPU. Reduzir categorias NÃO torna a passagem pela rede neural proporcionalmente mais rápida.

## Atualizar sem perder os dados da versão 4

1. Feche a instalação antiga. Extraia a 4.1 em outra pasta.
2. Prepare apenas o ambiente da nova pasta:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INICIAR.ps1 -CameraOnly -InstallOnly
```

3. Importe (substitua somente o caminho de origem):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\MIGRAR_DADOS.ps1 -Origem "C:\VisionLocal4\vision-phase4"
```

A origem é preservada e o destino com dados é recusado. Banco, registros, referências, evidências e anotações são importados. O script também tenta reutilizar o ONNX anterior, mas somente se tamanho e SHA-256 forem os oficiais; um arquivo inválido nunca é executado ou copiado como modelo válido.

Ao carregar análise de schema 2, o original é preservado em `data/analysis.pre-v4.1.json`. O perfil antigo **Todas** vira **Quarto**, conforme esta correção; limiares, regiões, linhas e demais parâmetros existentes são preservados. Por isso, selecione Menos alarmes para aplicar esse preset a uma configuração antiga. Uma escolha explícita posterior de Todas continua disponível e é preservada. Fontes, credenciais, imagens e banco não são apagados.

## Medições e validação

Leia `docs/TESTES_E_LIMITES.md`. Há testes de política, confirmação, prévia independente, falha da IA, pausa sem desconectar a câmera, compatibilidade de sessão, migração, evidências e funcionalidades anteriores.

Os ensaios de fluidez usam captura sintética 720p/30, janela Tk real e análise artificial: tanto espera de 450 ms quanto carga real de CPU/OpenCV por aproximadamente 450 ms. Isso testa a arquitetura e competição por CPU, NÃO substitui teste com YOLOX, Windows ou câmera física.

Não foi possível baixar os pesos neurais neste ambiente. O teste real de YOLOX permanece ignorado, não disfarçado como aprovado. Também há duas distribuições cv2 no ambiente de validação: a checagem de dependências sinaliza FAIL. A distribuição usa ambiente `.venv` isolado e uma única variante headless, mas a instalação limpa Windows ainda não foi homologada.

## Diagnóstico prático

- Se **Vídeo FPS** acompanha **Câmera FPS** e a IA está mais lenta, a separação está funcionando. As caixas novas dependem da análise.
- Se **Câmera FPS** já está baixo mesmo com IA pausada, investigue modo/resolução/iluminação/driver/transporte. Pedir 30 FPS não confirma que o dispositivo aceitou.
- Se só a imagem analisada está lenta, volte para Ao vivo. Não aumente análises/s esperando criar capacidade de CPU inexistente.
- Uma fotografia manual feita com IA pausada é salva com `analysis_status=NOT_ANALYZED`, sem fingir reconhecimento.
- **Mais → Arquivo → Exportar diagnóstico** inclui o estado da prévia, captura e IA, mas não envia fotos ou credenciais.

Dados ficam em `data/`. Modelo em `models/`. Não comite imagens, credenciais nem dados pessoais. Para encerrar, feche a janela. O aplicativo tenta finalizar captura, IA e gravações antes de sair.
