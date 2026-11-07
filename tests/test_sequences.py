# coding: utf-8
import os
import tempfile
import unittest

import sequences


class MatchExactTests(unittest.TestCase):

    def test_contiguous_block_matches(self):
        self.assertTrue(sequences.match_exact(
            ['C', 'Gm', 'F', 'Bb'], ['Gm', 'F']))

    def test_extra_chords_before_and_after_match(self):
        self.assertTrue(sequences.match_exact(
            ['C', 'D', 'Gm', 'F', 'Bb', 'A'], ['Gm', 'F']))

    def test_reversed_order_does_not_match(self):
        self.assertFalse(sequences.match_exact(['F', 'Gm'], ['Gm', 'F']))

    def test_chord_in_the_middle_does_not_match(self):
        self.assertFalse(sequences.match_exact(
            ['Gm', 'C', 'F'], ['Gm', 'F']))

    def test_different_repetition_does_not_match(self):
        self.assertFalse(sequences.match_exact(
            ['Gm', 'F'], ['Gm', 'Gm', 'F']))

    def test_case_sensitive(self):
        self.assertFalse(sequences.match_exact(['B', 'G'], ['Bm', 'G']))
        self.assertTrue(sequences.match_exact(['B', 'G'], ['B', 'G']))

    def test_sequence_longer_than_cifra_does_not_match(self):
        self.assertFalse(sequences.match_exact(['C'], ['C', 'G']))

    def test_empty_sequence_does_not_match(self):
        self.assertFalse(sequences.match_exact(['C', 'G'], []))


class ParseChordsCsvTests(unittest.TestCase):

    def test_simple_list(self):
        self.assertEqual(
            sequences.parse_chords_csv('Gm,F'), ['Gm', 'F'])

    def test_ignores_spaces_and_empty_tokens(self):
        self.assertEqual(
            sequences.parse_chords_csv(' Gm , F ,, '), ['Gm', 'F'])

    def test_empty_input_raises(self):
        with self.assertRaises(sequences.SequenceValidationError):
            sequences.parse_chords_csv('')

    def test_only_separators_raises(self):
        with self.assertRaises(sequences.SequenceValidationError):
            sequences.parse_chords_csv(' , , ')

    def test_non_string_raises(self):
        with self.assertRaises(sequences.SequenceValidationError):
            sequences.parse_chords_csv(['Gm', 'F'])


class DatabaseTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, 'sequences.db')
        self.conn = sequences.init_db(self.path)
        sequences.seed_legacy(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_seed_is_idempotent(self):
        self.assertEqual(len(sequences.list_sequences(self.conn)), 6)
        self.assertEqual(sequences.seed_legacy(self.conn), 6)
        self.assertEqual(len(sequences.list_sequences(self.conn)), 6)

    def test_legacy_catalog(self):
        catalog = sequences.list_sequences(self.conn)
        self.assertEqual([row['legacy_id'] for row in catalog],
                         [0, 1, 2, 3, 4, 5])
        self.assertTrue(all(row['match_mode'] == 'legacy' for row in catalog))
        self.assertEqual(catalog[4]['chords'], ['Gm', 'F'])

    def test_create_valid_custom(self):
        sequencia, criada = sequences.create_sequence(
            self.conn, 'Minha Sequência', ['C', 'G', 'Am'])
        self.assertTrue(criada)
        self.assertEqual(sequencia['name'], 'Minha Sequência')
        self.assertEqual(sequencia['chords'], ['C', 'G', 'Am'])
        self.assertEqual(sequencia['match_mode'], 'exact')
        self.assertIsNone(sequencia['legacy_id'])
        self.assertEqual(sequencia['slug'], 'minha-sequencia')
        self.assertEqual(len(sequences.list_sequences(self.conn)), 7)

    def test_duplicate_chords_returns_existing(self):
        first, criada = sequences.create_sequence(
            self.conn, 'Primeira', ['C', 'G'])
        second, criada_de_novo = sequences.create_sequence(
            self.conn, 'Outro nome', ['C', 'G'])
        self.assertTrue(criada)
        self.assertFalse(criada_de_novo)
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(sequences.list_sequences(self.conn)), 7)

    def test_duplicate_legacy_chords_returns_legacy(self):
        sequencia, criada = sequences.create_sequence(
            self.conn, 'Gm F duplicada', ['Gm', 'F'])
        self.assertFalse(criada)
        self.assertEqual(sequencia['legacy_id'], 4)
        self.assertEqual(sequencia['match_mode'], 'legacy')
        self.assertEqual(len(sequences.list_sequences(self.conn)), 6)

    def test_slug_collision_gets_numeric_suffix(self):
        first, _ = sequences.create_sequence(
            self.conn, 'Minha Sequência', ['C', 'G'])
        second, _ = sequences.create_sequence(
            self.conn, 'Minha Sequencia', ['D', 'A'])
        self.assertEqual(first['slug'], 'minha-sequencia')
        self.assertEqual(second['slug'], 'minha-sequencia-2')

    def test_resolve_legacy_by_slug(self):
        sequencia = sequences.resolve_sequence(self.conn, 'gm-f')
        self.assertEqual(sequencia['legacy_id'], 4)

    def test_resolve_legacy_by_chords_csv(self):
        sequencia = sequences.resolve_sequence(self.conn, 'Gm,F')
        self.assertEqual(sequencia['legacy_id'], 4)

    def test_resolve_custom_by_slug_and_chords(self):
        created, _ = sequences.create_sequence(
            self.conn, 'Custom', ['C', 'G'])
        by_slug = sequences.resolve_sequence(self.conn, created['slug'])
        by_chords = sequences.resolve_sequence(self.conn, 'C, G')
        self.assertEqual(by_slug['id'], created['id'])
        self.assertEqual(by_chords['id'], created['id'])

    def test_resolve_unknown_returns_none(self):
        self.assertIsNone(sequences.resolve_sequence(self.conn, 'nao-existe'))
        self.assertIsNone(sequences.resolve_sequence(self.conn, 'X,Y'))
        self.assertIsNone(sequences.resolve_sequence(self.conn, ''))

    def test_name_validation(self):
        for name in (None, '', '   ', 'a' * 81):
            with self.assertRaises(sequences.SequenceValidationError):
                sequences.create_sequence(self.conn, name, ['C'])

    def test_chords_validation(self):
        invalid = [
            [],
            'C,G',
            17 * ['C'],
            ['c'],
            ['X'],
            ['Gm F'],
            ['G,m'],
            ['C' * 18],
            [123],
            [''],
        ]
        for chords in invalid:
            with self.assertRaises(sequences.SequenceValidationError):
                sequences.create_sequence(self.conn, 'Válida', chords)

    def test_chord_is_stripped(self):
        sequencia, _ = sequences.create_sequence(
            self.conn, 'Com espaços', [' Gm ', ' F '])
        self.assertEqual(sequencia['chords'], ['Gm', 'F'])


if __name__ == '__main__':
    unittest.main()
