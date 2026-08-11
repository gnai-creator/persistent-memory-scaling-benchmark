# Contabilidade de tokens e comparação com ASM Phase 8.1

## Separação entre gates

TG-2 não chama um modelo de linguagem. Ele mede armazenamento, ingestão,
auditoria e consulta estruturada. Por isso, tokens de entrada e saída do LLM são
`0`/não aplicáveis nesse gate. Esse zero não será apresentado como economia em
relação a sistemas que executaram um reader.

TG-3/TG-4 medirão recuperação e resposta. Para cada pergunta serão preservados:

- pergunta original;
- template completo de system/user messages;
- evidências recuperadas, ordem e conteúdo antes do reader;
- tokens da pergunta, instruções, evidências e input total;
- tokens de saída;
- latência de recuperação e latência do reader separadas;
- modelo, revisão, tokenizer e parâmetros de geração;
- resposta e pontuação de qualidade.

Tokens serão calculados com o tokenizer exato do reader sobre a serialização
real enviada à API, não por caracteres, palavras ou estimativa de custo.

## Baseline ASM informado

Os seguintes valores foram fornecidos pelo projeto ASM e devem permanecer
marcados como baseline externo até que manifests/artefatos da execução sejam
ligados ao relatório:

### Phase 7.6 — MultiWOZ estruturado, três seeds

| Sistema | Recall@5 médio |
|---|---:|
| ASM Memory Bridge | 93,49% |
| BM25 | 75,59% |
| Recency | 31,05% |

Resultados adicionais informados: Recall@1 ≈ 49,45%, Recall@10 ≈ 99,32% e
Recall@5 por seed de 93,46%, 94,24% e 92,77%. O corpus informado é MultiWOZ 2.2
e o ASM-CM estava congelado; somente address heads foram treinados.

### Phase 8.1 — 979 perguntas com suporte válido

| Sistema | Recall | Qualidade | Tokens de entrada |
|---|---:|---:|---:|
| ASM compact | 93,56% | 66,59% | 1.070.228 |
| Vector RAG | 69,97% | 49,68% | 1.994.408 |
| BM25 | 75,89% | 56,85% | 2.148.717 |

Também foram informados: 46,34% menos tokens do que Vector RAG, vantagem de
16,91 pontos em qualidade, menos tokens em 951/979 comparações e latência média
do reader de 855 ms contra 1.065 ms. O reader informado foi o mesmo Qwen3 14B.

## Condição para comparação direta

TrustGraph só será colocado na mesma tabela quando executar:

1. o mesmo split/licença do MultiWOZ 2.2;
2. as mesmas 979 perguntas e ground truth;
3. o mesmo reader Qwen3 14B e tokenizer;
4. o mesmo limite/critério de evidências;
5. o mesmo prompt e parâmetros de geração;
6. três seeds ou uma justificativa pré-registrada para determinismo;
7. contagem de tokens sobre os requests efetivos.

Até lá, os resultados sintéticos TG-2 e os resultados MultiWOZ do ASM serão
exibidos em seções distintas. A limitação das perguntas estruturadas com pistas
explícitas também deve acompanhar qualquer afirmação pública; conversação aberta,
paráfrases e referências anafóricas pertencem ao protocolo R3/TG-3.
