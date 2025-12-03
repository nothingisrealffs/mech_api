import unittest
from unittest.mock import patch, MagicMock

from mtf_ingest import fetch_bv_pv_from_pull


class FetchBvPvTests(unittest.TestCase):
    def test_parses_bv_pv_with_commas(self):
        sample_out = '[{"Name": "Atlas II AS7-D-H2", "": "", "Tons": "100", "BV": "2,340", "PV": "55", "Role": "Juggernaut"}]'
        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = sample_out

        with patch('subprocess.run', return_value=fake):
            bv, pv = fetch_bv_pv_from_pull('Atlas', 'AS7-D-H2')
            self.assertEqual(bv, 2340)
            self.assertEqual(pv, 55)

    def test_handles_missing_json(self):
        fake = MagicMock()
        fake.returncode = 1
        fake.stdout = ''
        with patch('subprocess.run', return_value=fake):
            bv, pv = fetch_bv_pv_from_pull('Atlas', 'AS7-D-H2')
            self.assertIsNone(bv)
            self.assertIsNone(pv)


if __name__ == '__main__':
    unittest.main()
