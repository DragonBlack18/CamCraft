# COCO contiguous class order; names translated for the local interface.
NAMES = ('pessoa','bicicleta','carro','motocicleta','avião','ônibus','trem','caminhão','barco',
'semáforo','hidrante','placa de parada','parquímetro','banco','pássaro','gato','cachorro','cavalo',
'ovelha','vaca','elefante','urso','zebra','girafa','mochila','guarda-chuva','bolsa','gravata','mala',
'frisbee','esquis','snowboard','bola','pipa','taco de beisebol','luva de beisebol','skate',
'prancha de surfe','raquete','garrafa','taça','xícara/copo','garfo','faca','colher','tigela',
'banana','maçã','sanduíche','laranja','brócolis','cenoura','cachorro-quente','pizza','rosquinha',
'bolo','cadeira','sofá','planta em vaso','cama','mesa','vaso sanitário','televisor','notebook',
'mouse','controle remoto','teclado','celular','micro-ondas','forno','torradeira','pia','geladeira',
'livro','relógio','vaso','tesoura','urso de pelúcia','secador','escova de dentes')
INDOOR = frozenset([0,15,16,24,25,26,27,28,39,40,41,42,43,44,45,*range(56,80)])
BEDROOM = frozenset([0,15,16,24,26,28,39,41,56,57,58,59,60,62,63,64,65,66,67,73,74,75,76,77,79])

def allowed(mode: str, custom=()):
    if mode == 'people': return {0}
    if mode == 'indoor': return INDOOR
    if mode == 'bedroom': return BEDROOM
    if mode == 'custom': return frozenset(custom)
    if mode == 'all': return frozenset(range(80))
    raise ValueError('Perfil de categorias desconhecido.')
