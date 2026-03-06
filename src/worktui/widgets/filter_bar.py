from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Input, Static


VIEW_MODES = ["All", "Starred", "Issues", "PRs", "Devin"]


class FilterBar(Horizontal):
    """Filter input and view mode tabs."""

    _current_mode: int = 0

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Filter...", id="filter-input")
        yield Static(self._mode_label(), id="view-mode")

    def _mode_label(self) -> str:
        parts = []
        for i, mode in enumerate(VIEW_MODES):
            if i == self._current_mode:
                parts.append(f"[bold reverse] {mode} [/]")
            else:
                parts.append(f" {mode} ")
        return "[v] " + "|".join(parts)

    def cycle_mode(self) -> str:
        self._current_mode = (self._current_mode + 1) % len(VIEW_MODES)
        self.query_one("#view-mode", Static).update(self._mode_label())
        return VIEW_MODES[self._current_mode]

    @property
    def current_mode(self) -> str:
        return VIEW_MODES[self._current_mode]

    @property
    def filter_text(self) -> str:
        return self.query_one("#filter-input", Input).value
