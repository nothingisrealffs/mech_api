import unittest

from mech_bv import get_multiplier_for, compute_adjusted_bv


class BVMultiplierTests(unittest.TestCase):
    def test_multiplier_bounds(self):
        # ensure some values round-trip and bounds are enforced
        self.assertAlmostEqual(get_multiplier_for(4, 5), 1.00, places=3)
        self.assertAlmostEqual(get_multiplier_for(5, 4), 0.99, places=3)

    def test_compute_adjusted_bv_basic(self):
        base_bv = 2340
        # convert from base (5,4) to (4,5) - should be slightly larger than stored
        res = compute_adjusted_bv(base_bv, base_g=5, base_p=4, target_g=4, target_p=5)
        self.assertIn('multiplier', res)
        self.assertIn('adjusted_bv', res)
        # compute manually: target_mult/base_mult
        expected_multiplier = get_multiplier_for(4, 5) / get_multiplier_for(5, 4)
        self.assertAlmostEqual(res['multiplier'], expected_multiplier, places=6)
        self.assertEqual(res['adjusted_bv'], int(round(base_bv * expected_multiplier)))


if __name__ == '__main__':
    unittest.main()
