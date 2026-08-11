# TG-1 — janelas pareadas e atribuição de GPU

**Data:** 11 de agosto de 2026
**Estado:** controle implementado; gate ainda aberto

## Mudanças

- amostragem contínua em janela, em vez de snapshot único;
- mínimo, média e pico de RAM e VRAM;
- lista de processos GPU com PID, nome e bytes;
- delta por container e por volume;
- classificação explícita de infraestrutura compartilhada e backends da
  collection;
- agregador de repetições com média, desvio padrão e IC95% de Student.

## Primeira janela pareada

As duas janelas tiveram 10 segundos e três amostras externas:

| Estado | RAM média | RAM mínima | RAM máxima |
|---|---:|---:|---:|
| carregado, 100 eventos | 4.334.222.486 B | 4.333.068.353 B | 4.335.129.853 B |
| vazio | 4.440.775.285 B | 4.437.195.099 B | 4.443.548.418 B |

O vazio mediu aproximadamente 106,6 MB a mais que o carregado. Isso não indica
que inserir dados reduz RAM. Indica que restart, aquecimento, compaction, caches
e momento da coleta dominam o sinal de apenas 100 eventos. Portanto, subtrair
dois snapshots isolados não é uma estimativa aceitável de RAM/evento.

## Atribuição de GPU

A coleta por processo mostrou que a maior alocação observada durante as janelas
era de outro processo do host:

```text
../ASM/.venv/bin/python: 908.066.816 B
```

Também havia VS Code, Chrome e processos do desktop usando a GPU. Nenhum processo
TrustGraph/Ollama estava carregado na GPU durante a janela idle carregada. Assim,
a métrica anterior de VRAM total do dispositivo estava contaminada e não poderá
ser usada como custo TrustGraph. Esse achado valida a exigência de atribuição por
processo.

Em 11 de agosto, a atribuição foi promovida de diagnóstico manual para parte do
coletor. Cada amostra agora cruza, somente por leitura, os PIDs retornados pelo
driver com `/proc/<pid>` e os IDs/cgroups dos containers do projeto. A saída
separa `asm`, `trustgraph`, `other` e `unattributed`. A última classe é a diferença
entre a memória total usada informada pelo dispositivo e a soma que o driver
consegue expor por processo (por exemplo framebuffer, display e alocações não
enumeradas).

Uma janela real de validação mediu:

| Classe | VRAM média |
|---|---:|
| ASM | 908.066.816 B |
| TrustGraph | 0 B |
| outros | 832.569.344 B |
| não atribuída | 746.586.112 B |

O ASM permaneceu em execução e não foi reiniciado, encerrado, limitado ou
alterado. A classificação foi inteiramente externa. Nas janelas estruturadas
vazio, carregado, cold e warm, TrustGraph continuou em 0 B de VRAM atribuída;
portanto oscilações de desktop ou do treinamento não foram creditadas a ele.

Se uma fase posterior acionar um servidor de inferência compartilhado no host,
o PID desse servidor será registrado separadamente e seu custo marginal será
estimado contra uma janela vazia simultânea de mesma duração. A mera presença do
processo não basta para atribuir toda sua VRAM ao TrustGraph.

## Repetições de calibração de 11 de agosto

As tentativas independentes também detectaram um segundo confounder. O delta de
volume para os mesmos 100 eventos variou de 3.719.168 B a 151.523.328 B. O maior
valor ocorreu quando o baseline foi capturado cedo demais após a criação dos
volumes: bootstrap, logs, WAL e compactação continuaram durante a ingestão.
Esses valores ficam preservados como calibração e **não são resultados oficiais
de bytes/evento**.

O runner final deverá aplicar o mesmo período fixo de estabilização após todos os
health checks e o mesmo período pós-ingestão antes de cada snapshot. Uma repetição
que reinicie o stack ou apresente crescimento de controle fora da tolerância será
automaticamente rejeitada e refeita.

## Decisão

O gate TG-1 não será fechado com essas duas janelas. Para um resultado oficial:

- atribuir workloads GPU externos por PID/cgroup sem interferir neles;
- usar ordem balanceada vazio/carregado;
- repetir pelo menos três pares completos;
- usar a mesma idade do stack em cada janela;
- executar controle vazio pelo mesmo tempo total do workload carregado;
- calcular IC95% apenas após essas repetições.

A infraestrutura para essas repetições está pronta; os números atuais são
evidência de confounders, não uma curva de scaling.
