"""Regression tests for the actual GUI driver's acceptance decision."""
import copy
import unittest

from spyder_acceptance_state import evaluate


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.expected = dict(token='run-1', array=[[0, 1]], area=4.0)
        self.snapshot = dict(ready=True, alive=True, same_console=True,
                             pane_visible=True, kernel=self.expected.copy(),
                             source=dict(array_test={}, polygon_area={}),
                             rows=['array_test', 'polygon_area'])

    def check(self, result, elapsed=1):
        self.assertEqual(evaluate(self.snapshot, self.expected, elapsed, 30)[0], result)

    def test_normal(self):
        self.check('PASS')

    def test_delayed_gui(self):
        good = copy.deepcopy(self.snapshot)
        self.snapshot['source'] = {}
        self.snapshot['rows'] = []
        self.check('WAIT')
        self.snapshot = good
        self.check('PASS', 29)

    def test_kernel_alone_never_passes(self):
        self.snapshot['source'] = {}
        self.snapshot['rows'] = []
        self.check('WAIT')
        self.check('FAIL', 30)

    def test_filtered_rows(self):
        self.snapshot['rows'] = ['array_test']
        self.check('WAIT')

    def test_wrong_console(self):
        self.snapshot['same_console'] = False
        self.check('WAIT')

    def test_closed_kernel(self):
        self.snapshot['alive'] = False
        self.check('WAIT')

    def test_recognized_but_not_ready(self):
        self.snapshot['ready'] = False
        self.check('WAIT')

    def test_wrong_values(self):
        self.snapshot['kernel']['area'] = 3
        self.check('WAIT')

    def test_stale_callback_after_restart(self):
        self.snapshot['kernel']['token'] = 'previous-generation'
        self.check('WAIT')

    def test_hidden_pane(self):
        self.snapshot['pane_visible'] = False
        self.check('WAIT')

    def test_deadline_cannot_pass(self):
        self.check('FAIL', 30)


if __name__ == '__main__':
    unittest.main()
