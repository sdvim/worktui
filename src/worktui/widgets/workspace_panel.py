from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from worktui.config import load_starred
from worktui.models import RepoInfo, RepoWorktree


class WorkspacePanel(Static):
    """Bottom panel showing workspace repos, worktrees, and AI sessions."""

    def update_workspace(self, repos: list[RepoInfo]) -> None:
        starred = load_starred()
        content = Text()

        for i, repo in enumerate(repos):
            if i > 0:
                content.append("\n")
            content.append(f"{repo.name}/\n", style="bold")

            for wt in repo.worktrees:
                self._render_worktree(content, wt, starred)

        self.update(content)

    def _render_worktree(self, content: Text, wt: RepoWorktree, starred: set[str]) -> None:
        # Star prefix
        is_starred = wt.branch in starred
        prefix = "  \u2605 " if is_starred else "    "
        content.append(prefix)

        # Branch name
        content.append(f"{wt.branch:<24}")

        # Dirty status
        if wt.dirty:
            content.append("\u25cf dirty    ", style="yellow")
        else:
            content.append("\u2714 clean    ", style="dim")

        # Worktree suffix
        if wt.suffix:
            content.append(f"({wt.suffix})  ", style="dim")

        # AI session
        if wt.session:
            style = "green" if wt.session.status == "working" else "dim"
            content.append(f"{wt.session.agent} [{wt.session.status}]", style=style)

        content.append("\n")
