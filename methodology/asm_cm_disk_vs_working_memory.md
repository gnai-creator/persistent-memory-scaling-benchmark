# ASM-CM: crescimento em disco versus working memory bounded

**Status:** hipótese metodológica congelada para a comparação futura
**Data:** 11 de agosto de 2026

## Hipótese

O benchmark não parte da hipótese de que o ASM-CM inteiro tenha custo constante.
A hipótese testável é mais específica:

> À medida que o histórico cresce, o payload canônico e seus índices podem
> crescer em armazenamento persistente, enquanto o estado associativo necessário
> para a operação do ASM-CM permanece aproximadamente limitado em RAM.

Em notação de scaling, espera-se testar, e não presumir:

```text
ASM-CM:
ΔRAM_associativa / Δeventos → aproximadamente 0
Δdisco_payload / Δeventos > 0
```

`Aproximadamente 0` não exige RSS byte a byte constante. Runtime Python,
allocator, caches, buffers, batching e fragmentação podem causar oscilações. A
propriedade relevante é a ausência de crescimento proporcional ao histórico no
estado associativo residente.

Nenhuma forma específica de crescimento da RAM do TrustGraph será presumida. A
RAM operacional e seus caches são resultados empíricos. O que se espera do seu
modelo explícito é crescimento do armazenamento persistente pesquisável, cuja
inclinação também será medida.

## Modelo de recursos

```text
Histórico crescente
├── ASM-CM
│   ├── payload/archive em SSD                 [pode crescer]
│   ├── índices do Memory Bridge               [medir]
│   ├── snapshot do estado associativo         [hipótese: bounded]
│   └── estado associativo em RAM/VRAM         [hipótese: bounded]
└── TrustGraph
    ├── Cassandra: grafo, metadados e índices  [medir]
    ├── Qdrant: vetores e índices              [medir]
    ├── Garage: objetos                        [medir]
    └── RAM/cache operacional                  [medir, sem pressupor forma]
```

O arquivo de payload não é working memory. Preservar gigabytes de registros
exatos em SSD não implica manter esses gigabytes residentes para que o agente
continue operando. Ao mesmo tempo, o payload não pode desaparecer da
contabilidade de armazenamento total.

## Contabilidade obrigatória do ASM-CM

### Persistência

- payload bruto original;
- metadados e proveniência do payload;
- índices auxiliares do Memory Bridge;
- bindings/address head;
- snapshot serializado do estado associativo;
- WAL, journals, checkpoints e cópias temporárias duráveis;
- armazenamento total e delta sobre o baseline vazio.

### RAM

- baseline do processo sem eventos;
- RSS e working set após cada checkpoint;
- delta sobre o baseline;
- RAM idle após ingestão e período de estabilização;
- pico durante ingestão;
- pico durante consulta;
- RAM após uma sequência fixa de consultas;
- tamanho lógico do estado associativo, separado do RSS do processo;
- caches, buffers e allocator quando identificáveis.

### GPU

- estado associativo residente em VRAM, se houver;
- baseline do modelo/runtime;
- pico de ingestão e consulta;
- embeddings e reader separados do componente de memória.

## Contabilidade simétrica do TrustGraph

- bytes físicos e lógicos de Cassandra;
- collections, vetores e índices do Qdrant;
- objetos e metadados do Garage;
- WAL, commit logs, snapshots e traces;
- RSS/working set por container e do stack;
- caches cold e warm;
- VRAM de embeddings, extração e reader;
- custo compartilhado do stack separado do custo marginal por collection.

O tamanho do banco em disco nunca será tratado como RAM residente. Da mesma
forma, uma cache pequena do TrustGraph não será tratada como se toda a sua
representação pesquisável fosse bounded.

## Curvas e derivadas

Para cada checkpoint `N`, registrar:

```text
disk_total(N)
disk_payload(N)
state_persisted(N)
state_logical_ram(N)
process_rss_idle(N)
process_rss_peak_ingest(N)
process_rss_peak_query(N)
vram_peak(N)
```

Entre checkpoints consecutivos, calcular:

```text
bytes adicionais em disco / eventos adicionais
bytes adicionais de estado lógico / eventos adicionais
ΔRSS_idle / Δeventos
ΔRSS_peak_query / Δeventos
```

Além das derivadas locais, ajustar e publicar inclinação com intervalo de
confiança. Nenhuma curva será chamada de constante apenas por parecer horizontal
em poucos pontos.

## Cold storage versus working memory

O resultado deve mostrar explicitamente as duas camadas:

```text
10 anos de histórico
├── payload/archive ───────────────► SSD/disk  [cresce]
└── associative working state ─────► RAM/VRAM  [hipótese: bounded]
                                            │
                                            ▼
                                       consulta atual
```

Essa separação é arquitetural, não retórica. Será sustentada por medição de
processo, tamanho lógico do estado e armazenamento físico.

## Dois gates independentes

1. **Scaling estrutural:** o estado associativo permanece aproximadamente
   bounded conforme `N` cresce?
2. **Utilidade sob scaling:** a recuperação continua útil, correta e
   calibrada conforme `N` cresce?

Um estado pequeno que deixa de recuperar informação não demonstra memória útil.
Uma recuperação excelente com estado crescente não demonstra bounded working
memory. A tese forte exige as duas propriedades simultaneamente.

## Interpretação permitida

Se os dados sustentarem a hipótese, será válido afirmar que o ASM-CM separa
armazenamento histórico frio de working memory bounded sob a configuração
medida. Não será válido afirmar automaticamente que:

- o custo total do ASM-CM é constante;
- o payload é dispensável;
- o estado bounded preserva reconstrução exata;
- o ASM-CM substitui bancos, RAG ou proveniência explícita;
- o TrustGraph mantém todo o banco em RAM;
- RAM horizontal implica qualidade horizontal.

Resultados negativos também serão preservados: crescimento inesperado do
estado, caches proporcionais ao histórico, degradação de recuperação ou
dependência crescente de contexto invalidam ou limitam a hipótese.
