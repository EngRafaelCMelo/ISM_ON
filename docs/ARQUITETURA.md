# Arquitetura operacional

## Camadas

- `main.py` / `main2.py`: inicializacao, autenticacao e composicao dos componentes.
- `mainwindow.py`: apresentacao, selecao de fonte e comandos; nao acessa hardware diretamente.
- `acquisition_controller.py`: ciclo de vida de um worker e de uma `QThread` nova por partida.
- `daq_worker.py` / `simulation_worker.py`: fontes de dados com payload nomeado por canal.
- `pump_worker.py` / `oven_worker.py`: threads seriais, parser, estado e reconexao com backoff.
- `units.py`, `calc.py`: conversoes SI e calculos sem dependencia da UI.
- `calibration_store.py`, `config.py`, `auth.py`: persistencia atomica e validada.
- `session_manager.py`, `events.py`: rastreabilidade assincrona de ensaio e eventos.

## Estado da aquisicao

```text
STOPPED -> STARTING -> RUNNING -> STOPPING -> STOPPED
              |           |           |
              +--------> ERROR <-----+
```

O clique de inicio so entra em `STARTING`. A transicao para `RUNNING` ocorre exclusivamente no sinal `started` do worker. O clique de parada entra em `STOPPING` e a conclusao do worker e que retorna para `STOPPED`. Um erro impede que a UI apresente uma aquisicao como valida.

Cada partida cria um novo `QThread` e um novo worker. O encerramento usa `stop()` enfileirado e espera a thread; `terminate()` nao e usado como rotina.

## Payload de aquisicao

Cada amostra possui `ts`, `timestamp_ms`, `source`, `simulated` e `channels`. Cada canal possui `mA`, `eng_raw`, `eng`, `status` e `unit`. `None` representa leitura ausente/invalida; graficos convertem essa ausencia para `NaN` apenas na camada visual.

## DP e tempo

O canal diferencial configurado representa `DP medido`. `DP calculado` e a diferenca em Pa entre os canais configurados como montante e jusante. Ambos sao armazenados, exibidos e desenhados em curvas distintas.

O eixo X usa `timestamp_ms` da fonte e tempo decorrido desde a primeira amostra da partida. O historico e limitado por `plot.max_history_s` e a renderizacao e reduzida a no maximo 2000 pontos por curva.

## Ensaio

`SessionRecorder` cria um diretorio unico, escreve metadata/configuracao/calibracao, recebe amostras em fila e grava `measurements.csv`/`events.log` em thread separada. A origem `REAL` ou `SIMULATED` acompanha o ensaio e a metadata.
