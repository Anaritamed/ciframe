# deciframe

Descubra as músicas que você já sabe tocar (e ainda não faz ideia). Busque por
título/artista, gênero, pelos acordes que você já manja, ou por sequências de
acordes famosas — o deciframe cruza isso com uma base de cifras e sugere
músicas parecidas.

Stack: backend Flask (Python) servindo uma API JSON + um frontend AngularJS
estático, numa base de dados carregada de um CSV em memória (sem banco).

## Rodando localmente

### Com Docker

```
docker build -t ciframe .
docker run -v ciframe-instance:/app/instance -p 8080:8080 ciframe
```

Acesse [http://localhost:8080](http://localhost:8080).

O catálogo de sequências customizadas fica em um SQLite em
`/app/instance/sequences.db` (configurável pela variável `SEQUENCES_DB`). O
volume `ciframe-instance` preserva esse catálogo quando o container é recriado;
sem o volume, ele sobrevive apenas a reinícios do processo.

### Com virtualenv

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Acesse [http://localhost:5000](http://localhost:5000).

---

Para convenções de contribuição, veja [CONTRIB.md](CONTRIB.md). Licença: [LICENSE](LICENSE).
