# coding: utf-8
import json
import os
import tempfile
import unittest

# Precisa ser definido antes de importar main.py, que inicializa o banco no import.
_TMP = tempfile.mkdtemp(prefix='deciframe-api-')
os.environ['SEQUENCES_DB'] = os.path.join(_TMP, 'sequences.db')

import main
import sequences


LEGACY_CHORDS = {
    '0': 'Bm,G,D,A',
    '1': 'C,G,Am,F',
    '2': 'Em,G',
    '3': 'C,A7,Dm,G7',
    '4': 'Gm,F',
    '5': 'C,C7,F,Fm',
}
BASELINE_PATH = os.path.join(os.path.dirname(__file__), 'baseline_legacy.json')
KNOWN_MPB_SONG = (
    'ze-ramalho_mulher-nova-bonita-carinhosa-faz-homem-gemer-sem-sentir-dor')


class ApiTestCase(unittest.TestCase):

    def setUp(self):
        self.client = main.app.test_client()
        conn = sequences.connect(os.environ['SEQUENCES_DB'])
        conn.execute('DELETE FROM sequences WHERE legacy_id IS NULL')
        conn.commit()
        conn.close()

    def _get_json(self, path, **query):
        response = self.client.get(path, query_string=query)
        self.assertEqual(response.status_code, 200)
        return json.loads(response.data.decode('utf-8'))

    def _post_json(self, payload):
        return self.client.post('/sequencias', json=payload)

    def _collect_pages(self, ident):
        ids = []
        page = 1
        while True:
            data = self._get_json(
                '/similares', sequencia=ident, pagina=page)
            if not data:
                break
            ids.extend(item['id_unico_musica'] for item in data)
            if len(data) < main.TAM_PAGINA:
                break
            page += 1
        return ids

    def test_get_sequencias_lists_legacy_seeds(self):
        response = self.client.get('/sequencias')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers['Content-Type'].startswith('text/html'))
        data = json.loads(response.data.decode('utf-8'))
        legacy = [item for item in data if item['legacy_id'] is not None]
        self.assertEqual(
            [item['legacy_id'] for item in legacy], [0, 1, 2, 3, 4, 5])
        self.assertTrue(
            all(item['match_mode'] == 'legacy' for item in legacy))
        self.assertEqual(legacy[4]['chords'], ['Gm', 'F'])

    def test_post_valid_creates_and_appears(self):
        response = self._post_json(
            {'name': 'Cadastro API', 'chords': ['C', 'G']})
        self.assertEqual(response.status_code, 201)
        created = json.loads(response.data.decode('utf-8'))
        self.assertEqual(created['name'], 'Cadastro API')
        self.assertEqual(created['chords'], ['C', 'G'])
        self.assertEqual(created['match_mode'], 'exact')
        self.assertIsNone(created['legacy_id'])
        self.assertEqual(created['slug'], 'cadastro-api')

        catalog = self._get_json('/sequencias')
        self.assertIn(created['id'], [item['id'] for item in catalog])

    def test_post_accepts_chords_as_csv_string(self):
        response = self._post_json(
            {'name': 'String CSV', 'chords': 'C, G'})
        self.assertEqual(response.status_code, 201)
        created = json.loads(response.data.decode('utf-8'))
        self.assertEqual(created['chords'], ['C', 'G'])

    def test_post_duplicate_returns_existing(self):
        first = self._post_json(
            {'name': 'Primeira', 'chords': ['C', 'G']})
        second = self._post_json(
            {'name': 'Segunda', 'chords': ['C', 'G']})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        first_body = json.loads(first.data.decode('utf-8'))
        second_body = json.loads(second.data.decode('utf-8'))
        self.assertEqual(first_body['id'], second_body['id'])
        self.assertEqual(len(self._get_json('/sequencias')), 7)

    def test_post_duplicate_legacy_returns_legacy(self):
        response = self._post_json(
            {'name': 'Gm F de novo', 'chords': ['Gm', 'F']})
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.data.decode('utf-8'))
        self.assertEqual(body['legacy_id'], 4)
        self.assertEqual(body['match_mode'], 'legacy')
        self.assertEqual(len(self._get_json('/sequencias')), 6)

    def test_post_invalid_returns_400_with_json_dumps(self):
        payloads = [
            {'name': '', 'chords': ['C']},
            {'name': 'x', 'chords': []},
            {'name': 'x', 'chords': ['c']},
            {'name': 'x', 'chords': ['Gm F']},
            {'name': 'x', 'chords': ['G,m']},
            {'name': 'a' * 81, 'chords': ['C']},
            {'name': 'x', 'chords': 17 * ['C']},
        ]
        for payload in payloads:
            response = self._post_json(payload)
            self.assertEqual(response.status_code, 400, payload)
            self.assertTrue(
                response.headers['Content-Type'].startswith('text/html'))
            body = json.loads(response.data.decode('utf-8'))
            self.assertIn('error', body)
            self.assertTrue(body['error'])

    def test_post_invalid_body_returns_400(self):
        response = self.client.post(
            '/sequencias', data='not json', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', json.loads(response.data.decode('utf-8')))

    def test_similares_unknown_returns_empty(self):
        self.assertEqual(
            self._get_json('/similares', sequencia='nao-existe'), [])

    def test_similares_legacy_by_comma_matches_baseline(self):
        with open(BASELINE_PATH, encoding='utf-8') as baseline_file:
            baseline = json.load(baseline_file)

        for legacy_id, chords in LEGACY_CHORDS.items():
            self.assertEqual(
                self._collect_pages(chords),
                baseline[legacy_id],
                'regressão na sequência legada %s' % legacy_id,
            )

    def test_similares_legacy_by_slug_matches_baseline(self):
        with open(BASELINE_PATH, encoding='utf-8') as baseline_file:
            baseline = json.load(baseline_file)
        self.assertEqual(
            self._collect_pages('gm-f'), baseline['4'])

    def test_similares_legacy_has_no_diferenca(self):
        data = self._get_json('/similares', sequencia='Gm,F')
        self.assertTrue(data)
        for item in data:
            self.assertNotIn('diferenca', item)

    def test_similares_custom_uses_exact_matcher(self):
        chords = ['E', 'F#', 'E', 'F#']
        response = self._post_json(
            {'name': 'Bloco exato', 'chords': chords})
        self.assertEqual(response.status_code, 201)
        created = json.loads(response.data.decode('utf-8'))

        expected = sequences.exact_matches(
            main.apply_filtro(main.musicas.values(), main.generos), chords)
        expected_ids = [item['id_unico_musica'] for item in expected]
        self.assertIn(KNOWN_MPB_SONG, expected_ids)

        first_page = self._get_json(
            '/similares', sequencia=created['slug'], pagina=1)
        self.assertEqual(
            [item['id_unico_musica'] for item in first_page],
            expected_ids[:main.TAM_PAGINA])
        for item in first_page:
            self.assertNotIn('diferenca', item)
            musica = main.musicas[item['id_unico_musica']]
            self.assertTrue(sequences.match_exact(musica.cifra, chords))

        second_page = self._get_json(
            '/similares', sequencia=created['slug'], pagina=2)
        self.assertEqual(
            [item['id_unico_musica'] for item in second_page],
            expected_ids[main.TAM_PAGINA:2 * main.TAM_PAGINA])

    def test_similares_custom_respects_generos(self):
        chords = ['E', 'F#', 'E', 'F#']
        response = self._post_json(
            {'name': 'Bloco com gênero', 'chords': chords})
        self.assertEqual(response.status_code, 201)
        created = json.loads(response.data.decode('utf-8'))

        mpb_expected = sequences.exact_matches(
            main.apply_filtro(main.musicas.values(), ['MPB']), chords)
        mpb_ids = [item['id_unico_musica'] for item in mpb_expected]
        self.assertIn(KNOWN_MPB_SONG, mpb_ids)

        mpb_page = self._get_json(
            '/similares', sequencia=created['slug'],
            generos='MPB', pagina=1)
        self.assertEqual(
            [item['id_unico_musica'] for item in mpb_page],
            mpb_ids[:main.TAM_PAGINA])
        self.assertIn(
            KNOWN_MPB_SONG,
            [item['id_unico_musica'] for item in mpb_page])
        self.assertTrue(all(item['genero'] == 'MPB' for item in mpb_page))

        rock_page = self._get_json(
            '/similares', sequencia=created['slug'],
            generos='Rock', pagina=1)
        self.assertNotIn(
            KNOWN_MPB_SONG,
            [item['id_unico_musica'] for item in rock_page])
        self.assertTrue(all(item['genero'] == 'Rock' for item in rock_page))


if __name__ == '__main__':
    unittest.main()
