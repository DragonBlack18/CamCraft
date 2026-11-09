# CamCraft 4.2 — Windows, offline e migração

## Portátil

Baixe `CamCraft-Portable-4.2.0-x64.exe`, coloque em uma pasta sua (por exemplo Documentos\CamCraft) e abra. Não requer instalação nem administrador. Sua pasta `CamCraft-data` fica ao lado do executável. Para mover o aplicativo com seus registros, mova o EXE **e essa pasta** juntos, com o programa fechado.

O runtime e modelo são extraídos temporariamente pelo PyInstaller. Isso custa tempo na abertura e espaço temporário, mas não torna a análise dependente de Python instalado. Não grave o portátil em uma pasta sem permissão de escrita. É possível escolher outra pasta de dados com `--data-dir "D:\CamCraft-data"` ou `CAMCRAFT_DATA_DIR`.

## Setup

Execute `CamCraft-Setup-4.2.0-x64.exe`. Instalação por usuário, sem elevação obrigatória. Programa em `%LOCALAPPDATA%\Programs\CamCraft`, dados em `%LOCALAPPDATA%\CamCraft\data`. O atalho da área de trabalho é opcional. Não cria serviço, tarefa agendada ou inicialização automática.

Desinstalar remove o aplicativo e os atalhos, preservando os dados. A reinstalação pode reutilizá-los. Não altere/remova `installed.marker` da pasta instalada: ele define a separação entre programa e dados.

## Sem dependências externas de aplicativo

Incluídos: runtime Python, OpenCV, NumPy, SciPy, Pillow, Pydantic, psutil, Tcl/Tk, bibliotecas nativas necessárias e modelo ONNX oficial. Não há download de modelo no EXE. Um modelo ausente/corrompido é um pacote incompleto: reinstale a distribuição íntegra, em vez de aceitar um arquivo arbitrário.

Necessários: Windows x64 suportado, driver/permissão da câmera e hardware suficiente. RTSP/HTTP precisa de acesso à câmera na rede. Não há garantia para hardware proprietário sem driver/protocolo compatível. A GPU não é utilizada automaticamente.

## Importar a versão anterior

Feche ambas as versões e não inicie o monitoramento na nova pasta antes de importar. O destino precisa estar vazio. Exemplos (substitua apenas os caminhos):

```powershell
# Portátil: comando interno ao executável, não depende de Python.
& '.\CamCraft-Portable-4.2.0-x64.exe' --tool import-previous --source 'C:\VisionLocal\data' --destination '.\CamCraft-data'

# Setup: destino padrão da instalação por usuário.
& "$env:LOCALAPPDATA\Programs\CamCraft\CamCraft.exe" --tool import-previous --source 'C:\VisionLocal\data' --destination "$env:LOCALAPPDATA\CamCraft\data"
```

Não sobrescreve dados. Copia configurações, SQLite por backup consistente, referências, evidências e amostras. Não copia `.venv`, nem instala bibliotecas. O modelo já está incluído na distribuição. Credenciais DPAPI só funcionam na conta/PC compatível; em outra máquina será necessário cadastrar novamente o endereço da câmera.

## Diagnóstico do pacote

```powershell
$p = Start-Process '.\CamCraft-Portable-4.2.0-x64.exe' -ArgumentList '--self-test --report "C:\Temp\camcraft-selftest.json" --seconds 15' -Wait -PassThru
$p.ExitCode
```

O teste carrega o modelo real, executa inferência sobre imagem neutra, testa fonte sintética, interface, codecs, banco e processos. Não usa sua câmera, não envia imagens e não mede acurácia. Um diagnóstico pode demorar mais em CPU lenta. O relatório distingue erro de execução de precisão não medida.

## Segurança e limites

Sem assinatura Authenticode nesta versão. Confira os hashes e baixe pelo repositório correto. Não é necessário desativar antivírus/SmartScreen. Dados e imagens são locais; imagens não têm criptografia própria do aplicativo. Use permissões da conta e criptografia de disco quando necessário. Não exponha credenciais RTSP em issues públicas.

A visualização fluida e a frequência de inferência são medidas separadamente. A precisão depende de pixels úteis, iluminação, oclusão e exemplos reais. Use perfil Quarto ou Só pessoas para o ambiente apropriado; desabilitar categorias não corrige o modelo e pode reduzir recall.
