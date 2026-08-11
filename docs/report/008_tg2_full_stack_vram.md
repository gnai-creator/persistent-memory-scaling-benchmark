# TG-2 — VRAM total e atribuição da stack

## Objetivo

Registrar simultaneamente o consumo completo da GPU e a parcela atribuível aos
processos do TrustGraph. O experimento compara duas janelas externas de 30
segundos: stack TrustGraph desligada e stack c100k carregada em idle.

O ASM permaneceu em execução e não foi interrompido, reiniciado ou modificado.

## Resultado

| Métrica (média) | Stack desligada | Stack c100k idle |
|---|---:|---:|
| VRAM total do dispositivo | 2,374 GB | 2,329 GB |
| VRAM atribuída ao TrustGraph | 0 B | 0 B |
| VRAM atribuída ao ASM | 0,908 GB | 0,908 GB |
| VRAM atribuída a outros processos | 0,725 GB | 0,681 GB |
| VRAM não atribuída | 0,741 GB | 0,740 GB |
| RAM dos containers TrustGraph | 0 B | 4,270 GB |

Picos observados:

- VRAM total: 2,476 GB com a stack desligada e 2,381 GB com a stack ligada;
- RAM dos containers TrustGraph: 4,304 GB com a stack c100k ligada.

![RAM e VRAM da stack TrustGraph](../screens/tg2-vram-stack-comparison.png)

O gráfico público mostra exclusivamente recursos da stack TrustGraph: RAM dos
containers e VRAM atribuída aos seus processos. VRAM do ASM, desktop, driver e
outros processos permanece nos dados de auditoria, mas foi excluída da figura
para não ser confundida com custo do framework.

### Duas estatísticas de RAM, sem contradição

Este gráfico usa **RAM média dos containers durante uma janela idle de 30 s**:
4,27 GB no c100k. O painel de scaling usa outra estatística, **pico de RAM dos
containers durante a janela carregada**: 4,81 GB no c100k. Média e pico não devem
ser intercambiados; ambos permanecem identificados com duração, fase e unidade.

## Interpretação

O caminho estruturado medido do TrustGraph não criou um processo GPU
identificável, por isso sua VRAM atribuída foi 0 B. Isso não permite subtrair
diretamente os totais do dispositivo: processos externos variaram entre as
janelas e explicam a queda de aproximadamente 45 MB na VRAM total.

As duas grandezas devem permanecer separadas no benchmark:

1. **footprint operacional total** — RAM completa da stack e VRAM completa do
   dispositivo durante a janela;
2. **custo atribuível** — RAM dos containers e VRAM dos PIDs classificados como
   TrustGraph.

Da mesma forma, o delta pareado de aproximadamente 7,3 MB medido no checkpoint
c100k não significa que a stack inteira ocupe apenas 7,3 MB. Ele representa a
diferença entre controle e carga; o footprint idle completo observado foi de
aproximadamente 4,27 GB de RAM de containers.

## Artefatos

- dados: `manifests/tg2-vram-stack-comparison.json`;
- gráfico Matplotlib: `docs/screens/tg2-vram-stack-comparison.png`;
- versão vetorial: `docs/screens/tg2-vram-stack-comparison.svg`;
- gerador: `src/persistent_memory_scaling/trustgraph/vram_plot.py`.

## Limitações

- As janelas são consecutivas, não simultâneas; processos externos podem mudar.
- “Não atribuída” inclui memória reportada pelo dispositivo sem PID computacional
  correspondente na amostra.
- O resultado de 0 B vale para o caminho estruturado e a configuração testada;
  não é uma afirmação universal sobre todos os fluxos do TrustGraph.
