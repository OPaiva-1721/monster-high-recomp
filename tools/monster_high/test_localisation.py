import unittest
from localisation import digest, extract, patch

class LocalisationTests(unittest.TestCase):
    def setUp(self):
        self.data = b'HEADER\0Hello, <name>!\0TAIL'
        self.manifest = dict(source_sha256=digest(self.data), replacements=[
            dict(offset=7, source='Hello, <name>!', translation='Olá, <name>!')])

    def test_utf8_patch_preserves_layout_and_other_bytes(self):
        changed = patch(self.data, self.manifest)
        self.assertEqual(len(changed), len(self.data))
        self.assertEqual(changed[:7], self.data[:7])
        self.assertEqual(changed[21:], self.data[21:])
        self.assertEqual(changed[7:21].decode(), 'Olá, <name>! ')

    def test_refuses_mismatches_overflow_tokens_and_duplicates(self):
        for field, value in [('source', 'Wrong'), ('translation', 'Muito comprida <name>!'),
                             ('translation', 'Olá, <other>!'), ('offset', -1)]:
            item = dict(self.manifest['replacements'][0]); item[field] = value
            with self.assertRaises(ValueError):
                patch(self.data, dict(source_sha256=digest(self.data), replacements=[item]))
        with self.assertRaises(ValueError):
            patch(self.data, dict(source_sha256='bad', replacements=[]))
        self.manifest['replacements'] *= 2
        with self.assertRaises(ValueError): patch(self.data, self.manifest)

    def test_extraction_reports_byte_offsets(self):
        data = b'\xff\0' + 'Olá, você!'.encode() + b'\0'
        rows = extract(data)['strings']
        self.assertEqual(rows, [dict(offset=2, byte_length=12, text='Olá, você!')])

    def test_controller_entities_are_preserved(self):
        data=b'\0Press &icoffin; now\0'
        manifest=dict(source_sha256=digest(data),replacements=[
            dict(offset=1,source='Press &icoffin; now',translation='Use &wrong;')])
        with self.assertRaises(ValueError):patch(data,manifest)
        manifest['replacements'][0]['translation']='Use &icoffin;'
        self.assertIn(b'Use &icoffin;',patch(data,manifest))

if __name__ == '__main__': unittest.main()
