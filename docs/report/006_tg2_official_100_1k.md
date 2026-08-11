# TG-2 — checkpoints oficiais de 100 e 1.000 eventos

**Data:** 11 de agosto de 2026
**Estado:** dois checkpoints aprovados; curva completa pendente

## Protocolo

Cada ponto tem três runs fresh com volumes novos, flow e collection exclusivos,
estabilização de 60 segundos mais 15 segundos de quiescência, janela vazia de
30 segundos e janela carregada de 30 segundos. O delta oficial subtrai o
crescimento do controle vazio de mesma duração. Todos os runs exigiram os mesmos
21 IDs de container, ingestão dentro da janela, journal confirmado, auditoria
integral da collection e 100 consultas estruturadas sem falha.

## Resultados

| Métrica | 100 eventos | 1.000 eventos |
|---|---:|---:|
| disco pareado, média | 2.140.843 B | 19.615.744 B |
| disco, IC95% | [2.064.467; 2.217.218] B | [19.605.568; 19.625.920] B |
| RAM pareada, média | 35.429.985 B | 82.707.477 B |
| RAM, IC95% | [−66.717.333; 137.577.303] B | [56.484.355; 108.930.600] B |
| ingestão média | 8,590 s | 12,177 s |
| throughput médio | 11,64 eventos/s | 82,75 eventos/s |
| consulta média | 41,240 ms | 41,221 ms |
| p95 médio | 41,949 ms | 41,998 ms |
| triples únicos por run | 656/656 | 6.563/6.563 |
| ausentes/extras | 0/0 | 0/0 |
| pico VRAM TrustGraph | 0 B | 0 B |
| tokens enviados ao LLM | 0 / não aplicável | 0 / não aplicável |

O disco corresponde a aproximadamente 21.408 B/evento em c100 e 19.616
B/evento em c1k. Esses dois pontos sugerem crescimento persistente aproximadamente
linear, mas não bastam para estabelecer a curva; 10k, 100k e 1M permanecem
necessários.

A RAM de c100 é inconclusiva porque o IC95% cruza zero. Isso é evidência de que
caches e allocator dominam o sinal pequeno, não de RAM negativa. Em c1k o sinal
é positivo e o intervalo não cruza zero. A RAM total de pico do stack carregado
foi aproximadamente 4,47 GB em c100 e 4,55 GB em c1k.

O throughput maior em c1k reflete amortização de inicialização e batching; não
significa que throughput cresce indefinidamente com o histórico.

## Tokens e comparação ASM

TG-2 não executa reader ou LLM. O valor zero é uma propriedade do gate
estruturado e não uma economia comparável à Phase 8.1 do ASM. A comparação de
tokens exige o mesmo MultiWOZ, as mesmas 979 perguntas, o mesmo Qwen3 14B,
tokenizer, prompt e evidências efetivamente enviadas, conforme
`methodology/reader_token_accounting.md`.

## Decisão

Os checkpoints c100 e c1k passaram e autorizam calibração de c10k. O gate TG-2
permanece aberto até três repetições válidas de 10k, 100k e 1M e a geração da
curva completa.
