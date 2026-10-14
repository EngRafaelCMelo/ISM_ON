# Auditoria técnica — Supervisório ISM

Data da auditoria: 14/10/2026  
Base analisada: commit `9ca2eda` do repositório `karenhelloisa98/Supervisorio_ISM`.

## Escopo e entrada real

O aplicativo principal utilizava os módulos da raiz (`mainwindow.py`, `daq_worker.py`, `pump_worker.py`, `oven_worker.py`, `tela_login.py`) e o fluxo de inicialização estava em `main2.py`. O arquivo `SupervisorioISM.spec` apontava para `main.py`, mas no estado original havia apenas `Versão1/main.py`; também referenciava `assets`, enquanto os recursos reais estavam em `Imagens` e nos `.ui` da raiz.

`Versão1` é uma implementação/experimento paralelo. Seus arquivos em `Versão1/tests` são scripts de demonstração, não testes pytest confiáveis. A execução inicial de `python -m pytest` falhou na coleta com `ModuleNotFoundError: No module named 'ui_main'`.

## Problemas confirmados

| ID | Criticidade | Evidência | Impacto | Correção nesta rodada |
|---|---|---|---|---|
| A-01 | Alta | `mainwindow.py` criava quatro curvas fixas e iterava cinco valores; `config.json` contém P1, P2, P3, P4 e DP. | DP podia ser associado à curva errada ou causar inconsistência de índices. | Curvas agora são associadas por nome; P1–P4 ficam no gráfico principal e o canal diferencial possui curva própria. |
| A-02 | Alta | `calculate_permeability_realtime()` buscava `Pu` e `Pd`, inexistentes na configuração. | Permeabilidade não era calculada com o conjunto de canais atual. | Mapeamento explícito `upstream_channel`, `downstream_channel` e `differential_channel` em `config.json`. |
| A-03 | Alta | Valores eram convertidos/apresentados como psi, apesar de `config.json` declarar bar; o cálculo usava fator psi diretamente. | Resultado dimensionalmente incorreto, potencialmente por fator significativo. | `units.py` centraliza conversões e os cálculos usam Pa; a unidade configurada volta apenas na apresentação. |
| A-04 | Alta | Histórico gráfico usava `0.0` para leituras ausentes. | Falhas de sinal pareciam quedas reais de pressão. | Ausências permanecem `None` internamente e viram `NaN` somente no gráfico, produzindo lacunas. |
| A-05 | Alta | `stop()` do DAQ era chamado diretamente pela interface apesar de o worker estar em `QThread`; havia risco de manipular timer/tarefa na thread errada. | Encerramento incompleto, thread órfã ou impossibilidade de reiniciar. | `QMetaObject.invokeMethod(..., QueuedConnection)`, limpeza idempotente e encerramento aguardado. |
| A-06 | Alta | Exceções do DAQ podiam deixar tarefa/timer/logger parcialmente criados. | Recursos não liberados e aquisição duplicada no reinício. | Inicialização com cleanup em erro, estado ativo e `stop()` seguro. |
| A-07 | Média | Bomba e estufa usavam COM5/COM6 fixos e timeout fixo. | Aplicação dependia de uma instalação específica e não sinalizava ausência prolongada de dados. | Portas/baudrate/timeouts em `config.json`, listagem de portas em `serial_utils.py` e estados `DISCONNECTED`, `CONNECTING`, `OK`, `STALE`, `INVALID`, `ERROR`. |
| A-08 | Média | Parsers seriais não tinham cobertura automatizada; comunicação não validava finitude/estado de leituras. | Mensagens incompletas ou valores inválidos podiam entrar no fluxo sem diagnóstico claro. | Parsers preservados e testados; leituras inválidas e stale são sinalizadas. |
| A-09 | Média | `calibration_store.py` gravava diretamente no arquivo final. | Falha durante a gravação podia corromper coeficientes. | Gravação temporária com `fsync` e `os.replace`, com timestamp UTC da alteração. |
| A-10 | Média | CSV registrava correntes e valores de engenharia sem separar bruto, calibrado e status; `None` não era parte do contrato. | Rastreabilidade limitada e risco de interpretar ausência como zero. | Cabeçalho e linhas distinguem mA, bruto, calibrado e status; valores ausentes permanecem vazios. |
| A-11 | Média | Configuração não era validada antes de criar hardware; faixas e nomes podiam divergir. | Erros apareciam tarde e poderiam afetar aquisição. | `config.py` valida taxa, canais únicos, LRV/URV, unidades, mapeamentos e dispositivos. |
| A-12 | Média | `SupervisorioISM.spec` não incluía os recursos reais (`Imagens`, `.ui`) e apontava para entrada inexistente. | Executável poderia abrir sem interface/ícones ou nem iniciar. | Entrada oficial `main.py` adicionada e datas corrigidas no spec. |
| A-13 | Baixa | Artefatos `build`, `dist`, `venv`, `__pycache__` e `logs` estavam acompanhados pelo Git. | Repositório pesado e risco de versionar dados/artefatos locais. | `.gitignore` adicionado; a remoção do acompanhamento preserva os arquivos locais. |

## Riscos preservados deliberadamente

- As faixas de todos os transdutores foram mantidas exatamente como no `config.json`; não há evidência suficiente para alterar os valores físicos.
- Nenhum comando de controle novo foi criado para bomba, estufa ou válvulas; apenas leitura, parser e ciclo de conexão foram tratados.
- O parser serial existente foi mantido em espírito e apenas recebeu validação/estado, pois o protocolo real dos equipamentos não está documentado no repositório.
- Não foi declarado suporte de produção: o funcionamento real depende de Windows, driver NI-DAQmx, hardware NI, portas seriais e testes operacionais.

## Pendências para a próxima rodada

1. Integrar `CalibrationDialog` e `ParamsDialog` ao fluxo principal, sem manter duas fontes de parâmetros.
2. Definir com a engenharia o modelo de fluido e validar a equação para cada tipo de ensaio.
3. Executar testes de integração com NI-DAQmx, Vindum e estufa reais, incluindo desconexão durante operação.
4. Confirmar unidades/faixas dos transdutores e a semântica física de P1–P4/DP.
5. Implementar registro completo de ensaio (ID, temperatura, vazão, estados, parâmetros, configuração e calibração) sem bloquear a UI.
6. Criar build Windows em ambiente com todas as dependências e verificar o executável gerado.
