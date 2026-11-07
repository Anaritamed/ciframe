# Sequências de Acordes Customizadas — Design Document (Plano)

## Contexto Atual

- Backend Flask single-file (`main.py`) carrega `data/top/dataset_final.csv` (67.585 músicas) em memória no import; músicas e gêneros continuam vindo do CSV.
- As 6 sequências legadas estão hardcoded em `main.py:40-45` como strings concatenadas sem vírgula. `/similares?sequencia=` remove as vírgulas e usa o id para filtrar `musica.seqs_famosas` (`main.py:190-201` e `main.py:203-223`).
- `musica.py:16-18`: `cifra` mantém a progressão ordenada; `acordes = list(set(cifra))` perde ordem e repetição. O matcher novo deve usar `musica.cifra`, não `musica.acordes`.
- Frontend `#/porsequencia` (`routes.js:17-20` + `SequenciaController`) tem 4 sequências hardcoded (`sequencia.js:2-37`) e chama `similares?sequencia=` com os acordes unidos por vírgula (`sequencia.js:55-90`). Não há cadastro e a lista não reflete o backend (4 no frontend vs 6 no backend).
- Não há banco nem persistência; reiniciar o processo perde qualquer sequência nova. Pesquisa e decisão estão em `01-research.md`, `02-proposal.md` e no ADR `0002-persist-custom-sequences.md`.

## Requisitos

### Requisitos Funcionais

- Qualquer visitante, sem login, cadastra uma sequência: nome + lista ordenada de acordes.
- `GET /sequencias` devolve o catálogo completo, mas sem repetição de sequências: as 6 legadas + as sequências cadastradas pelo usuário.
- `GET /similares?sequencia=` aceita o slug de uma sequência do catálogo ou, por compatibilidade, a lista de acordes separada por vírgula, e devolve o mesmo formato/paginação de hoje.
- As 6 legadas continuam usando `musica.seqs_famosas` e produzindo exatamente os resultados atuais; customizadas usam o matcher exato em tempo real.
- A página `#/porsequencia` carrega o catálogo da API, permite cadastrar uma sequência e buscar; a rota não muda.
- O catálogo é persistido em SQLite e sobrevive a reinício do processo; com volume, sobrevive à recriação do container.
- O seed das 6 legadas é idempotente no startup.

### Requisitos Não-Funcionais

- Container único, local-only (ADR 0001); sem serviço externo e sem migrar músicas/gêneros do CSV.
- Respostas continuam sendo strings de `json.dumps(...)`, não `jsonify`, inclusive os erros de validação.
- Matching case-sensitive; ordem e repetição importam; sem normalização enarmônica.
- SQLite com WAL e `busy_timeout`; cenário normal de 1 worker do gunicorn.
- A varredura de ~67k músicas (média de ~52 acordes por música) por request deve ficar abaixo de ~1s no uso local; sem índice nesta iteração.
- Validação restritiva no POST para limitar abuso e entradas inválidas.

## Decisões de Design

### 1. Matching

Implementar um matcher exato: a sequência `S` aparece em `musica.cifra` quando existe um índice `i` tal que `musica.cifra[i:i+len(S)] == S` — ou seja, um bloco contíguo e na mesma ordem. Justificativa:

- Definição precisa, implementável e testável; preserva ordem e repetição e não exige normalização.
- `musica.acordes` é um `set` e não serve.
- As 6 legadas permanecem no caminho `seqs_famosas` (`match_mode='legacy'`) porque o matcher exato não reproduz os resultados atuais (`Gm,F`: 6 no legado vs 40+ por acordes).
- Trade-off: duas semânticas de matching convivem; uma customizada que duplique uma legada pode retornar resultados diferentes dela.

### 2. Persistência

SQLite via `sqlite3` da stdlib, em arquivo único configurável por `SEQUENCES_DB` (default `instance/sequences.db` relativo à raiz do app — no Docker, `/app/instance/sequences.db`; fora de `data/`). Justificativa:

- Sem dependência nova e sem serviço externo; ACID, índices e consultas simples; cabe no container único.
- Fora de `data/` para que um volume não esconda o CSV embutido na imagem.
- WAL + `busy_timeout` para concorrência; um escritor por vez é aceitável com 1 worker.
- Alternativas descartadas: JSON/shelve/TinyDB (concorrência/transação fracas), LMDB (dependência nativa) e memória (não persiste).

### 3. Módulo novo `sequences.py`

Isolar schema, seed, catálogo e matcher em `sequences.py`, importado por `main.py`. Justificativa:

- Permite testar matcher e DB sem importar `main.py` (que carrega o CSV de 16 MB).
- Mantém `main.py` focado nas rotas e no caminho legado.
- Trade-off: mais um arquivo, mas sem nova dependência.

### 4. Esquema e seed

Tabela `sequences` com `id`, `slug` único, `name`, `chords` (JSON canônico), `match_mode` (`legacy`/`exact`), `legacy_id` único (0-5; nulo para custom) e `created_at`. Seed idempotente por `legacy_id` com `INSERT OR IGNORE`; as 6 definições (`legacy_id`, nome, acordes e slug fixo) ficam em `LEGACY_SEQUENCES` no módulo.

- `name` das legadas = acordes unidos por espaço (ex.: `"Gm F"`), sem inventar nomes.
- Duplicata = mesma lista ordenada de acordes (JSON canônico); retorna a existente de forma idempotente.
- Slug de custom: derivado do nome (sem acentos, minúsculo, com `-`), recebendo sufixo numérico em caso de colisão.

### 5. API

- `GET /sequencias`: catálogo completo como `json.dumps`, obrigatoriamente; cada item `{id, slug, name, chords, match_mode, legacy_id, created_at}`.
- `POST /sequencias`: corpo `{name, chords}`; valida, deduplica e insere; 201 ao criar, 200 se duplicada, 400 com `{"error": "..."}` em `json.dumps`. Sem login, autoria ou moderação.
- `GET /similares?sequencia=`: resolve por slug e, depois, pela lista ordenada de acordes; se `legacy`, usa `get_similares_por_sequencia`; se `exact`, usa o matcher novo; aplica `generos` e `get_pagina`; entrada desconhecida retorna `[]`.
- Objetos de resultado espelham o caminho legado (`main.py:210-220`); não incluir `diferenca`, pois o template esconde resultados com esse campo.

### 6. Frontend

- Remover as 4 sequências hardcoded; no init, chamar `GET /sequencias` e montar `vm.sequenciasFamosas` no formato que o template já espera (`{acordes: [{acorde, cor}]}`), mapeando `chords` (strings) para objetos com `cor`.
- Adicionar um formulário (nome + acordes separados por vírgula) que faz `POST /sequencias`, valida no cliente e recarrega o catálogo; exibir o erro da API. O formulário deve ficar fora do `ng-repeat` e usar `ng-submit` para não disparar a busca da sequência.
- `pesquisarPorSequencia` continua chamando `similares?sequencia=`, agora com o `slug` da sequência selecionada; manter o filtro de gênero.
- `sequencia.html`: renderizar o catálogo com o nome e o formulário; manter `ng-hide="music.diferenca.length"` (campo ausente torna a expressão falsy).

## Design Técnico

### 1. Componentes Principais

`sequences.py` (novo):

```python
def init_db(path: str) -> sqlite3.Connection: ...
def seed_legacy(conn) -> int: ...
def list_sequences(conn) -> list[dict]: ...
def create_sequence(conn, name: str, chords: list[str]) -> tuple[dict, bool]: ...
def resolve_sequence(conn, ident: str) -> dict | None: ...
def parse_chords_csv(raw: str) -> list[str]: ...
def match_exact(cifra: list[str], chords: list[str]) -> bool: ...
def exact_matches(songs, chords: list[str], generos_key) -> list[dict]: ...
```

`main.py`: no startup, chamar `init_db` e `seed_legacy`; adicionar as rotas `GET/POST /sequencias`; em `/similares`, resolver a sequência e despachar para o caminho legacy ou exact; manter `get_similares` e `get_pagina` intactos.

### 2. Modelos de Dados

```sql
CREATE TABLE IF NOT EXISTS sequences (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  chords TEXT NOT NULL,          -- JSON array ordenado e canônico
  match_mode TEXT NOT NULL CHECK (match_mode IN ('legacy','exact')),
  legacy_id INTEGER UNIQUE,      -- 0..5 ou NULL
  created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sequences_chords ON sequences(chords);
```

Linha -> dict: `chords` desserializado com `json.loads`; `created_at` em ISO-8601 UTC. Configurar `PRAGMA journal_mode=WAL` e `PRAGMA busy_timeout=5000`.

### 3. Pontos de Integração

- Cadastro: browser -> `POST /sequencias` -> validação -> dedupe por `chords` -> insert -> JSON.
- Busca: browser -> `GET /similares?sequencia=<slug|acordes>` -> `resolve_sequence` -> legacy (`seqs_famosas`) ou exact (`musica.cifra`) -> `apply_filtro` por gênero -> `get_pagina` -> JSON.
- Contrato de erro: status 400, corpo `json.dumps({"error": "mensagem"})`, `Content-Type: text/html` (comportamento legado).
- Compatibilidade: `?sequencia=Gm,F` continua resolvendo a legada `legacy_id=4` pelo bloco ordenado.

### 4. Arquivos Alterados

| Arquivo | Mudança |
|---|---|
| `main.py` | init/seed no startup; `GET/POST /sequencias`; resolução em `/similares`; `generos` ordenado para regressão determinística; manter o caminho legado e `json.dumps`. |
| `sequences.py` (novo) | schema, seed, catálogo, validação, dedupe, slug e matcher exato. |
| `static/assets/js/controllers/sequencia.js` | carregar o catálogo da API; formulário/POST; mapear `chords` para o view model; busca por slug. |
| `static/templates/sequencia.html` | renderizar o catálogo com nome; formulário de cadastro; mensagem de erro. |
| `tests/test_sequences.py` (novo) | unitários de matcher, validação, slug/dedupe/seed. |
| `tests/test_api.py` (novo) | integração + regressão das 6 via Flask test client. |
| `tests/baseline_legacy.json` (novo) | baseline ordenado das 6 legadas para a regressão obrigatória. |
| `.gitignore` / `.dockerignore` | ignorar `instance/` (DB local). |
| `README.md` | documentar `docker run -v ciframe-instance:/app/instance ...`. |
| `docs/features/sequencias-customizadas/03-plan.md` | este plano. |
| `musica.py`, `Dockerfile`, `requirements.txt`, `data/*.csv` | sem mudança. |

## Plano de Implementação

Sem prazo externo; as fases são sequenciais e cada uma só avança com os critérios de saída verdes.

### Fase 0 — Baseline de regressão (antes de alterar código)

- [x] Subir a versão atual e salvar, para cada uma das 6 sequências, a lista ordenada de `id_unico_musica` de `/similares?sequencia=...`, percorrendo as páginas.
- [x] Guardar o baseline como artefato de teste (`tests/baseline_legacy.json` ou temporário).
- [x] Critério de saída: baseline completo das 6 sequências.

### Fase 1 — Persistência e matcher

- [x] Criar `sequences.py` com DDL, init, seed idempotente, `list/create/resolve`, slug/dedupe e `match_exact`.
- [x] Definir `LEGACY_SEQUENCES` (legacy_id 0-5, nome, acordes e slug fixo).
- [x] Escrever `tests/test_sequences.py` (DB em arquivo temporário; sem CSV).
- [x] Critério de saída: unitários verdes; rodar o seed duas vezes não duplica linhas.

### Fase 2 — Backend e API

- [x] Em `main.py`, inicializar DB/seed no import; adicionar `GET/POST /sequencias`.
- [x] Trocar o dict `sequencias` por resolução via DB em `/similares`; preservar `get_similares_por_sequencia`, `apply_filtro`, `get_pagina` e formatos.
- [x] Implementar validação: nome 1-80; 1-16 acordes; token com raiz A-G, sufixo permitido e máx. 17 chars; sem vírgula/espaço; erros 400 em `json.dumps`.
- [x] Escrever `tests/test_api.py` (test client, `SEQUENCES_DB` temporário).
- [x] Critério de saída: endpoints e testes de integração verdes; entrada desconhecida -> `[]`.

### Fase 3 — Frontend

- [x] `sequencia.js`: remover hardcoded; carregar `GET /sequencias`; mapear para o view model atual; formulário com nome/acordes; `POST` e recarga; exibir erro.
- [x] `sequencia.html`: renderizar o catálogo (nome + hex) e o formulário; manter layout e classes atuais.
- [x] Critério de saída: cadastro aparece na lista sem reload; busca por slug retorna músicas; as 6 legadas aparecem.

### Fase 4 — Regressão, Docker e documentação

- [x] Rodar a regressão comparando com o baseline da Fase 0; zero diferenças nas 6.
- [x] Rodar `docker build` e `docker run -v ciframe-instance:/app/instance -p 8080:8080 ciframe`; cadastrar, reiniciar o processo e recriar o container, confirmando a persistência.
- [x] Atualizar o README com o volume; confirmar `.gitignore`/`.dockerignore`.
- [x] Preencher `04-test-report.md` com cobertura e resultado.
- [x] Critério de saída: definição de pronto abaixo.

> Nota de implementação: `generos` passou a ser ordenado no startup (`sorted(generos)`) para eliminar a ordem não determinística do `set` entre processos. O conjunto de resultados não muda; apenas a ordem dos nomes de gênero fica estável para a regressão.

## Riscos e Mitigação

| Risco | Como perceber | Mitigação |
|---|---|---|
| Regressão nas 6 sequências legadas | Diferença na lista ordenada de `id_unico_musica` em relação ao baseline | Capturar o baseline antes de alterar; manter o caminho `seqs_famosas`; comparar exatamente na Fase 4. |
| Matching exato não encontra acordes "limpos" em cifras sujas | Busca por sequência cadastrada retorna vazio ou menos que o esperado | Documentar a limitação; manter a semântica contígua/ordenada; não normalizar nesta iteração; avaliar índice/fuzzy no futuro. |
| Perda do catálogo ao recriar o container | `GET /sequencias` volta a mostrar só as 6 após `docker rm` + `run` | Documentar e testar o volume `ciframe-instance:/app/instance`; logar o caminho do DB no startup. |
| Concorrência de escrita no SQLite | Erros `database is locked` sob carga | WAL + `busy_timeout=5000`; cenário normal é 1 worker do gunicorn. |
| POST anônimo abusivo/spam | Catálogo crescendo sem controle | Validação de tamanho/formato e limite de acordes; rate limiting fica como risco aceito nesta iteração. |
| Seed e CSV divergirem | Sequência legada some ou muda de resultado após troca de CSV | Seed idempotente por `legacy_id`; troca de CSV já exige reinício; registrar a dependência no ADR 0002. |

## Definição de Pronto

- [x] `POST /sequencias` cadastra uma sequência válida e ela aparece em `GET /sequencias`.
- [x] Cadastro duplicado (mesma lista ordenada de acordes) retorna a sequência existente, sem criar outra.
- [x] `GET /similares?sequencia=<slug>` de uma sequência customizada retorna as músicas em que ela aparece como bloco contíguo e ordenado.
- [x] `GET /similares?sequencia=<acordes por vírgula>` continua funcionando para as 6 legadas e para a compatibilidade.
- [x] As 6 sequências originais retornam exatamente os mesmos resultados do baseline (regressão obrigatória).
- [x] A página `#/porsequencia` lista o catálogo real da API, permite cadastrar e buscar, sem lista hardcoded.
- [x] O catálogo persiste após reiniciar o processo e após recriar o container com o volume montado.
- [x] Testes unitários e de integração passam; `04-test-report.md` documenta cobertura e regressão.

## Estratégia de Testes

### Testes Unitários

- `match_exact`: bloco contíguo casa; ordem invertida não casa; acordes extras antes/depois casam; acorde no meio ou repetição diferente não casa; case-sensitive (`B` vs `Bm`); sequência maior que a cifra não casa; lista vazia é rejeitada antes do matcher.
- `parse_chords_csv`: `Gm,F` -> `['Gm','F']`; espaços e vírgulas vazias são tratados; entrada vazia -> erro.
- `create_sequence`: validação de nome/acordes; dedupe pela mesma lista ordenada; slug único com sufixo; `legacy_id` não aceito em custom.
- `seed_legacy`: idempotente (rodar duas vezes mantém 6 linhas).
- Banco em diretório temporário; nunca usar o DB de produção.

### Testes de Integração

- `GET /sequencias` retorna as 6 seeds no primeiro boot; `POST` válido aparece; `POST` duplicado devolve a existente; `POST` inválido -> 400 com `json.dumps`.
- `GET /similares?sequencia=<slug custom>` retorna resultados do matcher exato e respeita `pagina`/`generos`.
- `GET /similares?sequencia=Gm,F` resolve a legada e mantém o formato (sem `diferenca`).
- Entrada desconhecida -> `[]`.
- Regressão: para cada uma das 6, comparar a lista ordenada de IDs com o baseline; exigir igualdade exata.

### Como Rodar

```
python -m unittest discover -s tests -v
```

Ambiente: `SEQUENCES_DB` apontando para arquivo temporário; sem rede; Docker apenas no smoke test.

## Observabilidade

- Apenas log de startup: caminho do `SEQUENCES_DB`, se é novo ou existente e quantas seeds legadas foram garantidas; útil para diagnosticar volume ausente.
- Sem métricas, dashboards ou alertas: app local-only, sem infraestrutura de observabilidade.
- Erros de validação são retornados ao cliente; não logar payloads de acordes.

## Considerações Futuras

### Melhorias Potenciais

- Rate limiting/antispam no POST anônimo.
- Edição, exclusão, moderação e autoria (exigiria login).
- Normalização enarmônica/transposição e matching fuzzy (mudaria a semântica; fora do escopo).
- Índice por primeiro acorde/bigramas se a varredura de 67k músicas virar gargalo.
- Framework de migração se o schema crescer.

### Limitações Conhecidas

- Duas semânticas de matching no mesmo catálogo.
- Persistência entre recriações exige volume; sem volume, o catálogo sobrevive só a restart do processo.
- SQLite permite um escritor por vez; não escala horizontalmente.
- O vocabulário do CSV é ruidoso (6.654 tokens, incluindo `(C`, `9)` e `2x`); o matching exato pode não encontrar sequências digitadas com acordes "limpos" em cifras sujas.
- Sem rate limiting; o catálogo aberto pode receber spam (risco aceito nesta iteração).

## Dependências

### Dependências de Desenvolvimento

- Nenhuma nova dependência de runtime (`sqlite3` é stdlib).
- Testes com `unittest` da stdlib; sem pytest/build tools.
- Docker apenas para o smoke test de volume.

## Considerações de Segurança

- POST anônimo por design; validação de tamanho/formato e limite de acordes para reduzir abuso.
- SQL sempre parametrizado; nunca concatenar `name`/`chords` na query. `chords` é persistido como JSON.
- Sem secrets, autenticação ou dados pessoais; nenhum segredo no DB ou nos logs.
- O frontend renderiza texto via binding Angular (sem `ng-bind-html`), evitando XSS do nome cadastrado.
- CORS `*` já existe em `main.py:274-277`; não alterar. Rate limiting fica como risco em aberto.

## Estratégia de Rollout

1. Desenvolvimento local: implementar as fases 1-3; rodar unitários e integração.
2. Teste de regressão: comparar as 6 com o baseline da Fase 0.
3. Docker local: `docker build -t ciframe .` e `docker run -v ciframe-instance:/app/instance -p 8080:8080 ciframe`; validar cadastro, busca e persistência após restart/recriação.
4. Sem staging/produção: o deploy é local-only (ADR 0001).
5. Rollback: reverter o código; o arquivo SQLite é inerte para a versão antiga e pode ser mantido ou removido sem afetar músicas/gêneros.

## Referências

- `docs/features/sequencias-customizadas/00-enunciado.md`
- `docs/features/sequencias-customizadas/01-research.md`
- `docs/features/sequencias-customizadas/02-proposal.md`
- `docs/adr/0001-local-only-docker-deploy.md`
- `docs/adr/0002-persist-custom-sequences.md`
- `docs/adr/0003-lift-frontend-freeze.md`
- `main.py` (`limpa_cifra` 11-23; legadas 40-45; `/similares` 170-201; legado 203-223; paginação 226-228)
- `musica.py:16-18`
- `static/assets/js/controllers/sequencia.js`
- `static/templates/sequencia.html`
- `static/assets/js/routes.js:17-20`
