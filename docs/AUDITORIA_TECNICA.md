# Auditoria tecnica - Supervisorio ISM

Data da base original: 14/10/2026. O projeto foi estabilizado em duas etapas sobre a arquitetura PyQt5 existente. As faixas dos transdutores foram preservadas: P1-P4 em 0-10000 bar e DP em 0-200 bar.

## Achados da Etapa 1

| ID | Severidade | Problema | Tratamento |
|---|---|---|---|
| A-01 | Alta | Curvas e valores podiam associar DP ao indice errado. | Mapeamento por nome e curvas por canal. |
| A-02 | Alta | Mapeamento Pu/Pd nao correspondia ao config. | Montante/jusante/DP explicitos em `config.json`. |
| A-03 | Alta | Mistura de bar/psi e calculo fora de SI. | Conversoes centralizadas e calculo em Pa. |
| A-04 | Alta | Falhas apareciam como zero. | `None` no processamento e `NaN` no grafico. |
| A-05 | Alta | Stop podia manipular timer/DAQ na thread errada. | Stop enfileirado, cleanup idempotente e espera. |
| A-06 | Alta | Falhas deixavam tarefa/logger parcialmente vivos. | Cleanup em erro e fechamento seguro. |
| A-07 | Media | COM5/COM6 e timeouts eram fixos. | Configuracao e listagem de portas. |
| A-08 | Media | Parsers e estados seriais sem cobertura. | Parsers testados e estados explicitos. |
| A-09 | Media | Calibracao podia corromper no write direto. | Write atomico, timestamp e backup. |
| A-10 | Media | CSV nao separava bruto/calibrado/status. | Colunas distintas e vazios preservados. |
| A-11 | Media | Configuracao nao era validada no inicio. | Validacao de canais, faixas, unidades e dispositivos. |
| A-12 | Media | Empacotamento nao carregava recursos corretos. | `main.py`, `.ui`, `Imagens` e dependencias no spec. |
| A-13 | Baixa | Artefatos locais estavam no Git. | `.gitignore` e desindexacao sem apagar arquivos locais. |

## Implementacoes da Etapa 2

| ID | Implementacao | Evidencia |
|---|---|---|
| E2-01 | Maquina `STOPPED`, `STARTING`, `RUNNING`, `STOPPING`, `ERROR`; `RUNNING` depende do worker. | `operation_state.py`, `acquisition_controller.py`. |
| E2-02 | Nova `QThread`/worker por partida, stop enfileirado e sem `terminate()`. | `acquisition_controller.py`, teste Qt de start/stop. |
| E2-03 | Calibracao no menu, leitura atual, captura sem dado desabilitada, confirmacao/backup/timestamp. | `mainwindow.py`, `calibration_dialog.py`. |
| E2-04 | Parametros editados no dialogo retornam para os campos usados pelos calculos. | `params_dialog.py`, `mainwindow.py`. |
| E2-05 | DP medido e DP calculado separados em labels, curvas e registros. | `mainwindow.py`, `session_manager.py`. |
| E2-06 | Portas/baudrate/timeout/stale editaveis; estados e reconexao com backoff. | `serial_settings_dialog.py`, workers seriais. |
| E2-07 | Graficos usam timestamp, janelas temporais, buffer limitado e downsampling. | `mainwindow.py`. |
| E2-08 | Ensaio isolado com metadata, CSV, eventos e origem REAL/SIMULATED. | `session_manager.py`, `session_dialog.py`. |
| E2-09 | Eventos e alarmes centralizados para DAQ, sensores e serial. | `events.py`, `main2.py`. |
| E2-10 | Login local sem credencial fixa, PBKDF2-SHA256 com salt e perfis. | `auth.py`, `tela_login.py`. |

## Testes executados

- `python -m pytest -q`: 21 testes aprovados.
- `python -m py_compile` nos modulos principais: aprovado.
- Smoke test Qt offscreen: janela, timestamps, curvas DP distintas e modo simulado.
- Smoke test do controlador: `STARTING -> RUNNING -> STOPPING -> STOPPED`.

## Riscos e limites conhecidos

- A leitura serial continua sem comandos de atuacao; o protocolo real precisa ser confirmado com fabricante.
- A UI valida fluxos, mas nao substitui intertravamentos fisicos.
- O modelo de permeabilidade e valido apenas dentro das hipoteses registradas em `calc.py` e no config.
- O login local possui primeiro administrador, mas criacao administrativa de operadores ainda e procedimento controlado fora da UI.

## Pendente de homologacao em hardware

1. Driver NI-DAQmx, tarefa real, canais fisicos e comportamento de desconexao.
2. Identificacao/baudrate/formato das mensagens da bomba Vindum e estufa.
3. Confirmacao metrologica das faixas/unidades e calibracao ZERO/SPAN.
4. Conferencia fisica de P1/P2/P3/P4/DP e comparacao DP medido versus calculado.
5. Validacao da permeabilidade com fluido, viscosidade e procedimento aprovados.
6. Execucao do checklist em `docs/TESTES_HARDWARE.md` com evidencias.
