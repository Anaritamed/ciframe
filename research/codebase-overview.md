# deciframe — Pesquisa do Código-Fonte (estado atual)

## Resumo

O deciframe é uma aplicação Flask de container único apoiada em um CSV de 67.585 linhas carregado uma única vez na memória do processo no momento do import; não há banco de dados, ORM nem camada de persistência. O backend expõe oito rotas HTTP que retornam strings de `json.dumps(...)`, oferecendo busca por palavra-chave, similaridade por conjunto de acordes e busca por sequências de acordes fixas, com filtro por gênero e páginas fixas de 100 itens. O frontend é uma SPA legada em AngularJS 1.4.9 com jQuery, Bootstrap e ui-bootstrap carregados por CDN, servida pelo mesmo processo Flask e sem etapa de build. Os dados de músicas são produzidos por um pipeline offline de scrapers em Python 2 e scripts em R armazenados em `scripts/` e `data/top/`, e seis sequências de acordes estão fixas tanto no backend (`main.py`) quanto no frontend (`sequencia.js`, apenas quatro). O deploy é um Dockerfile único executando gunicorn; não há testes, configuração de CI, gerenciador de pacotes JavaScript, migrações nem banco de dados em tempo de execução.

---

## 1. Estrutura do repositório e runtime

| Área | Caminho | Papel |
|---|---|---|
| Entrada do backend | `main.py:1-280` | Aplicação Flask, ingestão do CSV, todas as rotas, lógica de busca |
| Objeto de domínio | `musica.py:1-25` | Objeto de valor `Musica` |
| Dependências de runtime | `requirements.txt:1-5` | Flask 3.1.3, gunicorn 23.0.0 |
| Container | `Dockerfile:1-12` | Python 3.9-slim, gunicorn na porta 8080 |
| SPA estática | `static/` | Aplicação AngularJS, templates, diretivas, CSS, imagens |
| Dados | `data/` | CSVs/TXTs, matriz de transposição, notas de teoria |
| Pipeline offline | `scripts/` | Scrapers e transformações de dados em R/Python |
| Documentação | `README.md`, `AGENTS.md`, `CONTRIB.md`, `docs/` | Instruções de execução, convenções, ADRs, templates de tarefas |

O processo Flask serve tanto a API quanto os arquivos estáticos. Quando executado diretamente, chama `app.run(debug=True)` (`main.py:279-280`); no container, o gunicorn carrega `main:app` (`Dockerfile:12`).

Não existem arquivos de teste, diretório `.github/`, `Makefile` nem configuração de CI. Uma busca no repositório retorna apenas `docs/features/sequencias-customizadas/04-test-report.md` como arquivo com nome relacionado a testes, e ele é um template de documentação.

---

## 2. Backend

### 2.1 Inicialização e índice em memória

`main.py:37-47` declara estado mutável no nível de módulo:

- `genero_musicas = {}` — gênero → lista de `Musica`
- `generos = set()` — nomes de gêneros únicos
- `acordes = set()` — nomes de acordes únicos
- `sequencias = {'BmGDA': 0, 'CGAmF': 1, 'EmG': 2, 'CA7DmG7': 3, 'GmF': 4, 'CC7FFm': 5}` — seis sequências fixas mapeadas para IDs inteiros (`main.py:40-45`)
- `musicas_dict = {}` — ID único → `Musica`

As posições das colunas são constantes fixas (`main.py:26-34`): `ARTISTA_ID=0`, `MUSICA_ID=1`, `ARTISTA=2`, `MUSICA=3`, `GENERO=4`, `POPULARIDADE=5`, `TOM=6`, `SEQ_FAMOSA=7`, `CIFRA=8`. `TAM_PAGINA=100` (`main.py:35`).

O CSV é aberto no import do módulo (`main.py:49`). A primeira linha é lida e descartada (`main.py:50`); a primeira linha de `data/top/dataset_final.csv` é um registro de dados, não um cabeçalho, portanto uma linha de dados não é indexada. Cada linha seguinte tem todos os caracteres `"` e todas as substrings `NA` removidos, depois o último caractere é removido e, em seguida, a linha é dividida por `,` (`main.py:52-55`). A popularidade é convertida com `.replace('.', '')` e depois para `int` (`main.py:56`). O campo `CIFRA` é dividido por `;` e passado por `limpa_cifra` (`main.py:58-61`); um `CIFRA` vazio torna-se `[]`. O campo `SEQ_FAMOSA` é dividido por `;` (`main.py:63`).

`limpa_cifra` (`main.py:11-23`) descarta tokens em branco; para tokens que contêm `|`, pega o primeiro token antes do primeiro pipe e antes do primeiro espaço; caso contrário, divide por espaços e acrescenta todos os tokens.

À medida que cada linha é processada, o gênero é adicionado a `generos` (`main.py:66`), um objeto `Musica` é construído e inserido em `musicas_dict` (`main.py:69-74`), cada acorde é adicionado a `acordes` (`main.py:76-78`) e o objeto é anexado à lista do gênero (`main.py:80-85`). Após o carregamento, `musicas` é um `OrderedDict` de todas as músicas ordenado por popularidade decrescente (`main.py:87-89`), `generos` torna-se uma lista (`main.py:92`) e cada lista de gênero é ordenada por popularidade decrescente (`main.py:94-96`). `f.close()` está em `main.py:98`.

Fatos observados no carregamento do CSV atual:

- O arquivo tem 16 MB e 67.586 linhas; 67.585 linhas de dados são processadas após o descarte da primeira linha.
- São carregados 52 valores distintos de gênero, incluindo `R&B;`.
- 514 linhas têm valor não vazio em `SEQ_FAMOSA`.
- 8.141 linhas têm valor vazio em `CIFRA`.
- Ocorrem 13 valores distintos de `TOM`.
- Todas as linhas amostradas contêm nove campos separados por vírgula.

### 2.2 Modelo de domínio

`Musica.__init__` (`musica.py:3-22`) armazena: `id_artista`, `nome_artista`, `id_musica`, `nome_musica`, `genero`, `popularidade`, `tom`, `cifra`, `seqs_famosas`. Deriva `acordes` como `list(set(cifra))` (`musica.py:17`) e `id_unico_musica` como `'%s_%s' % (id_artista, id_musica)` (`musica.py:20`). Constrói `url` como `http://www.cifraclub.com.br/<id_artista>/<id_musica>` (`musica.py:22`). `__str__` retorna `id_unico_musica,genero,popularidade` (`musica.py:24-25`).

### 2.3 Superfície HTTP

| Rota | Handler | Parâmetros | Comportamento |
|---|---|---|---|
| `GET /` | `main.py:101-103` | — | `send_static_file('index.html')` |
| `GET /<path:path>` | `main.py:109-112` | path | `send_static_file(path)` para qualquer caminho não correspondido |
| `GET /search` | `main.py:114-142` | `key` (obrigatório), `generos` (CSV opcional), `pagina` (padrão `1`) | Correspondência de palavra-chave sem acentos contra artista + nome da música; retorna subconjunto paginado |
| `GET /musicas` | `main.py:154-156` | — | Retorna `[v.__dict__ for v in musicas.values()]` para todas as músicas |
| `GET /generos` | `main.py:158-160` | — | Retorna a lista `generos` |
| `GET /acordes` | `main.py:162-164` | — | Retorna `list(acordes)` |
| `GET /musica/<m_id>/` | `main.py:166-168` | path `m_id` | Retorna `musicas[m_id].__dict__` indexado por `id_unico_musica` |
| `GET /similares` | `main.py:170-201` | `acordes`, `id_unico_musica`, `sequencia`, `generos`, `pagina` | Similaridade por conjunto de acordes, similaridade por música ou busca por sequência; paginado exceto no caminho de sequência |

`/search` converte `key` para minúsculas e normaliza acentos (`main.py:118-119`); a ausência de `key` provoca erro quando `.lower()` é chamado. Seleciona o conjunto de gêneros a partir de `generos` ou do valor da query `generos` separado por vírgulas (`main.py:121-123`), filtra a coleção ordenada por popularidade (`main.py:125`) e então considera uma música correspondente somente quando todas as palavras da consulta estão presentes na lista de tokens normalizados de `artista + ' ' + música` (`main.py:128-131`). Os campos retornados são `id_unico_musica`, `id_artista`, `id_musica`, `nome_artista`, `nome_musica`, `genero`, `url` (`main.py:132-140`). A resposta é `json.dumps(get_pagina(out, pagina_tag))` (`main.py:142`).

Tratamento de `sequencia` em `/similares` (`main.py:190-197`): as vírgulas são removidas do valor da query (`replace(',', '')`) e, se a string resultante for uma chave de `sequencias`, o ID inteiro é consultado e `get_similares_por_sequencia` é chamado; caso contrário, o handler retorna `json.dumps([])`. Se `acordes` for fornecido, ele é dividido por vírgulas (`main.py:184-186`); senão, se `id_unico_musica` for fornecido, os `acordes` da música são usados (`main.py:187-189`); senão, se `sequencia` foi fornecida, o caminho de sequência retorna antecipadamente. Se nenhum de `acordes`, `id_unico_musica` ou uma `sequencia` reconhecida for fornecido, `acordes` permanece `[]` e `get_similares([], ...)` retorna uma lista vazia.

`get_similares_por_sequencia` (`main.py:203-223`) filtra por gênero e então mantém músicas em que `str(id_seq) in musica.seqs_famosas`. Os campos retornados incluem popularidade, acordes, gênero e URL (`main.py:210-220`).

`get_similares` (`main.py:230-263`) filtra por gênero, exclui a própria música por `id_unico_musica` (`main.py:238`), calcula `intersecao = set(acordes) ∩ set(musica.acordes)` e `diferenca = set(musica.acordes) - set(acordes)` (`main.py:240-241`), mantém apenas músicas com interseção não vazia (`main.py:245`) e retorna objetos com as listas `diferenca` e `intersecao` adicionadas (`main.py:246-258`). Os resultados são ordenados por `len(diferenca)` crescente e depois por `len(intersecao)` decrescente (`main.py:262-263`).

`apply_filtro` (`main.py:266-272`) concatena as listas por gênero para cada gênero solicitado que existe em `generos`; nomes de gêneros desconhecidos não contribuem com nada. `get_pagina` (`main.py:226-228`) fatia com `(pagina - 1) * 100` baseado em zero.

`add_header` define `Access-Control-Allow-Origin: *` em toda resposta (`main.py:274-277`). Todos os handlers retornam `json.dumps(...)` em vez de `jsonify`, portanto as respostas são strings simples; aplica-se o content type padrão do Flask.

A docstring de `/musicas` afirma que o serviço é paginado (`main.py:149-153`), enquanto o handler retorna a coleção completa de `musicas` (`main.py:154-156`). `/musica/<m_id>/` espera a chave composta `id_unico_musica` (`main.py:166-168`).

### 2.4 Normalização de palavras-chave

`remover_combinantes` (`main.py:145-147`) aplica normalização Unicode NFD e remove caracteres da categoria `Mn`, de modo que a busca é insensível a acentos tanto na consulta quanto no texto pesquisável das músicas (`main.py:119`, `main.py:129-130`).

---

## 3. Dataset e pipeline offline de dados

### 3.1 Dataset principal

`data/top/dataset_final.csv` é um arquivo separado por vírgulas sem cabeçalho, com nove campos por linha, correspondentes às constantes de `main.py:26-34`. Exemplo da primeira linha:

```
14-bis,a-qualquer-tempo,14 Bis,A Qualquer Tempo,MPB,70115,B,NA,E;F#;E;F#;...
```

Os campos são: slug do artista, slug da música, artista de exibição, música de exibição, gênero, popularidade/visualizações, tom (`TOM`), IDs de sequências famosas separados por ponto e vírgula (`SEQ_FAMOSA`) e progressão de acordes separada por ponto e vírgula (`CIFRA`). Os valores de `SEQ_FAMOSA` são os IDs numéricos de `data/mapeamento_sequencias_famosas.txt`:

| ID | Nome | Sequência |
|---|---|---|
| 0 | Sequência de Bm | Bm - G - D - A |
| 1 | Sequência de C | C - G - Am - F |
| 2 | Sequência Em | Em - G |
| 3 | Sequência de C (Samba) | C - A7 - Dm - G7 |
| 4 | Sequência de Gm | Gm - F |
| 5 | Sequência de C (Samba cont.) | C - C7 - F - Fm |

Esses IDs correspondem às seis chaves de `sequencias` em `main.py:40-45`, na mesma ordem.

### 3.2 Outros ativos de dados

- `data/top/visualizacoes.csv`, `data/top/visualizacoes_pontos.csv` — artista, música, contagem de visualizações.
- `data/top/chords-transitions-empty.csv` — matriz vazia de transições de acordes com 42 colunas nomeadas.
- `data/top/artista_musica_estilo.txt` — artista, música, estilo (CSV sem cabeçalho).
- `data/top/top_artistas.txt`, `data/top/url-estilos.txt`, `data/top/top_artistas.txt_*.songs` — entradas/saídas de crawling.
- `data/top/html_estilos/*.html` — 73 páginas de listagem de gêneros salvas.
- `data/dataset_seq_notas.csv` — dataset com cabeçalho e colunas `ARTISTA`, `MUSICA`, `ESTILO`, `TOM`, `VISUALIZACOES`, `CIFRA`, `NCIFRA` (acordes normalizados).
- `data/data-cavaco.csv` — `artista,musica,tom,sequencia`.
- `data/transposition_matrix2.csv` — matriz de graus entre tom e acorde.
- `data/mapeamento_sequencias_famosas.txt`, `data/teoria`, `data/artistas_por_letra.txt` — rótulos de sequências, notas de teoria de tons, índice de crawling.

Os arquivos `.songs` (`data/top/top_artistas.txt_0.songs` a `_3.songs`) e as listas de URLs são artefatos de scraper. `data/cavaco_htlms.tar.gz` é um arquivo compactado de HTML.

### 3.3 Scripts do pipeline

- `scripts/generate_data_set.py:1-91` — scraper em Python 2 com BeautifulSoup. Define `get_famosas` (`scripts/generate_data_set.py:7-24`) com as mesmas seis sequências em minúsculas e separadas por ponto e vírgula; lê HTML em `#cifra_tom`, `#breadcrumb`, `h2.subtitulo`, `h1.titulo`, `div.cifra_exib` e emite as nove colunas do dataset.
- `scripts/cifra_parser.py:1-27` — scraper em Python 2 para extração de artista/música/tom/acordes.
- `scripts/parse_artistas_estilos.py:1-30` — helper em Python 2; o corpo com BeautifulSoup está comentado.
- `scripts/parse_estilos.py:1-22` — scraper em Python 2 para URLs de listagem de gêneros.
- `scripts/DownloadAll.java:1-72` + `scripts/collect_song_list.sh:1-6` — crawler Java/jsoup que grava listas de links `.songs` e rotaciona a saída a cada 25.000 links.
- `scripts/download_band_names.sh:1-11`, `scripts/download_cifras.sh:1-9` — helpers de download via curl.
- `scripts/normalize_chords.R:1-41` e `scripts/simplify_chords.R:1-36` — normalização de acordes em R/dplyr usando `data/transposition_matrix2.csv` e as colunas `ARTISTA`, `MUSICA`, `CIFRA`, `TOM`.
- `scripts/build-chords-transitions.R:1-77` — construtor de matriz de transições em R que lê `data/dataset_seq_notas.csv` e `data/top/chords-transitions-empty.csv`; faz referência a um `musicas_df` não definido em `scripts/build-chords-transitions.R:77`.
- `scripts/add_estilos.py:1-45` e `scripts/add_estilos.R:1-10` — fazem join dos dados de artista/música/estilo aos dados de músicas; a versão Python usa sintaxe de print do Python 2 (`scripts/add_estilos.py:36-37`).
- `data/top/merge_datasets.R:1-15` — faz join de `dataset.csv` e `visualizacoes_pontos.csv` e grava um `dataset_final.csv` de cinco colunas.
- `data/top/popularidade.R:1-9` — agrega visualizações por artista.

Os scripts R esperam o esquema antigo de cinco colunas de `dataset_final.csv` (`ARTISTA`, `MUSICA`, `VISUALIZACOES`, `TOM`, `CIFRA`) e nomes de colunas como cabeçalho (`scripts/normalize_chords.R:33-36`, `data/top/merge_datasets.R:3-15`), enquanto o `data/top/dataset_final.csv` versionado não tem cabeçalho e possui nove campos consumidos posicionalmente por `main.py`. Os scrapers Python usam sintaxe de Python 2.

---

## 4. Frontend

### 4.1 Bootstrap e dependências

`static/index.html:1-149` define `ng-app="deciframeApp"` e `ng-controller="MainController"` (`static/index.html:2`, `static/index.html:22`). Carrega Bootstrap 3.3.6 CSS, Google Fonts, `assets/css/app.css` e `icons.css` locais (`static/index.html:13-20`). Os scripts de runtime são carregados por CDN: jQuery 1.11.3, Bootstrap 3.3.6 JS, AngularJS 1.4.9 core/route/animate e angular-ui-bootstrap 2.1.4 (`static/index.html:125-134`). Os scripts locais são `ngprogress.js`, o módulo da aplicação, as rotas, seis controllers e duas diretivas (`static/index.html:135-147`). O Google Analytics usa `UA-85286010-1` (`static/index.html:25-32`). O markup do menu/time é inline (`static/index.html:34-121`), e o conteúdo roteado é renderizado em `<div class="page" ng-view></div>` (`static/index.html:123`).

`static/bower.json:1-26` declara uma dependência, `ng-material-floating-button` (`ng-mfb#~0.6.2`); `static/.bowerrc:1-3` aponta o Bower para `assets/vendor`, que é ignorado pelo Git (`.gitignore:1`). Nenhum diretório vendor ou instalação do Bower está versionado.

### 4.2 Módulo Angular e constantes

`static/assets/js/app.js:1-58` cria o módulo `deciframeApp` com as dependências `ngRoute`, `ngAnimate`, `ngProgress`, `ui.bootstrap` (`static/assets/js/app.js:1-2`). Declara `RESTAPI = { url: 'http://localhost:5003' }` (`static/assets/js/app.js:3-5`) e um array estático `GENEROS` com 51 strings de gênero (`static/assets/js/app.js:6-58`). O backend expõe atualmente 52 gêneros; a lista do frontend não inclui `R&B;` e inclui todos os demais gêneros do backend. `RESTAPI` não é referenciado por nenhum outro arquivo.

### 4.3 Rotas

`static/assets/js/routes.js:1-29` define:

| Rota hash | Template | Controller | Alias do controller |
|---|---|---|---|
| `#/` | `templates/home.html` | `HomeController` | — |
| `#/poracordes` | `templates/acordes.html` | `AcordesController` | `Chords` |
| `#/pormusica` | `templates/musica.html` | `MusicaController` | `Musica` |
| `#/porsequencia` | `templates/sequencia.html` | `SequenciaController` | `Sequencia` |
| `#/sobre` | `templates/about.html` | `AboutController` | — |
| caso contrário | redireciona para `/` | — | — |

### 4.4 Controllers

| Arquivo | Comportamento |
|---|---|
| `static/assets/js/controllers/main.js:1-12` | Alternância do menu e helper de rota ativa |
| `static/assets/js/controllers/home.js:1-4` | Define `pageTitle` e `pageClass` |
| `static/assets/js/controllers/about.js:1-4` | Define `pageTitle` e `pageClass` |
| `static/assets/js/controllers/acordes.js:1-125` | Paleta fixa de acordes agrupada de C a B; estado de múltipla seleção; chama `similares?acordes=...` |
| `static/assets/js/controllers/musica.js:1-80` | Busca typeahead via `search?key=...`; chama `similares?id_unico_musica=...` |
| `static/assets/js/controllers/sequencia.js:1-105` | Quatro objetos de sequência fixos; chama `similares?sequencia=...` |
| `static/assets/js/controllers/search.js:1-26` | Stub de desenvolvimento; não é carregado por `index.html` |

Detalhes:

- **Paleta de acordes** — `acordes.js:2-44` fixa sete arrays (`acordesC` … `acordesB`) com nomes de acordes e cores; `acordes.js:47-53` os insere em `vm.acordes`. `addAcorde` alterna a pertinência e refaz a busca imediatamente (`acordes.js:63-71`). `createChordsString` junta os nomes dos acordes selecionados com vírgulas (`acordes.js:76-82`). `pesquisarPorAcordes` monta `similares?acordes=...` e acrescenta `&generos=...` quando um gênero está selecionado (`acordes.js:84-108`).
- **Busca por música** — `musica.js:14-20` executa `search?key=<valor>`; `musica.js:43-70` chama `similares?id_unico_musica=...`. `musica.html:13-18` configura o typeahead com comprimento mínimo 3 e espera de 1.000 ms.
- **Busca por sequência** — `sequencia.js:2-31` define quatro sequências: `Bm G D A`, `C G Am F`, `Gm F` e `C C7 F Fm`; `sequencia.js:33-37` popula `vm.sequenciasFamosas`. O backend tem seis sequências (`main.py:40-45`), incluindo `Em G` e `C A7 Dm G7`, que não estão nessa lista fixa do frontend. `sequencia.js:55-61` junta os nomes dos acordes selecionados com vírgulas; `sequencia.js:63-90` chama `similares?sequencia=...`; `sequencia.js:92-95` limpa a seleção.
- **URL base da API** — `apiUrl` é inicializado como `""` em `acordes.js:91`, `musica.js:12` e `sequencia.js:72`, portanto as requisições do navegador são caminhos relativos na mesma origem.

### 4.5 Templates e diretivas

- `static/templates/home.html:58-86` liga para `#/poracordes`, `#/pormusica`, `#/porsequencia`; `home.html:6-8` embute a diretiva da esfinge.
- `static/templates/acordes.html:6-8` renderiza a paleta de acordes; `acordes.html:19-38` renderiza acordes selecionados e seletor de gênero; `acordes.html:40-91` renderiza músicas correspondentes (`ng-hide="music.diferenca.length"`) e músicas que exigem acordes extras (`ng-show="music.diferenca.length"`), incluindo `df-hex` para `music.diferenca`.
- `static/templates/musica.html:8-18` input typeahead; `musica.html:46-113` renderiza a música selecionada e músicas similares usando a mesma divisão por `diferenca`.
- `static/templates/sequencia.html:5-8` renderiza a lista fixa de sequências; `sequencia.html:19` mostra a sequência selecionada; `sequencia.html:34` renderiza os acordes da sequência selecionada com clique para limpar; `sequencia.html:40-59` renderiza os resultados.
- `static/templates/about.html:1-9` mostra apenas o título da página.
- `static/assets/js/directives/df-hex.js:1-12` define `<df-hex>` com escopo isolado `acorde`, `acordeColor`, `acordeChecked`, `small`; `static/templates/directives/df-hex.html:1-9` renderiza o SVG hexagonal e o rótulo do acorde.
- `static/assets/js/directives/df-esfinge.js:1-9` define `<df-esfinge>` com escopo isolado `dfAnimated`; `static/templates/directives/df-esfinge.html:1-326` contém o SVG da esfinge e as classes de animação CSS.
- `static/assets/js/ngprogress.js:1-218` embute o ngProgress 1.1.2 e fornece `ngProgressFactory`.
- `static/assets/css/app.css` (16 KB) e `static/assets/css/icons.css` (4 KB) concentram estilos de layout e ícones; `static/assets/css/fonts/` contém o conjunto de fontes icomoon.

---

## 5. Deploy e configuração

`Dockerfile:1-12` usa `python:3.9-slim`, define `/app`, instala `requirements.txt`, copia o repositório, expõe a porta 8080 e inicia `gunicorn --bind 0.0.0.0:8080 main:app`. `requirements.txt:4-5` fixa Flask 3.1.3 e gunicorn 23.0.0. `.dockerignore:1-4` exclui `.git`, `.venv`, `__pycache__` e `*.pyc`; `.gitignore:1-4` exclui `static/assets/vendor`, `.venv`, `*.pyc` e `__pycache__/`.

`README.md:11-31` documenta tanto o fluxo com Docker (`-p 8080:8080`) quanto o uso de virtualenv (`python main.py`, porta 5000). `AGENTS.md` registra a stack, comandos de execução, endpoint de verificação (`/generos`) e armadilhas: alterações no CSV exigem reinício, os endpoints retornam strings de `json.dumps` em vez de `jsonify`, e `docs/adr/` deve ser consultado antes de mudanças de deploy.

ADRs:

- `docs/adr/0001-local-only-docker-deploy.md:1-15` registra a remoção das configurações de App Engine/Heroku e a adoção de um único Dockerfile local-only; o alvo de nuvem está indefinido.
- `docs/adr/0002-persist-custom-sequences.md:1-13` é um template não preenchido para uma decisão futura de persistência.
- `docs/adr/0003-lift-frontend-freeze.md:1-20` registra que o frontend legado em AngularJS pode ser modificado quando uma tarefa exigir; a stack em si não está sendo modernizada.

`docs/features/sequencias-customizadas/` contém cinco templates de fase (`00-enunciado.md` a `04-test-report.md`) descrevendo uma tarefa full-stack de sequências customizadas; as seções a serem preenchidas pelo estudante permanecem como placeholders, exceto o enunciado da tarefa.

---

## 6. Fluxos de dados entre componentes

1. **Inicialização** — `main.py:49-98` lê `data/top/dataset_final.csv` e constrói `musicas`, `musicas_dict`, `generos`, `acordes` e `genero_musicas` em memória; o gunicorn serve `main:app` (`Dockerfile:12`) e o Flask responde tanto à API quanto às requisições estáticas.
2. **Carregamento da página estática** — `GET /` serve `static/index.html` (`main.py:101-103`); o AngularJS inicializa `deciframeApp`, roteia para um template e os controllers disparam XHRs na mesma origem.
3. **Busca por acordes** — `acordes.js:84-108` seleciona acordes → `GET /similares?acordes=...&generos=...` → `main.py:170-201` → `get_similares` (`main.py:230-263`) → lista JSON → o template renderiza músicas com `diferenca` vazia/não vazia.
4. **Busca por música** — typeahead de `musica.js:14-20` → `GET /search?key=...` → `main.py:114-142` → correspondências ordenadas por popularidade → `musica.js:43-70` envia `GET /similares?id_unico_musica=...` → `get_similares` usando o conjunto de acordes daquela música.
5. **Busca por sequência** — `sequencia.js:63-90` envia uma sequência unida por vírgulas → `main.py:190-197` remove as vírgulas, consulta o mapa `sequencias` de seis chaves e então `get_similares_por_sequencia` (`main.py:203-223`) compara com a lista `seqs_famosas` derivada do CSV.
6. **Construção de dados (offline)** — os scrapers produzem artefatos HTML/`.songs`/CSV; `generate_data_set.py` deriva `SEQ_FAMOSA` usando as mesmas seis sequências; scripts R produzem acordes normalizados e matrizes de transição; o CSV versionado é o que a aplicação em execução consome.

---

## 7. Inventário do estado atual e discrepâncias factuais

Estes são comportamentos presentes no código hoje, registrados sem recomendação:

- O carregador do CSV descarta a primeira linha física (`main.py:49-50`); o arquivo não tem linha de cabeçalho, e sua primeira linha é um registro de dados.
- O carregador remove toda substring `NA` globalmente (`main.py:53`), além de tratar `NA` como valor vazio.
- O dataset é dividido por vírgulas após apenas a remoção de aspas, sem parsing de CSV (`main.py:53-55`).
- `/musicas` retorna todas as músicas apesar da docstring mencionar paginação (`main.py:149-156`).
- `/musica/<m_id>/` usa como chave o `id_unico_musica` (`artista_id_musica_id`), não um ID numérico de música (`main.py:166-168`, `musica.py:20`).
- `/similares?sequencia=` só reconhece as seis chaves concatenadas exatas de `main.py:40-45`; valores não reconhecidos retornam `[]` (`main.py:194-197`).
- `/similares` sem `acordes`, `id_unico_musica` ou `sequencia` reconhecida retorna `[]` porque `acordes` permanece vazio (`main.py:184-199`).
- O frontend define quatro sequências (`sequencia.js:2-31`) enquanto o backend define seis (`main.py:40-45`).
- A constante `GENEROS` do frontend (`app.js:6-58`) é estática e omite o gênero `R&B;` do backend.
- `RESTAPI` (`app.js:3-5`) é declarado mas não usado; os controllers usam `apiUrl = ""`.
- `search.js` (`static/assets/js/controllers/search.js:1-26`) contém um stub de desenvolvimento e não é carregado por `index.html`.
- `static/bower.json` declara `ng-material-floating-button`, mas `static/assets/vendor` é ignorado e está ausente.
- Os scripts R de preparação de dados fazem referência a um `dataset_final.csv` de cinco colunas com cabeçalho (`merge_datasets.R:15`, `normalize_chords.R:33-36`), enquanto o arquivo versionado não tem cabeçalho e possui nove campos.
- Os scripts de scraper em Python usam sintaxe de Python 2 (`scripts/generate_data_set.py:5`, `scripts/cifra_parser.py:6`, `scripts/add_estilos.py:36-37`).
- `data/top/merge_datasets.R:3` lê `dataset.csv`, que não está presente no repositório.
- `scripts/build-chords-transitions.R:77` faz referência a `musicas_df`, que não está definido naquele arquivo.
- `.playground:1-13` ainda descreve o projeto inicial de Flask para Google App Engine e lista `app.yaml`/`appengine_config.py`, que não existem mais.
- Não existe no repositório nenhum teste, executor de testes, workflow de CI, esquema de banco, migração ou ferramenta de build JavaScript.

---

## 8. Estado do Git

Branch atual: `master`, limpa, sincronizada com `origin/master` em `fb97001` (`Update 00-enunciado.md`). Commits recentes: `e03bc62` removeu a restrição de congelamento do frontend, `3b8ec59` adicionou o enunciado/templates de sequências customizadas, `d834fb7` adicionou `AGENTS.md` e simplificou o README, `ff57dc5` substituiu as configurações de App Engine/Heroku pelo Dockerfile e modernizou dependências, e `249bdc9` corrigiu a compatibilidade com Python 3 e a API local. Os branches remotos incluem `origin/app-engine-deploy`, `origin/chord-search`, `origin/final-round`, `origin/frontend`, `origin/gh-pages` e `origin/master`.
