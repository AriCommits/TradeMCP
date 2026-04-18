import unittest
from greeks_viz.services.greeks_calculator import compute_all_greeks, build_surface

class GreeksCalculatorTestCase(unittest.TestCase):
    def test_compute_all_greeks(self):
        chain = "mock_chain_data"
        results = compute_all_greeks(chain)
        self.assertEqual(len(results), 10)
        
        # Check first combo
        self.assertEqual(results[0]['greeks'], ('delta', 'gamma', 'theta'))
        self.assertIn('surface', results[0])

    def test_build_surface_empty(self):
        surface = build_surface("mock_chain", ('delta', 'gamma', 'theta'))
        self.assertEqual(surface['x'], [])
        self.assertEqual(surface['y'], [])
        self.assertEqual(surface['z'], [])
        
    def test_build_surface_no_chain(self):
        surface = build_surface(None, ('delta', 'gamma', 'theta'))
        self.assertNotEqual(len(surface['x']), 0)
        self.assertNotEqual(len(surface['y']), 0)
        self.assertNotEqual(len(surface['z']), 0)
