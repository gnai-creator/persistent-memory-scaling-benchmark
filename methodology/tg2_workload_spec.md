# TG-2 — especificação congelada do workload estruturado

**Versão:** `tg2-workload-v1`
**Seed:** `20260811`

## Objetivo

Medir crescimento físico, RAM residente, throughput e consulta estruturada sem
misturar extração por LLM. Todos os fatos são importados diretamente como RDF e
cada checkpoint usa flow e collection exclusivos.

## Distribuição determinística

O tipo do evento é definido por `sequence mod 8`:

1. fato atômico;
2. fato temporal;
3. relação entre entidades;
4. caminho multi-hop pessoa → cidade → país;
5. correção/supersessão;
6. afirmações conflitantes com fontes distintas;
7. payload duplicado com eventos de proveniência independentes;
8. distrator.

O idioma alterna deterministicamente entre `en` e `pt-BR`. IDs de evento,
evidência, entidades e relações derivam somente de seed e sequência. O hash
SHA-256 é calculado por serialização JSON canônica em streaming.

## Proveniência

Cada evento possui um IRI próprio e triples explícitos de tipo, sequência,
categoria, evidence ID e entidade focal. Correções, conflitos e duplicatas não
apagam seus eventos anteriores. Assim, fatos coincidentes podem ser deduplicados
pela semântica RDF sem perder a existência dos eventos que os originaram.

## Retomada

A ingestão usa chunks numerados. Um chunk entra no journal somente depois que o
marcador do seu último evento é consultável. O journal é vinculado ao hash,
event count e chunk size; qualquer divergência aborta a retomada. Reexecutar um
journal completo não envia eventos novamente.

## Auditoria exata

O endpoint bulk `export_triples()` da versão TrustGraph 2.8.12 não encerrou o
WebSocket no teste de integração. O auditor usa, portanto, a partição física
`default.quads_by_collection` da collection exclusiva e faz `SELECT JSON s,p,o`.
O oracle esperado e o export observado são comparados em SQLite temporário,
fora da janela de medição. A validação exige zero ausentes, zero inesperados e
zero duplicatas no export.

Essa leitura direta é específica do backend selecionado e está registrada como
tal; não é apresentada como API portátil do TrustGraph.
