# Persistir sequências de acordes customizadas em SQLite

A busca por sequência sempre foi fechada: seis sequências fixas em `main.py` e
quatro no frontend, e os matches vinham de uma tag pré-computada no CSV
(`SEQ_FAMOSA`). Não havia como um visitante cadastrar uma sequência nova nem
como ela sobreviver a um reinício, porque não existia persistência. A tarefa
pede um catálogo aberto e anônimo, que cresça sem novo deploy, mantendo músicas e
gêneros no CSV em memória e a aplicação no Dockerfile único e local-only do ADR
0001.

Decidimos introduzir um banco SQLite de arquivo único para persistir apenas o
catálogo de sequências. O `sqlite3` é da stdlib, não adiciona dependência de pip
nem serviço externo, dá ACID, índices e consultas simples, e cabe no container
único já existente. O arquivo fica fora de `data/` (por exemplo
`/app/instance/sequences.db`, configurável por `SEQUENCES_DB`) para que um volume
Docker não esconda o `data/top/dataset_final.csv` embutido na imagem; a
persistência entre reinícios e recriações do container passa a exigir a montagem
de um volume nesse diretório. As seis sequências originais são semeadas de forma
idempotente com um `legacy_id` e um modo de matching, e continuam usando
`musica.seqs_famosas` exatamente como hoje. Sequências customizadas usam um
matcher novo sobre `musica.cifra`: a sequência precisa aparecer como um bloco
contíguo e ordenado de acordes.

Escolhemos o matcher exato contíguo porque ele tem uma definição precisa,
implementável e testável, preserva ordem e repetição e não exige normalização de
acordes. Deliberadamente não reutilizamos a pontuação por interseção de conjuntos
de `get_similares`: ela ignora ordem e casa com qualquer música que tenha pelo
menos um acorde em comum, o que gera resultados ruidosos (a pesquisa mediu 40+
para `Gm,F` contra 6 no caminho legado) e não responde se a sequência realmente
aparece na música.

As consequências são duas semânticas de matching convivendo no mesmo catálogo:
uma sequência customizada que duplique uma das seis originais pode retornar
resultados diferentes. As seis originais permanecem exatamente compatíveis, que é
o critério de regressão obrigatório. O SQLite permite um escritor por vez; isso é
aceitável com um worker do gunicorn e, se houver mais, deve ser combinado com WAL
e `busy_timeout`. O catálogo não escala horizontalmente, mas a aplicação continua
local-only e de container único. Não há framework de migração: inicialização e
seed são idempotentes no startup. Se o CSV for substituído, os seeds legados
podem precisar ser refeitos, e a troca de CSV já exige reinício hoje. A API
continua anônima, sem autoria ou moderação; validação e deduplicação ficam no
cadastro, mas rate limiting fica fora do escopo. As respostas continuam sendo
strings de `json.dumps`, não `jsonify`. Por fim, a persistência passa a depender
de um volume montado: sem ele, o catálogo sobrevive a reinícios do processo, mas
não à recriação do container, e isso precisa ser documentado junto ao comando de
execução.
