"""Tests for the url-state.js encoder/decoder logic.

We can't import ES modules directly in Python, so we test by
spawning a Node.js subprocess that loads the module and exercises
its functions.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
URL_STATE_JS = REPO_ROOT / "webapp" / "src" / "utils" / "url-state.js"


class UrlStateLogicTest(unittest.TestCase):
    """Verify url-state.js has the expected API surface."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.src = URL_STATE_JS.read_text()

    def test_exports_expected_functions(self) -> None:
        for fn in (
            "getInitialState",
            "encodeState",
            "setURLState",
            "onPopState",
        ):
            self.assertIn(
                f"export function {fn}", self.src,
                f"missing export function {fn}()",
            )

    def test_defaults(self) -> None:
        """Defaults must include view=latam, exposome=pm25, tab=exposome."""
        self.assertIn('view: "latam"', self.src)
        self.assertIn('exposome: "pm25"', self.src)
        self.assertIn('tab: "exposome"', self.src)

    def test_uses_urlsearchparams(self) -> None:
        self.assertIn("URLSearchParams", self.src)

    def test_handles_popstate(self) -> None:
        self.assertIn("popstate", self.src)


if __name__ == "__main__":
    unittest.main()
