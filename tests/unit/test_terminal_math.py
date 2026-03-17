"""Tests for terminal-only LaTeX rendering."""

from __future__ import annotations

from anki_pipeline.terminal_math import render_latex_for_terminal


class TestRenderLatexForTerminal:
    def test_renders_anki_inline_math(self):
        text = r"The sum \(\alpha + \beta\) is important."
        assert render_latex_for_terminal(text) == "The sum α+ β is important."

    def test_renders_raw_dollar_math_after_normalization(self):
        text = "The derivative of $x^2$ is $2x$."
        assert render_latex_for_terminal(text) == "The derivative of x^2 is 2x."

    def test_renders_display_math_without_delimiters(self):
        text = r"Use \[\frac{1}{2}\] here."
        assert render_latex_for_terminal(text) == "Use 1/2 here."

    def test_leaves_non_math_text_unchanged(self):
        text = "No formulas here."
        assert render_latex_for_terminal(text) == text
