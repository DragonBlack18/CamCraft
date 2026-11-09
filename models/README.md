# Modelo neural

O peso não está incluído neste ZIP. `INICIAR.cmd` chama `tools/prepare_model.py`, que baixa o arquivo oficial especificado em `manifest.json`, verifica tamanho/SHA-256 e executa uma inferência real no computador de destino. Após a preparação, reutiliza o arquivo local.

Não renomeie outro modelo para este nome. Não use o pequeno arquivo Git LFS como peso: são necessários os bytes binários indicados no manifesto. Em rede corporativa restrita, obtenha esse arquivo oficial por um computador autorizado e copie-o aqui; a verificação continuará obrigatória.

O modelo foi referenciado pela fonte oficial, mas não pôde ser obtido/executado no ambiente onde este ZIP foi desenvolvido.
