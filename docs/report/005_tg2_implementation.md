# TG-2 — implementação e testes de integração

**Data:** 11 de agosto de 2026
**Estado:** implementação pronta; campanha oficial pendente

## Entregue

- gerador determinístico em streaming para `100`, `1k`, `10k`, `100k` e `1M`;
- categorias atômica, temporal, relacional, multi-hop, correção, conflito,
  duplicata e distrator;
- inglês e português brasileiro;
- proveniência explícita no grafo;
- SHA-256 do workload congelado;
- ingestão em chunks com journal atômico, retomável e vinculado ao hash;
- snapshots e amostragem contínua durante ingestão;
- auditoria integral da collection contra oracle SQLite;
- 100 consultas estruturadas distribuídas deterministicamente;
- teardown que encerra somente TrustGraph e preserva os volumes finais.

## Integrações executadas

| Run | Eventos | Triples brutos | Triples únicos auditados | Ausentes/extras | Disco Δ | RAM Δ | Ingestão |
|---|---:|---:|---:|---:|---:|---:|---:|
| `tg2-c100-integration-r2` | 100 | 662 | 656/656 | 0/0 | 1.875.968 B | 20.706.230 B | 10,39 s |
| `tg2-c1k-integration-r1` | 1.000 | 6.625 | 6.563/6.563 | 0/0 | 16.924.672 B | 112.485.991 B | 14,54 s |

A consulta estruturada teve média de 41,119 ms em ambos os runs e nenhuma das
100 consultas de cada checkpoint falhou. TrustGraph registrou pico de 0 B de
VRAM atribuída; o ASM permaneceu separado em 908.066.816 B médios.

Os deltas acima validam o instrumento, mas não formam ainda uma curva oficial:
cada ponto tem somente uma repetição e não recebeu o controle pareado completo
da futura campanha. Não se calculou IC95% nem se extrapolou para checkpoints
maiores.

## Teste de retomada

O run de 100 eventos foi reiniciado sobre os volumes preservados com o journal
completo. Resultado:

- eventos importados: `0`;
- eventos ignorados com segurança: `100`;
- triples auditados: `656/656`;
- ausentes, extras e duplicatas: `0`.

## Falha descoberta e correção

O primeiro protótipo concluiu ingestão e snapshots, mas ficou aguardando
indefinidamente o fim do WebSocket de `bulk.export_triples()`. A execução foi
interrompida sem remover volumes. A auditoria foi substituída por streaming da
partição Cassandra da collection, que concluiu e encontrou exatamente o oracle.

## Próximo passo

Executar a campanha oficial balanceada: três repetições fresh por checkpoint,
controle vazio pareado, começando em `100` e `1k`, e promover progressivamente
`10k`, `100k` e `1M` apenas após espaço em disco e duração serem estimados pelo
ponto anterior.
