# Checklist de homologacao em hardware

Este checklist nao foi executado neste ambiente. Cada item precisa de evidencia registrada pelo responsavel tecnico.

## Preparacao

- [ ] Confirmar versao do Windows, driver NI-DAQmx e permissao do usuario.
- [ ] Confirmar fisicamente P1, P2, P3, P4 e DP, LRV/URV e unidade.
- [ ] Confirmar `cDAQ1Mod3/ai*` e faixa de corrente 4-20 mA.
- [ ] Identificar portas COM reais da bomba Vindum e estufa.
- [ ] Confirmar baudrate, terminadores e formato das mensagens com a documentacao do fabricante.
- [ ] Fazer backup de `config.json` e `calibration.json`.

## DAQ

- [ ] Iniciar aquisicao e verificar `STARTING` -> `RUNNING`.
- [ ] Confirmar que cada canal aparece no nome correto.
- [ ] Aplicar corrente proxima de 4 mA, 20 mA, abaixo de 3,6 mA e acima de 21 mA.
- [ ] Confirmar estados `OPEN_LOOP`, `OVERRANGE`, `INVALID` e lacuna no grafico.
- [ ] Parar, reiniciar varias vezes e fechar com aquisicao ativa.
- [ ] Desconectar o dispositivo e confirmar `ERROR`/liberacao da tarefa.

## Serial

- [ ] Conectar bomba/estufa e confirmar `CONNECTING` antes da primeira leitura.
- [ ] Confirmar `OK` somente apos mensagem valida.
- [ ] Enviar mensagem invalida e confirmar `INVALID`.
- [ ] Interromper dados e confirmar `STALE` apos o tempo configurado.
- [ ] Desconectar/reconectar e confirmar backoff sem threads duplicadas.
- [ ] Confirmar que nenhum comando de atuacao e emitido.

## Calibracao e ensaio

- [ ] Executar ZERO/SPAN com referencia rastreavel.
- [ ] Conferir backup, timestamp e aplicacao apos reinicio controlado.
- [ ] Criar ensaio real e conferir metadata, CSV, eventos e encerramento.
- [ ] Confirmar que uma sessao real nao recebe payload simulado.
- [ ] Conferir DP medido contra o transdutor e DP calculado contra Pmontante-Pjusante.
- [ ] Confirmar calculo de permeabilidade com unidade/modelo aprovados pela engenharia.

## Evidencias

- [ ] Anexar logs, CSV, metadata, versao do commit e fotos/identificacao do setup.
- [ ] Registrar aprovacao ou pendencia por item; nao declarar homologacao apenas com o modo simulado.
