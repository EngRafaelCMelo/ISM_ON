# Supervisorio ISM

Aplicacao desktop PyQt5 para supervisao de ensaios de coreflooding, com aquisicao de pressao por NI-DAQmx, comunicacao serial com bomba/estufa, calibracao, calculos, graficos temporais e registro rastreavel de ensaios.

Esta etapa preserva as faixas existentes de `config.json` (P1-P4: 0-10000 bar; DP: 0-200 bar) e nao cria comandos de atuacao para os equipamentos.

## Requisitos

- Windows para NI-DAQmx e equipamentos reais.
- Python 3.10+.
- PyQt5, pyqtgraph, NumPy, nidaqmx e pyserial.
- Para testes/build: `pytest` e `pyinstaller`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

## Execucao

```powershell
python main.py
```

No primeiro acesso, o sistema solicita a criacao do primeiro administrador. Use uma senha com pelo menos oito caracteres. O arquivo `users.json` e local, usa PBKDF2-SHA256 com salt e nao deve ser versionado.

Para operar sem NI-DAQ, bomba ou estufa:

```powershell
python main.py --simulate
```

O modo simulado aparece no titulo, nos payloads e no metadata dos ensaios. Dados simulados nunca sao misturados silenciosamente com ensaios reais.

## Operacao integrada

1. Confirme o login.
2. Inicie o sistema e aguarde o estado `RUNNING`; esse estado so e emitido apos confirmacao do worker.
3. Use o menu `Operacao` para abrir parametros, calibracao ou comunicacao serial.
4. Conecte bomba/estufa somente depois de conferir portas e baudrate.
5. Clique em `Iniciar Experimento`, informe os metadados e encerre o registro ao final.
6. Pare o sistema e aguarde `STOPPED` antes de fechar ou alterar calibracao/configuracao.

DP medido e DP calculado permanecem separados na tela e no CSV. A fonte usada na permeabilidade pode ser selecionada na combobox existente. O mapeamento de montante/jusante continua em `config.json` e nao presume a ordem fisica dos canais.

## Persistencia

- `config.json`: canais, faixas, unidades, mapeamento, dispositivos, janelas de grafico e parametros cientificos canonicos.
- `calibration.json`: coeficientes e volumes; salvamentos sao atomicos e criam backup.
- `users.json`: usuarios locais e perfis `admin`/`operator`.
- `ensaios/<data>_<amostra>_<id>/`: `metadata.json`, `measurements.csv` e `events.log`; a origem `REAL`/`SIMULATED` e validada por amostra.
- `logs/events.log`: eventos e alarmes globais em JSON Lines, com timestamp, origem, severidade e codigo.
- `logs/`: CSV legado do worker DAQ, mantendo mA, bruto, calibrado e status.

No executavel empacotado, `config.json` e os dados locais sao copiados para a pasta `data/` ao lado do `.exe`, evitando gravacao em `_MEIPASS` temporario.

## Testes e build

```powershell
python -m pytest -q
python -m py_compile operation_state.py auth.py events.py session_manager.py session_dialog.py serial_settings_dialog.py acquisition_controller.py mainwindow.py main2.py
pyinstaller --clean --noconfirm SupervisorioISM.spec
```

A suíte local possui 30 testes automatizados e nao depende de NI-DAQmx nem de portas seriais reais.

Os testes nao dependem de NI-DAQ ou portas seriais reais. O build Windows ainda precisa ser validado no computador de operacao.

## Documentacao

- [Arquitetura](docs/ARQUITETURA.md)
- [Operacao](docs/OPERACAO.md)
- [Checklist de testes de hardware](docs/TESTES_HARDWARE.md)
- [Auditoria tecnica](docs/AUDITORIA_TECNICA.md)

## Limitacoes e homologacao

O modo simulacao e funcional para validar fluxo, estados, graficos, persistencia e calculos. Ainda nao e evidencia de funcionamento industrial. Permanecem pendentes: driver NI-DAQmx, canais fisicos, protocolo serial Vindum/estufa, unidades/faixas confirmadas pela engenharia, comportamento em desconexao real e validacao metrologica da calibracao/permeabilidade.
