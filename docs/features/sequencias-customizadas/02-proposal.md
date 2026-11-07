# Proposta — Sequências de Acordes Customizadas

## Abordagem escolhida

### Algoritmo de matching

Uma sequência é uma lista ordenada de acordes. Uma música casa com a sequência
`S` quando `S` aparece como um bloco **contíguo e na mesma ordem** em
`musica.cifra` (a progressão ordenada lida do CSV por `limpa_cifra`,
`main.py:11-23` e `main.py:58-61`). Formalmente: existe um índice `i` tal que
`musica.cifra[i:i+len(S)] == S`. A comparação é token a token, case-sensitive,
sem normalização; repetições contam; acordes extras antes ou depois do bloco são
permitidos; acordes no meio do bloco, reordenação ou repetição diferente não
casam. Por exemplo, `C,Gm,F,Bb` casa com `Gm,F`, mas `Gm,C,F` e `F,Gm` não casam.
Não usamos `musica.acordes` (`musica.py:17`) porque ele é um `set` e perde ordem e
repetição.

As 6 sequências originais permanecem no modo legado: são semeadas no banco com
`match_mode='legacy'` e `legacy_id` 0-5 e continuam usando `musica.seqs_famosas`
via `get_similares_por_sequencia` (`main.py:203-223`). Isso é obrigatório porque
o matching em tempo real não reproduz os resultados atuais — a pesquisa mostrou
`Gm,F` retornando 6 músicas via tag e 40+ via acordes. Sequências novas usam o
matcher exato. O endpoint devolve o mesmo formato de objeto do caminho legado
(`main.py:210-220`) e pagina com `get_pagina`; não devolvemos `diferenca` não
vazia, porque `static/templates/sequencia.html:43` esconde resultados com
`diferenca`.

### Banco de dados

SQLite via `sqlite3` da stdlib, em arquivo único. O arquivo fica fora de `data/`
(por exemplo `/app/instance/sequences.db`, configurável por `SEQUENCES_DB`) para
que um volume não esconda `data/top/dataset_final.csv`, que é embutido na imagem.
O container continua único; a persistência entre reinícios e recriações exige
montar um volume nesse diretório
(`docker run -v ciframe-instance:/app/instance ...`). Usamos WAL e
`busy_timeout` para tolerar escrita concorrente; o caso normal é 1 worker do
gunicorn.

Alternativas descartadas: JSON/shelve/TinyDB (sem transação ou consulta robusta
e concorrência ruim), LMDB (dependência nativa e complexidade) e memória (não
persiste). SQLite foi o melhor encaixe na pesquisa.

### Esquema de dados (alto nível)

- `sequences`: `id` (PK), `slug` (único), `name`, `chords` (JSON com a lista
  ordenada de acordes), `match_mode` (`legacy` ou `exact`), `legacy_id` (0-5,
  único, nulo para sequências customizadas) e `created_at`.
- Seed idempotente das 6 originais por `legacy_id` (`INSERT OR IGNORE`).
- Índice único em `slug`; a lista ordenada de acordes (JSON normalizado) é usada
  para detectar duplicatas.

### API

- `GET /sequencias`: retorna o catálogo completo (as 6 + custom) como string de
  `json.dumps`, no formato
  `{id, slug, name, chords: [...], match_mode, legacy_id, created_at}`.
- `POST /sequencias`: corpo `{ "name": "...", "chords": ["Gm", "F"] }`. Valida
  nome e lista (não vazia, máximo de acordes, tokens com caracteres permitidos),
  gera `slug` e insere. Duplicata é definida como a mesma lista ordenada de
  acordes: nesse caso retorna a sequência existente de forma idempotente, em vez
  de criar outra. As respostas continuam sendo `json.dumps(...)`, não `jsonify`,
  inclusive os erros de validação.
- `GET /similares?sequencia=...`: aceita o `slug` de uma sequência do catálogo
  ou, por compatibilidade, a lista de acordes separada por vírgulas (ex.:
  `Gm,F` e `Bm,G,D,A`). Resolve primeiro por `slug`, depois pela lista ordenada
  já cadastrada. Se for `legacy`, usa `get_similares_por_sequencia`; se for
  `exact`, usa o matcher novo. Pagina com `pagina` como hoje; entrada
  desconhecida continua retornando `[]`.
- Não há login, autoria nem moderação. O catálogo é aberto e anônimo, conforme o
  enunciado.

### Frontend

Em `static/assets/js/controllers/sequencia.js`, remover os quatro objetos
hardcoded (`sequencia.js:2-37`) e carregar o catálogo com `GET /sequencias` na
inicialização. A lista `vm.sequenciasFamosas` passa a vir da API e é renderizada
do mesmo jeito em `static/templates/sequencia.html:5-8`. Adicionar um formulário
simples (nome + acordes separados por vírgula) que faz `POST /sequencias` e
recarrega a lista. `pesquisarPorSequencia` continua chamando
`similares?sequencia=...` (`sequencia.js:63-90`), agora com o `slug` da sequência
selecionada (ou a lista de acordes, mantendo compatibilidade). A rota
`#/porsequencia` (`routes.js:17-20`) não muda. Itens com acordes extras fora do
bloco continuam visíveis; não usamos `diferenca` para escondê-los.

## Alternativas consideradas e descartadas

- **Reutilizar `get_similares` por interseção de conjuntos.** Descartada porque
  ignora ordem e repetição e casa com qualquer música que tenha pelo menos um
  acorde em comum (para `Gm,F`, 40+ resultados, incluindo músicas com só `Gm` ou
  só `F`). Não modela "a sequência aparece na música" e exigiria um filtro
  explícito de contenção para não sugerir músicas que não têm os dois acordes.
- **Matching em tempo real também para as 6 originais.** Descartada porque quebra
  o critério de regressão: a pesquisa mostrou resultados diferentes dos atuais
  (6 músicas via `SEQ_FAMOSA` vs 40+ via acordes para `Gm,F`). As 6 continuam no
  caminho legado.
- **JSON/shelve/TinyDB/LMDB em vez de SQLite.** Descartadas pelos motivos da
  pesquisa: falta de transação ou consulta, concorrência fraca, dependência extra
  ou complexidade.
- **Manter a lista hardcoded no frontend e só adicionar um cadastro.** Descartada
  porque o enunciado exige que `#/porsequencia` reflita o catálogo real do
  backend.

## Escopo explícito

**Dentro do escopo:**

- Criar o banco SQLite, inicializar e semear as 6 sequências legadas.
- `GET /sequencias` e `POST /sequencias` (cadastro anônimo, validação e
  deduplicação).
- Matcher exato contíguo e ordenado sobre `musica.cifra` para sequências
  customizadas; caminho legado preservado para as 6.
- Resolução de `/similares?sequencia=` por slug ou lista de acordes, com
  paginação e o mesmo formato de resposta atual.
- Frontend `#/porsequencia` lendo o catálogo da API e formulário de cadastro.
- Persistência via volume Docker, documentada no ADR 0002.
- Teste de regressão das 6 sequências e testes do matcher e da API.

**Fora do escopo (e por quê):**

- Login, autoria, edição, exclusão ou moderação de sequências: o catálogo é
  aberto e anônimo; um CRUD completo aumenta o escopo sem requisito.
- Migrar músicas/gêneros para o banco: o enunciado fixa o CSV em memória.
- Normalização enarmônica, transposição ou equivalência de acordes: a pesquisa
  mostrou que `B != Bm` e que o comportamento atual é case-sensitive; mudar isso
  alteraria resultados.
- Matching fuzzy ou por conjunto de acordes: ver alternativa descartada.
- Alterar o pipeline offline, o CSV ou os scripts de scraping.
- Trocar `json.dumps(...)` por `jsonify` ou mudar o content type das respostas.
- Múltiplos containers, banco externo ou deploy em nuvem (ADR 0001).
- Framework de migração: o seed é idempotente no startup.
- Rate limiting/antispam: fica como risco em aberto para uma iteração futura.
