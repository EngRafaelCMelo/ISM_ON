# Supervisório ISM

Aplicação desktop PyQt5 para supervisão de ensaios de coreflooding, com aquisição de pressão por NI-DAQ, comunicação serial com bomba Vindum e estufa, calibração, cálculos científicos e exportação CSV.

Esta primeira rodada estabiliza o software sem alterar as faixas atuais dos transdutores: P1–P4 permanecem em 0–10000 bar e DP em 0–200 bar até validação pelas especificações físicas.

## Requisitos

- Windows para a integração real com NI-DAQmx e equipamentos seriais.
- Python 3.10 ou superior.
- Driver NI-DAQmx e hardware configurado para aquisição real.
- PyQt5, pyqtgraph, NumPy, nidaqmx e pyserial.

Instalação:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

## Execução

```powershell
python main.py
```

O ponto de entrada oficial é `main.py`; `main2.py` permanece como módulo de compatibilidade. A aplicação valida `config.json` antes de abrir o DAQ.

Para testar sem NI-DAQ, bomba ou estufa:

```powershell
python main.py --simulate
```

O título e o status da janela exibem `[MODO SIMULACAO]`. As mensagens geradas carregam `source=SIMULATED` e nunca são misturadas silenciosamente com uma aquisição real.

## Configuração

`config.json` centraliza taxa de aquisição, canais físicos, LRV/URV, unidades, mapeamento de montante/jusante/DP, modelo de fluido, portas seriais e timeouts. As portas atuais COM5/COM6 foram preservadas como valores padrão, mas agora podem ser alteradas no arquivo.

O processamento usa SI internamente. Pressões configuradas em bar são convertidas para Pa nos cálculos e voltam à unidade configurada apenas na apresentação. A lei de Darcy em tempo real é permitida somente para `incompressible_liquid`; ensaios com gás devem usar o modelo pulse-decay e suas hipóteses experimentais.

## Testes

```powershell
python -m pytest
```

Os testes não exigem hardware e cobrem conversão 4–20 mA, pressão, vazão, calibração ZERO/SPAN, porosidade, Darcy, pulse-decay, validação de configuração, CSV, parsers seriais e modo simulação.

## Empacotamento

Com dependências de desenvolvimento instaladas:

```powershell
pyinstaller --clean --noconfirm SupervisorioISM.spec
```

O spec inclui `config.json`, os dois arquivos `.ui`, a pasta `Imagens`, metadados do NI-DAQmx e dependências dinâmicas. Um build não substitui a validação com driver NI-DAQmx, portas COM e equipamentos reais.

## Organização

- `main.py` / `main2.py`: inicialização e ciclo de vida das threads.
- `mainwindow.py`: apresentação e atualização da interface.
- `daq_worker.py`: aquisição NI-DAQ e conversão/calibração dos canais.
- `simulation_worker.py`: fonte sintética explicitamente identificada.
- `pump_worker.py` / `oven_worker.py`: comunicação serial e parsers.
- `units.py`, `calc.py`, `config.py`: unidades, cálculos e validação sem dependência da UI.
- `calibration_store.py`, `logger_csv.py`: persistência e rastreabilidade.
- `tests/`: testes automatizados sem hardware.

## Limitações conhecidas

Ainda é necessária validação operacional com NI-DAQmx, bomba Vindum, estufa, protocolo serial real e especificações físicas dos transdutores. Os diálogos legados de parâmetros/calibração ainda não estão conectados ao fluxo principal de `main.py` e devem ser integrados em uma próxima rodada, com revisão de permissões e rastreabilidade do ensaio.
