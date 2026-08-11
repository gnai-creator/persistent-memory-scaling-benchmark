# TG-2 — checkpoint oficial de 10.000 eventos

**Data:** 11 de agosto de 2026
**Estado:** checkpoint aprovado; 100k e 1M pendentes

Três runs fresh usaram controle vazio e janela carregada de 180 segundos,
estabilização idêntica, dez chunks de 1.000 eventos e auditoria integral.

| Métrica | Resultado |
|---|---:|
| disco pareado, média | 183.089.835 B |
| disco, IC95% | [135.040.847; 231.138.823] B |
| RAM pareada, média | 300.362.849 B |
| RAM, IC95% | [159.684.621; 441.041.077] B |
| ingestão média | 51,338 s |
| throughput | 194,86 eventos/s |
| consulta média | 42,128 ms |
| p95 médio | 42,293 ms |
| auditoria por run | 64.500/64.500 triples |
| ausentes/extras | 0/0 |
| VRAM TrustGraph | 0 B |
| tokens LLM | 0 / não aplicável |

O disco observado foi 171.954.176, 171.892.736 e 205.422.592 B. A terceira
repetição provavelmente capturou estado diferente de flush/compaction; ela não
foi descartada, pois passou todos os critérios pré-registrados. A variabilidade
aparece no IC95% e faz parte do comportamento operacional.

O custo médio foi aproximadamente 18.309 B/evento, abaixo de c100 e c1k por
amortização de infraestrutura e páginas. Ainda não é uma conclusão de
assintótica: faltam 100k e 1M.

Durante a primeira tentativa, Docker reportou `NetIO` como `1e+03kB`. O parser
foi corrigido para notação científica e ganhou teste de regressão; aquela
tentativa terminou antes da ingestão e não integra os resultados.
