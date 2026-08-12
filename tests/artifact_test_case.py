"""Opt-in base class for tests that validate materialized research artifacts.

Unit tests must run in a clone containing only source, configuration and small
reference inputs.  Checks of a particular Santiago release are still valuable,
but require an explicit artifact materialization and opt-in flag.
"""
from __future__ import annotations

import os
import unittest


class MaterializedArtifactTestCase(unittest.TestCase):
    """Skip release/figure assertions unless explicitly requested."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        original = cls.__dict__.get("setUpClass")

        @classmethod
        def gated(inner: type[unittest.TestCase]) -> None:
            if os.environ.get("EXPOSOME_RUN_ARTIFACT_TESTS") != "1":
                raise unittest.SkipTest(
                    "requires EXPOSOME_RUN_ARTIFACT_TESTS=1 and a materialized release"
                )
            if original is not None:
                original.__get__(None, inner)()

        cls.setUpClass = gated  # type: ignore[method-assign]
