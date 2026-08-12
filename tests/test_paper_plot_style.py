from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import matplotlib.pyplot as plt

from exposome.paper_plot_style import (
    COLORS,
    apply_astro_paper_style,
    save_paper_figure,
    style_rank_axis,
)


class PaperPlotStyleTest(unittest.TestCase):
    def test_paper_profile_and_paired_export(self) -> None:
        apply_astro_paper_style("paper", use_seaborn=False)
        self.assertEqual(plt.rcParams["font.family"], ["serif"])
        self.assertEqual(plt.rcParams["xtick.direction"], "in")
        self.assertTrue(plt.rcParams["xtick.top"])
        self.assertGreaterEqual(plt.rcParams["axes.linewidth"], 2.0)

        fig, ax = plt.subplots(figsize=(4, 3))
        ax.barh(["A", "B"], [2, 1], color=COLORS["data"])
        style_rank_axis(ax)
        with tempfile.TemporaryDirectory() as tmp:
            outputs = save_paper_figure(fig, Path(tmp) / "ranking")
            self.assertEqual({path.suffix for path in outputs}, {".pdf", ".png"})
            self.assertTrue(all(path.is_file() and path.stat().st_size > 0 for path in outputs))
        plt.close(fig)

    def test_unknown_profile_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            apply_astro_paper_style("unknown")


if __name__ == "__main__":
    unittest.main()
