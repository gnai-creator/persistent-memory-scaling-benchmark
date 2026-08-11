# TG-2 — correção do gráfico de scaling

## Correção de RAM

O painel anterior conectava deltas pareados de RAM e podia sugerir uma queda de
consumo no checkpoint c100k. Essa interpretação não era válida: c100–c10k eram
médias de três repetições, enquanto c100k tinha uma única execução, e o delta
pareado é sensível a caches, allocator e drift do controle.

O painel foi substituído por **pico de RAM total dos containers TrustGraph**:

- c100, c1k e c10k: média do pico, IC 95% e `n=3`;
- c100k: marcador isolado e `n=1`, sem intervalo de confiança;
- o ponto c100k não é conectado à série repetida como se tivesse a mesma força
  estatística.

O delta pareado permanece nos artefatos brutos para auditoria, mas não aparece
mais como curva pública de scaling.

No c100k, este painel apresenta o pico de 4,81 GB. O gráfico separado de
footprint apresenta a média de 4,27 GB sobre 30 s idle. A diferença é esperada:
o primeiro é pico da janela carregada e o segundo é média temporal idle, não uma
reexecução discordante da mesma estatística.

## Comparação ASM-CM

ASM-CM ainda não foi adicionado como **curva TG-2**, porque não executou o mesmo
workload nos checkpoints c100, c1k, c10k e c100k sob o mesmo coletor. Os resultados
Phase 7.6/8.1 usam MultiWOZ e medem retrieval, reader e tokens; apresentá-los como
série de armazenamento, ingestão ou consulta TG-2 seria uma comparação de
protocolos diferentes.

Após a conclusão da Phase 8.1, o painel de RAM passou a incluir uma linha horizontal
tracejada de **0,115 GB peak RSS** como referência operacional separada
“ASM-CM + Bridge 8.1”. A própria anotação declara “not TG-2 scaling”; o ponto não é
usado para ajustar tendência, extrapolação ou intervalo de confiança.

Os outros três quadrantes agora mostram explicitamente
“ASM-CM + Bridge 8.1: NOT MEASURED UNDER TG-2”. Isso evita uma omissão visual sem
inventar valores de storage, structured-query latency ou ingestion throughput a
partir de um protocolo MultiWOZ incompatível.

A série ASM-CM será adicionada quando o gate ASM-TG-2 produzir, por checkpoint:

- RAM total do processo/serviços ASM;
- VRAM atribuída aos PIDs ASM;
- armazenamento físico e active-state bytes, separados;
- ingestão e consulta com o mesmo workload TG-2;
- três repetições e IC 95%, ou marcação explícita de `n=1`.

O treinamento ASM em andamento não foi interrompido ou modificado.

## Enquadramento arquitetural

A formulação adotada no artigo será:

> TrustGraph is not itself a neural memory model; it is an AI/context
> infrastructure platform that orchestrates graphs, storage, retrieval, and
> models. ASM-CM is a neural memory model.

Em forma curta:

> TrustGraph stores memory as data structures. ASM-CM represents memory as
> learned state.

Isso é contexto para interpretar as medições, não uma conclusão derivada delas.
O benchmark continua responsável apenas por quantificar RAM, VRAM, disco, estado
ativo, CPU, I/O, ingestão, consulta, retrieval e reader sob protocolos declarados.
