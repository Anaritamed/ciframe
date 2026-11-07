# coding: utf-8
"""Catálogo de sequências de acordes e matcher exato.

Este módulo é independente de ``main.py`` para que o banco e o matcher possam
ser testados sem carregar o CSV de músicas. Músicas e gêneros continuam vindo do
CSV; apenas o catálogo de sequências é persistido em SQLite.
"""
import json
import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone

MAX_NAME_LENGTH = 80
MAX_CHORDS = 16
MAX_CHORD_LENGTH = 17

# Raiz A-G (case-sensitive), acidente opcional e sufixo com caracteres usuais
# de cifra. Vírgula e espaço ficam de fora de propósito.
CHORD_RE = re.compile(r'^[A-G](?:[#b])?[A-Za-z0-9#+\-/()°.ºø]*$')

LEGACY_SEQUENCES = [
    {
        'legacy_id': 0,
        'name': 'Bm G D A',
        'chords': ['Bm', 'G', 'D', 'A'],
        'slug': 'bm-g-d-a',
    },
    {
        'legacy_id': 1,
        'name': 'C G Am F',
        'chords': ['C', 'G', 'Am', 'F'],
        'slug': 'c-g-am-f',
    },
    {
        'legacy_id': 2,
        'name': 'Em G',
        'chords': ['Em', 'G'],
        'slug': 'em-g',
    },
    {
        'legacy_id': 3,
        'name': 'C A7 Dm G7',
        'chords': ['C', 'A7', 'Dm', 'G7'],
        'slug': 'c-a7-dm-g7',
    },
    {
        'legacy_id': 4,
        'name': 'Gm F',
        'chords': ['Gm', 'F'],
        'slug': 'gm-f',
    },
    {
        'legacy_id': 5,
        'name': 'C C7 F Fm',
        'chords': ['C', 'C7', 'F', 'Fm'],
        'slug': 'c-c7-f-fm',
    },
]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sequences (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  chords TEXT NOT NULL,
  match_mode TEXT NOT NULL CHECK (match_mode IN ('legacy','exact')),
  legacy_id INTEGER UNIQUE,
  created_at TEXT NOT NULL
)
"""

CREATE_CHORDS_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_sequences_chords ON sequences(chords)
"""


class SequenceValidationError(ValueError):
    """Erro de validação de uma sequência enviada pelo cliente."""


def connect(path):
    """Abre uma conexão configurada com WAL e busy_timeout."""
    conn = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=5000')
    return conn


def init_db(path):
    """Cria o diretório e o schema, devolvendo uma conexão pronta para uso."""
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = connect(path)
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(CREATE_CHORDS_INDEX_SQL)
    conn.commit()
    return conn


def seed_legacy(conn):
    """Garante as 6 sequências legadas de forma idempotente.

    Devolve quantas linhas legadas existem ao final.
    """
    created_at = _utc_now()
    for sequence in LEGACY_SEQUENCES:
        conn.execute(
            """
            INSERT OR IGNORE INTO sequences
                (slug, name, chords, match_mode, legacy_id, created_at)
            VALUES (?, ?, ?, 'legacy', ?, ?)
            """,
            (
                sequence['slug'],
                sequence['name'],
                _canonical_chords(sequence['chords']),
                sequence['legacy_id'],
                created_at,
            ),
        )
    conn.commit()
    row = conn.execute(
        'SELECT COUNT(*) FROM sequences WHERE legacy_id IS NOT NULL'
    ).fetchone()
    return row[0]


def list_sequences(conn):
    """Devolve o catálogo completo: legadas primeiro, depois customizadas."""
    rows = conn.execute(
        """
        SELECT * FROM sequences
        ORDER BY (legacy_id IS NULL), legacy_id, id
        """
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def create_sequence(conn, name, chords):
    """Valida, deduplica e insere uma sequência customizada.

    Devolve ``(sequencia, criada)``; ``criada`` é False quando a mesma lista
    ordenada de acordes já existia (inclusive se for uma legada).
    """
    name = _validate_name(name)
    chords = _validate_chords(chords)
    canonical = _canonical_chords(chords)

    existing = _find_by_chords(conn, canonical)
    if existing is not None:
        return _row_to_dict(existing), False

    base_slug = _slugify(name)
    created_at = _utc_now()

    for _ in range(5):
        slug = _unique_slug(conn, base_slug)
        try:
            cursor = conn.execute(
                """
                INSERT INTO sequences
                    (slug, name, chords, match_mode, legacy_id, created_at)
                VALUES (?, ?, ?, 'exact', NULL, ?)
                """,
                (slug, name, canonical, created_at),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            existing = _find_by_chords(conn, canonical)
            if existing is not None:
                return _row_to_dict(existing), False
            # Colisão de slug: tenta de novo com outro sufixo.
            continue

        row = conn.execute(
            'SELECT * FROM sequences WHERE id = ?', (cursor.lastrowid,)
        ).fetchone()
        return _row_to_dict(row), True

    raise SequenceValidationError('não foi possível gerar um slug único')


def resolve_sequence(conn, ident):
    """Resolve uma sequência por slug ou pela lista de acordes separada por vírgula."""
    if not isinstance(ident, str):
        return None
    ident = ident.strip()
    if not ident:
        return None

    row = conn.execute(
        'SELECT * FROM sequences WHERE slug = ?', (ident,)
    ).fetchone()
    if row is not None:
        return _row_to_dict(row)

    try:
        chords = parse_chords_csv(ident)
    except SequenceValidationError:
        return None

    row = _find_by_chords(conn, _canonical_chords(chords))
    return _row_to_dict(row) if row is not None else None


def parse_chords_csv(raw):
    """Converte ``'Gm, F'`` em ``['Gm', 'F']``, ignorando espaços e vazios."""
    if not isinstance(raw, str):
        raise SequenceValidationError('lista de acordes inválida')
    chords = [token.strip() for token in raw.split(',')]
    chords = [token for token in chords if token]
    if not chords:
        raise SequenceValidationError('informe ao menos um acorde')
    return chords


def match_exact(cifra, chords):
    """Indica se ``chords`` aparece como bloco contíguo e ordenado em ``cifra``."""
    if not chords or len(chords) > len(cifra):
        return False
    size = len(chords)
    for start in range(len(cifra) - size + 1):
        if cifra[start:start + size] == chords:
            return True
    return False


def exact_matches(songs, chords, generos_key=None):
    """Varre ``songs`` e devolve os matches exatos no formato do caminho legado.

    ``songs`` pode já vir filtrado por gênero; ``generos_key``, quando informado,
    restringe adicionalmente pelo gênero da música.
    """
    if not chords:
        return []

    generos = set(generos_key) if generos_key is not None else None
    similares = []
    for musica in songs:
        if generos is not None and musica.genero not in generos:
            continue
        if match_exact(musica.cifra, chords):
            similares.append({
                'id_unico_musica': musica.id_unico_musica,
                'id_artista': musica.id_artista,
                'id_musica': musica.id_musica,
                'nome_artista': musica.nome_artista,
                'nome_musica': musica.nome_musica,
                'popularidade': musica.popularidade,
                'acordes': musica.acordes,
                'genero': musica.genero,
                'url': musica.url,
            })
    return similares


def _canonical_chords(chords):
    return json.dumps(list(chords), ensure_ascii=False, separators=(',', ':'))


def _find_by_chords(conn, canonical):
    return conn.execute(
        'SELECT * FROM sequences WHERE chords = ?', (canonical,)
    ).fetchone()


def _row_to_dict(row):
    data = dict(row)
    data['chords'] = json.loads(data['chords'])
    return data


def _validate_name(name):
    if not isinstance(name, str):
        raise SequenceValidationError('nome é obrigatório')
    name = name.strip()
    if not name:
        raise SequenceValidationError('nome é obrigatório')
    if len(name) > MAX_NAME_LENGTH:
        raise SequenceValidationError(
            'nome deve ter no máximo %d caracteres' % MAX_NAME_LENGTH
        )
    return name


def _validate_chords(chords):
    if not isinstance(chords, (list, tuple)):
        raise SequenceValidationError('acordes devem ser uma lista')
    if not chords:
        raise SequenceValidationError('informe ao menos um acorde')
    if len(chords) > MAX_CHORDS:
        raise SequenceValidationError(
            'no máximo %d acordes por sequência' % MAX_CHORDS
        )

    normalized = []
    for chord in chords:
        if not isinstance(chord, str):
            raise SequenceValidationError('acorde inválido')
        chord = chord.strip()
        if not chord:
            raise SequenceValidationError('acorde inválido')
        if len(chord) > MAX_CHORD_LENGTH:
            raise SequenceValidationError(
                'acorde muito longo: %s' % chord[:MAX_CHORD_LENGTH]
            )
        if not CHORD_RE.match(chord):
            raise SequenceValidationError('acorde inválido: %s' % chord)
        normalized.append(chord)
    return normalized


def _slugify(name):
    decomposed = unicodedata.normalize('NFKD', name)
    without_marks = ''.join(
        ch for ch in decomposed if unicodedata.category(ch) != 'Mn'
    )
    slug = re.sub(r'[^a-z0-9]+', '-', without_marks.lower()).strip('-')
    return slug or 'sequencia'


def _unique_slug(conn, base):
    slug = base
    suffix = 2
    while conn.execute(
        'SELECT 1 FROM sequences WHERE slug = ?', (slug,)
    ).fetchone() is not None:
        slug = '%s-%d' % (base, suffix)
        suffix += 1
    return slug


def _utc_now():
    return datetime.now(timezone.utc).isoformat()
