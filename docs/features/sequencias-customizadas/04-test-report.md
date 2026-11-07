# Relatório de testes — Sequências de Acordes Customizadas

## Cobertura

Suíte completa: **39 testes, todos verdes** (`Ran 39 tests in ~2.8s — OK`).

### `tests/test_sequences.py` — 26 testes

- `MatchExactTests` (8): bloco contíguo casa; acordes extras antes/depois
  casam; ordem invertida não casa; acorde no meio não casa; repetição
  diferente não casa; case-sensitive (`B` vs `Bm`); sequência maior que a
  cifra não casa; lista vazia não casa.
- `ParseChordsCsvTests` (5): lista simples; espaços e vírgulas vazias são
  ignorados; entrada vazia levanta erro; só separadores levanta erro;
  entrada não-string levanta erro.
- `DatabaseTests` (13): catálogo legado com 6 linhas e `legacy_id` 0-5;
  seed idempotente (duas execuções mantêm 6 linhas); criação válida;
  dedupe pela mesma lista ordenada de acordes; duplicata de legada devolve
  a linha legada; colisão de slug recebe sufixo numérico; resolução por
  slug e por acordes; entrada desconhecida devolve `None`; validação de
  nome; validação de acordes; `strip` do acorde.

### `tests/test_api.py` — 13 testes

- `GET /sequencias`: retorna as 6 seeds legadas e mantém
  `Content-Type: text/html`.
- `POST /sequencias`: cadastro válido retorna 201 e aparece no catálogo;
  acordes enviados como string CSV são aceitos; duplicata retorna 200 com
  o mesmo `id`; duplicata de legada devolve a legada; payload inválido
  retorna 400 com `json.dumps`; corpo inválido retorna 400.
- `/similares`: sequência desconhecida retorna `[]`; custom usa o matcher
  exato e respeita `pagina`; custom respeita `generos`; legada por slug e
  por lista de acordes batem com o baseline; legada não inclui
  `diferenca`.
- Regressão: comparação exata das listas ordenadas de `id_unico_musica`
  das 6 legadas com `tests/baseline_legacy.json`.

### Smoke manual

- Servidor Flask: `GET /generos`, `GET /sequencias`, `POST /sequencias`,
  `/similares` custom e legado; reinício com o mesmo `SEQUENCES_DB`
  manteve as 7 linhas.
- Docker: `docker build`; `docker run -v ciframe-instance:/app/instance`;
  POST; `docker rm` e novo `docker run` com o mesmo volume; o catálogo
  persistiu (7 linhas) e o log indicou DB existente + 6 seeds garantidas.
- Benchmark local: `/similares` custom exato ~0,36-0,47 s; legado
  ~0,06-0,13 s (alvo de ~1 s).

## Teste de regressão obrigatório

O baseline foi capturado **antes** de alterar o código, a partir do
`main.py` original (`HEAD`) e do mesmo `data/top/dataset_final.csv`, usando
o Flask test client: para cada uma das 6 legadas, todas as páginas de
`/similares?sequencia=<acordes por vírgula>`, salvando a lista ordenada de
`id_unico_musica` em `tests/baseline_legacy.json`.

Contagens do baseline: `0=199`, `1=296`, `2=4`, `3=5`, `4=7`, `5=3`.

Resultado após a implementação: **zero diferenças nas 6 sequências**, tanto
por lista de acordes (`test_similares_legacy_by_comma_matches_baseline`)
quanto por slug (`test_similares_legacy_by_slug_matches_baseline`).

Observação: a ordem dos gêneros vinha de um `set` e variava entre
processos. Para tornar a comparação reproduzível, tanto a captura do
baseline quanto o código novo usam `sorted(generos)`. Isso não altera o
conjunto de resultados, apenas estabiliza a ordem dos nomes de gênero.

## Como rodar

Execute na raiz do repositório (o `main.py` carrega o CSV por caminho
relativo). Com o virtualenv do projeto:

```
.venv/bin/python -m unittest discover -s tests -v
```

Ou, com o ambiente já ativo:

```
python -m unittest discover -s tests -v
```

Os testes criam `SEQUENCES_DB` em diretório temporário e não usam rede. O
Docker é necessário apenas para o smoke test de volume.

## O que ficou de fora

- Frontend Angular: não há infraestrutura de testes JS no projeto. O
  controller/template foram verificados por revisão e `node --check` no
  controller, mas não há teste automatizado de DOM/E2E nem execução em
  navegador nesta entrega.
- Concorrência de escrita e múltiplos workers do gunicorn: não houve teste
  de carga; WAL + `busy_timeout=5000` estão configurados e o cenário
  normal é 1 worker.
- Rate limiting/antispam do POST anônimo: risco aceito nesta iteração, sem
  teste.
- Matching exato contra todo o vocabulário ruidoso do CSV: os testes
  cobrem a semântica do matcher, não cada token real (`(C`, `9)`, `2x`
  etc.); a limitação está documentada no plano.
- Persistência em Docker foi validada manualmente com volume nomeado
  local, não em CI.
- Não foi testada a migração de um DB existente de uma versão anterior,
  pois não havia schema anterior.
