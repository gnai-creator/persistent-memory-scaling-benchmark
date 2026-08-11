# TG-1 — resultado oficial de instrumentação

**Data:** 11 de agosto de 2026
**Estado:** gate aprovado para a trilha estruturada

## Protocolo aceito

Foram executados três ciclos independentes (`tg1-official-v2-r1..r3`). Cada
ciclo usou volumes novos, confirmou Pulsar, Cassandra, API e flow, estabilizou
por pelo menos 60 segundos e verificou novamente o crescimento físico durante
15 segundos. Depois mediu uma janela vazia e uma janela carregada de 30 segundos
cada. O valor oficial é:

```text
delta pareado = delta carregado - delta do controle vazio de mesma duração
```

O ciclo era rejeitado se o controle crescesse mais de 8 MiB, se qualquer um dos
21 containers reiniciasse, se o armazenamento não estivesse quiescente ou se a
auditoria dos eventos falhasse. As três repetições passaram sem alteração dos
critérios. Calibrações anteriores e `tg1-official-r1` foram excluídas porque
usavam uma versão anterior do protocolo.

## Resultado pareado — 100 eventos

| Métrica | r1 | r2 | r3 | média | IC95% |
|---|---:|---:|---:|---:|---:|
| RAM dos containers | 466.756.830 B | 460.965.543 B | 457.007.173 B | 461.576.515 B | [449.394.663; 473.758.368] B |
| volumes físicos | 5.423.104 B | 5.423.104 B | 5.414.912 B | 5.420.373 B | [5.408.623; 5.432.123] B |

O custo observado nesse checkpoint equivale a aproximadamente 54.204 bytes
físicos/evento. O delta de RAM equivale a 4,62 MB/evento apenas neste pequeno
checkpoint e **não deve ser extrapolado linearmente**: ele inclui caches,
allocators e estado de runtime. Os checkpoints de TG-2 determinarão a derivada
de escala.

O controle vazio cresceu somente 45.056, 53.248 e 49.152 B. A verificação de
quiescência anterior ao baseline mediu exatamente 28.672 B nos três ciclos,
muito abaixo da tolerância congelada.

## CPU, RAM residente e consulta estruturada

Durante a ingestão, a soma de CPU dos containers teve média entre repetições de
92,14% e pico médio de 457,53%. Percentuais acima de 100% representam uso de
múltiplos cores somado pelo Docker. A RAM média total foi 4.853.081.764 B no
carregado contra 4.398.167.098 B no controle vazio.

Cada repetição executou 100 consultas cold e 100 warm:

| Estado | latência média | IC95% da média | p95 médio |
|---|---:|---:|---:|
| cold | 41,604 ms | [40,891; 42,317] ms | 41,973 ms |
| warm | 41,285 ms | [41,127; 41,442] ms | 41,903 ms |

## VRAM atribuída

TrustGraph registrou pico de **0 B** nas doze janelas oficiais (vazio,
carregado, cold e warm em três repetições). Isso é esperado para a trilha
estruturada, que não invoca o modelo de linguagem nem embeddings durante essas
operações.

O processo ASM permaneceu em execução e apresentou média constante de
908.066.816 B. Essa VRAM foi classificada como `asm`, nunca como TrustGraph. O
benchmark somente leu `nvidia-smi`, PID, `/proc` e cgroups; não encerrou,
reiniciou, limitou ou modificou o ASM.

## Decisão do gate

TG-1 está aprovado para CPU, RAM, disco físico, I/O, rede, Prometheus e VRAM
atribuída da trilha estruturada. Bytes físicos e dados lógicos permanecem
separados. Keyword/FTS não foi habilitado nesta configuração e será medido quando
uma variante que o use entrar no TG-3.

O próximo gate é TG-2: workload determinístico, auditoria de conteúdo e curvas
em múltiplos checkpoints. O resultado de 100 eventos aqui valida o instrumento;
não constitui ainda uma conclusão de scaling sobre TrustGraph ou ASM-CM.
