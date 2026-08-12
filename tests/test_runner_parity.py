from __future__ import annotations

import unittest

from exposome.runner_parity import load_runner_parity


class RunnerParityGateTests(unittest.TestCase):
    def test_every_catalog_layer_is_registered_but_none_is_retired_early(self) -> None:
        records = load_runner_parity()
        self.assertTrue(all(record.registered for record in records))
        self.assertTrue(all(record.state == "adapter" for record in records))
        self.assertFalse(any(record.retirement_ready for record in records))


if __name__ == "__main__":
    unittest.main()
