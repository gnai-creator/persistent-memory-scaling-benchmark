# TG-1 — instrumentação e contabilidade

**Data:** 11 de agosto de 2026
**Estado:** implementação concluída; gate de medição ainda não promovido

## O que foi implementado

O coletor `pmsb-tg1` registra, com unidades explícitas:

- CPU, memória, rede, block I/O e PIDs por container via `docker stats`;
- bytes físicos de todos os volumes Compose por mounts efêmeros somente-leitura;
- VRAM e utilização da GPU via `nvidia-smi`;
- todas as séries Prometheus `tg_*` disponíveis;
- collections do Qdrant;
- `nodetool tablestats` do Cassandra, com fallback de schema por `cqlsh`;
- totais separados de RAM e disco;
- deltas totais e por evento sem somar medidas físicas e lógicas.

Schemas versionados foram adicionados para snapshot e delta. O parser aceita
unidades decimais e IEC e possui testes contra confusão de RAM e disco.

## Run de calibração com 100 eventos

| Fase | RAM containers | Volumes físicos | VRAM total do dispositivo |
|---|---:|---:|---:|
| vazio | 3.984.316.169 B | 211.951.616 B | 2.255.486.976 B |
| pós-ingestão idle | 4.469.971.485 B | 220.127.232 B | 3.752.853.504 B |
| query ativa | 4.470.746.382 B | 220.180.480 B | 3.764.387.840 B |
| pós-query idle | 4.479.671.862 B | 221.405.184 B | 3.972.005.888 B |

Delta vazio → pós-ingestão:

```text
RAM agregada:       +485.655.316 B
disco físico:         +8.175.616 B
RAM/evento:            4.856.553 B  (apenas normalização de RSS)
disco/evento:             81.756 B
```

Esses números são calibração, não resultados oficiais de scaling. Em especial,
`RAM/evento` não representa estado lógico por evento e não deve ser extrapolado.

## Decomposição do crescimento físico até pós-ingestão

| Volume | Delta |
|---|---:|
| BookKeeper | +4.165.632 B |
| Cassandra | +1.851.392 B |
| Qdrant | +1.306.624 B |
| Prometheus | +462.848 B |
| Loki | +311.296 B |
| ZooKeeper | +40.960 B |
| Garage metadata | +36.864 B |
| Garage data | 0 B |
| Grafana | 0 B |

O total não pode ser atribuído integralmente aos 100 eventos: BookKeeper,
Prometheus e Loki crescem também com tráfego operacional e tempo decorrido. O
TG-1 oficial precisará de um controle vazio com a mesma duração.

## Cobertura e achados

- 21 containers ativos medidos;
- 9/9 volumes medidos;
- 1.592 séries `tg_*` no vazio e 2.684 após ingestão;
- duas collections Qdrant criadas para `tg0-smoke`;
- schema Cassandra capturado pelo fallback;
- GraphRAG iniciou, mas não concluiu no prazo da sessão de calibração;
- o documento e as 300 triplas foram aceitos, e os sujeitos 000 e 099 foram
  confirmados com duas triplas cada.

## Por que o gate permanece aberto

Ainda faltam três controles para publicar curvas confiáveis:

1. controle vazio com a mesma duração do run carregado;
2. amostragem contínua para picos, em vez de um único snapshot durante a query;
3. atribuição de VRAM por processo e repetição suficiente para intervalo de
   confiança.

Portanto, TG-1 produziu a infraestrutura e uma calibração real, mas nenhum valor
deste relatório deve ser apresentado como coeficiente final de scaling.
