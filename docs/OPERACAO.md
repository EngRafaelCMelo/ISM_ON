# Procedimento de operacao

## Primeiro acesso

Na primeira abertura, informe um usuario e uma senha com pelo menos oito caracteres para criar o administrador. Nao existe senha padrao. Para criar operadores adicionais, use a API local `UserStore.create_user(..., role="operator")` em procedimento administrativo controlado; nao edite hashes manualmente.

## Inicializacao e parada

1. Confira `config.json`, portas e a origem de dados.
2. Faça login.
3. Inicie o sistema.
4. Aguarde o indicador `RUNNING`; `STARTING` significa que o worker ainda nao confirmou a fonte.
5. Para parar, clique uma vez e aguarde `STOPPED`.
6. Em `ERROR`, pare/recupere de forma controlada e reinicie somente depois de a thread anterior ter terminado.

## Calibracao

Somente administrador pode abrir a tela de calibracao e a aquisicao deve estar parada. A tabela mostra RAW/corrigido, permite capturar ZERO e SPAN, calcula `a`/`b` e exibe a data da ultima gravacao. Sem leitura valida, captura fica desabilitada. Cada salvamento pede confirmacao, cria backup e grava atomicamente. Depois de calibrar, recarregue/reinicie a aquisicao para aplicar os coeficientes de forma controlada.

## Parametros

O menu `Operacao > Parametros do ensaio` edita os mesmos campos usados pela tela principal: diametro, comprimento, viscosidade, vazao/temperatura manuais e mapeamento upstream/downstream. A tela principal e a origem usada nos calculos; o dialogo apenas edita e devolve os valores.

## Bomba e estufa

Abra `Operacao > Comunicacao serial` com bomba e estufa desconectadas. As portas detectadas aparecem em combos editaveis. Baudrate, timeout e stale sao persistidos com backup de `config.json`. A porta aberta nao e considerada leitura valida: o estado permanece `CONNECTING` ate uma mensagem valida. Erros acionam reconexao com backoff; nao ha comandos de atuacao.

## Registro de ensaio

Inicie a aquisicao, clique `Iniciar Experimento`, informe identificador/amostra/operador/observacoes/tipo e confirme. O diretório criado contem:

```text
ensaios/
└── 2026-10-14_amostra_001_xxxxxxxx/
    ├── metadata.json
    ├── measurements.csv
    └── events.log
```

O CSV preserva canais, mA, bruto, calibrado, status, DP medido/calculado, vazao, temperatura e permeabilidade. Um erro encerra o registro de forma segura e preserva o que ja foi enfileirado.
