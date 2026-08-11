# ASM-CM R3 — linguagem livre

O R3 do `asm-memory-bridge` terminou e gerou um novo context address head, mas não
passou o gate de promoção.

| Sistema | Recall@5 |
|---|---:|
| ASM context head treinado | 15,62% |
| ASM bindings-only | 12,50% |
| ASM context zero | 3,12% |
| ASM other-conversation | 5,47% |
| BM25 | 57,81% |
| Vector | 60,16% |

O head treinado superou os controles zero e other-conversation e ganhou de
bindings-only em inglês e português. Porém, a vantagem agregada sobre bindings foi
de apenas 3,12 pontos, abaixo do gate de 10 pontos. A decisão automática foi
`promote=false` e `authorize_r4=false`.

O R3 usa 128 exemplos de teste com rótulos automáticos propostos e sem validação
humana. Ele não invalida o resultado estruturado da Phase 8.1, mas mostra que a
transição para perguntas abertas e referências conversacionais ainda não está
resolvida no ASM-CM.

Proveniência:

- `../asm-memory-bridge/runs/dual_asm_r3/results.json`;
- `../asm-memory-bridge/runs/dual_asm_r3/report.md`;
- checkpoint ASM-CM congelado e inalterado: `true`;
- train/dev/test: 12.000 / 2.048 / 128.
