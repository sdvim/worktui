from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Input, Static

from worktui.config import GITHUB_REPO, LINEAR_API_KEY, POLL_INTERVAL, load_settings, load_starred, save_settings, toggle_starred
from worktui.models import WorkItem
from worktui.services.cache import load_cache
from worktui.services.poller import poll_once
from worktui.widgets.detail_pane import DetailPane
from worktui.widgets.filter_bar import FilterBar
from worktui.widgets.item_table import ItemTable
from worktui.widgets.status_bar import StatusBar

SORT_MODES = ["PR Status", "Activity", "Linear Status", "Type"]
AGENTS = ["claude", "codex"]

# Lower number = more urgent, sorted first
PR_STATUS_URGENCY = {
    "Needs Review": 0,
    "Changes Requested": 1,
    "In Review": 2,
    "Draft": 3,
    "Approved": 4,
    "Merged": 5,
    "Closed": 6,
    "": 7,
}

LINEAR_STATUS_URGENCY = {
    "Urgent": 0,
    "In Progress": 1,
    "In Review": 2,
    "Todo": 3,
    "Backlog": 4,
    "Triage": 5,
    "": 6,
}

HELP_TEXT = """\
[bold]worktui - Keyboard Shortcuts[/]

  j/k      Navigate down/up
  g/G      Jump to top/bottom
  Enter    Open primary item in browser
  o        Open PR in browser
  i        Open Linear issue in browser
  /        Focus filter input
  Esc      Clear filter, return to table
  x        Toggle star on selected item
  v        Cycle view: All > Starred > Issues > PRs > Devin
  s        Cycle sort: PR Status > Activity > Linear Status > Type
  a        Cycle agent: claude > codex
  R        Launch AI code review (Needs Review PRs)
  I        Launch AI implement (Linear tickets)
  r        Force refresh
  S        Settings
  ?        Toggle this help
  q        Quit
"""


class HelpScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("question_mark", "dismiss", "Close help", priority=True),
        Binding("escape", "dismiss", "Close help", priority=True),
        Binding("q", "dismiss", "Close help", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="help-overlay"):
            yield Static(HELP_TEXT)


class SettingsScreen(ModalScreen[bool]):
    """Settings modal with integration toggles."""

    BINDINGS = [
        Binding("escape", "dismiss_settings", "Close"),
        Binding("q", "dismiss_settings", "Close"),
        Binding("S", "dismiss_settings", "Close", key_display="shift+s"),
    ]

    def compose(self) -> ComposeResult:
        settings = load_settings()
        with Container(id="settings-overlay"):
            yield Static("[bold]Settings[/]\n")
            with Vertical(id="settings-checks"):
                yield Checkbox("Linear Issues", settings.get("enable_linear", True), id="cb-linear")
                yield Checkbox("GitHub Issues", settings.get("enable_github_issues", False), id="cb-gh-issues")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        settings = load_settings()
        if event.checkbox.id == "cb-linear":
            settings["enable_linear"] = event.value
        elif event.checkbox.id == "cb-gh-issues":
            settings["enable_github_issues"] = event.value
        save_settings(settings)

    def action_dismiss_settings(self) -> None:
        self.dismiss(True)


class WorkTuiApp(App[None]):
    CSS_PATH = "styles/app.tcss"

    BINDINGS = [
        Binding("q", "maybe_quit", "Quit", priority=True),
        Binding("question_mark", "maybe_help", "Help", priority=True),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False, key_display="shift+g"),
        Binding("o", "open_pr", "Open PR", show=False),
        Binding("i", "open_issue", "Open Issue", show=False),
        Binding("slash", "focus_filter", "Filter", show=False),
        Binding("escape", "clear_filter", "Clear", show=False),
        Binding("v", "cycle_view", "Cycle View", show=False),
        Binding("s", "cycle_sort", "Cycle Sort", show=False),
        Binding("a", "cycle_agent", "Cycle Agent", show=False),
        Binding("R", "launch_review", "Launch Review", show=False, key_display="shift+r"),
        Binding("I", "launch_implement", "Implement", show=False, key_display="shift+i"),
        Binding("x", "toggle_star", "Star", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("S", "settings", "Settings", show=False, key_display="shift+s"),
    ]

    _all_items: list[WorkItem]
    _displayed_items: list[WorkItem]
    _last_poll: datetime | None
    _last_error: str | None
    _sort_mode: int
    _poll_countdown: int
    _agent_mode: int

    def __init__(self) -> None:
        super().__init__()
        self._all_items = []
        self._displayed_items = []
        self._last_poll = None
        self._last_error = None
        self._sort_mode = 0
        self._poll_countdown = 0
        self._agent_mode = 0

    def compose(self) -> ComposeResult:
        yield FilterBar()
        yield ItemTable(id="item-table")
        yield DetailPane(id="detail-pane")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        settings = load_settings()
        if settings.get("enable_linear") and not LINEAR_API_KEY:
            self.notify("LINEAR_API_KEY not set - Linear issues won't load", severity="warning")
        cached = load_cache()
        if cached:
            items, cached_at = cached
            self._all_items = items
            self._last_poll = cached_at
            self._apply_filters()
            self._update_status_bar()
        self._do_refresh()
        self._start_poll_timer()
        self.query_one(ItemTable).focus()

    def _start_poll_timer(self) -> None:
        self._poll_countdown = POLL_INTERVAL
        self.set_interval(1, self._tick)

    def _tick(self) -> None:
        self._poll_countdown -= 1
        if self._poll_countdown <= 0:
            self._do_refresh()
            self._poll_countdown = POLL_INTERVAL
        self._update_status_bar()

    @work(exclusive=True)
    async def _do_refresh(self) -> None:
        items, error = await poll_once()
        self._all_items = items
        self._last_poll = datetime.now(timezone.utc)
        self._last_error = error
        self._poll_countdown = POLL_INTERVAL
        self._apply_filters()
        self._update_status_bar()

    def _apply_filters(self) -> None:
        filter_bar = self.query_one(FilterBar)
        mode = filter_bar.current_mode
        text = filter_bar.filter_text.lower()

        HIDDEN_PR = {"Merged", "Closed"}
        HIDDEN_LINEAR = {"Backlog", "Canceled", "Triage"}
        items = [
            i for i in self._all_items
            if not (i.prs and all(p.status in HIDDEN_PR for p in i.prs))
            and not (i.issues and not i.prs and i.linear_status in HIDDEN_LINEAR)
        ]

        if mode == "Starred":
            starred = load_starred()
            items = [i for i in self._all_items if i.star_id in starred]
        elif mode == "Issues":
            items = [i for i in items if i.issues]
        elif mode == "PRs":
            items = [i for i in items if i.prs and not any(p.is_devin for p in i.prs)]
        elif mode == "Devin":
            items = [i for i in items if any(p.is_devin for p in i.prs)]

        if text:
            items = [
                i for i in items
                if text in i.display_title.lower()
                or text in i.display_id.lower()
                or text in i.unified_status.lower()
            ]

        items = self._sort_items(items)
        self._displayed_items = items
        self.query_one(ItemTable).update_items(items)

    def _sort_items(self, items: list[WorkItem]) -> list[WorkItem]:
        mode = SORT_MODES[self._sort_mode]
        if mode == "PR Status":
            return sorted(items, key=lambda i: (
                PR_STATUS_URGENCY.get(i.pr_status, 7),
                LINEAR_STATUS_URGENCY.get(i.linear_status, 6),
            ))
        elif mode == "Activity":
            return sorted(items, key=lambda i: i.updated_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        elif mode == "Linear Status":
            return sorted(items, key=lambda i: (
                LINEAR_STATUS_URGENCY.get(i.linear_status, 6),
                PR_STATUS_URGENCY.get(i.pr_status, 7),
            ))
        else:  # Type
            order = {"Issue+PR": 0, "Issue": 1, "PR": 2, "PR(Dvn)": 3}
            return sorted(items, key=lambda i: order.get(i.display_type, 9))

    def _update_status_bar(self) -> None:
        self.query_one(StatusBar).update_status(
            item_count=len(self._displayed_items),
            last_poll=self._last_poll,
            error=self._last_error,
            seconds_until_poll=self._poll_countdown,
            agent=AGENTS[self._agent_mode],
        )

    def _update_detail(self) -> None:
        table = self.query_one(ItemTable)
        item = table.get_selected_item()
        self.query_one(DetailPane).update_item(item)

    def on_resize(self) -> None:
        try:
            table = self.query_one(ItemTable)
            table.on_resize()
        except Exception:
            pass

    def on_data_table_cursor_moved(self, _event) -> None:
        self._update_detail()

    def on_data_table_row_selected(self, _event) -> None:
        self.action_open_primary()

    def on_input_changed(self, _event: Input.Changed) -> None:
        self._apply_filters()

    # --- Actions ---

    def action_cursor_down(self) -> None:
        table = self.query_one(ItemTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self.query_one(ItemTable)
        table.action_cursor_up()

    def action_cursor_top(self) -> None:
        table = self.query_one(ItemTable)
        table.move_cursor(row=0)

    def action_cursor_bottom(self) -> None:
        table = self.query_one(ItemTable)
        if table._work_items:
            table.move_cursor(row=len(table._work_items) - 1)

    def action_open_primary(self) -> None:
        item = self.query_one(ItemTable).get_selected_item()
        if item and item.primary_url:
            self._open_url(item.primary_url)

    def action_toggle_star(self) -> None:
        item = self.query_one(ItemTable).get_selected_item()
        if not item:
            return
        is_starred = toggle_starred(item.star_id)
        label = "\u2605" if is_starred else "unstarred"
        self.notify(f"{label} {item.display_id}", timeout=1)
        self._apply_filters()

    def action_open_pr(self) -> None:
        item = self.query_one(ItemTable).get_selected_item()
        if item and item.pr_url:
            self._open_url(item.pr_url)

    def action_open_issue(self) -> None:
        item = self.query_one(ItemTable).get_selected_item()
        if item and item.issue_url:
            self._open_url(item.issue_url)

    def action_focus_filter(self) -> None:
        self.query_one("#filter-input", Input).focus()

    def action_clear_filter(self) -> None:
        if self._has_modal():
            self.screen.dismiss()
            return
        inp = self.query_one("#filter-input", Input)
        inp.value = ""
        self.query_one(ItemTable).focus()
        self._apply_filters()

    def action_cycle_view(self) -> None:
        self.query_one(FilterBar).cycle_mode()
        self._apply_filters()

    def action_cycle_sort(self) -> None:
        self._sort_mode = (self._sort_mode + 1) % len(SORT_MODES)
        self.notify(f"Sort: {SORT_MODES[self._sort_mode]}", timeout=2)
        self._apply_filters()

    def action_refresh(self) -> None:
        self.notify("Refreshing...", timeout=2)
        self._do_refresh()

    def action_cycle_agent(self) -> None:
        self._agent_mode = (self._agent_mode + 1) % len(AGENTS)
        self.notify(f"Agent: {AGENTS[self._agent_mode]}", timeout=2)
        self._update_status_bar()

    def action_launch_review(self) -> None:
        item = self.query_one(ItemTable).get_selected_item()
        if not item or not item.primary_pr:
            self.notify("No PR on this item", severity="warning", timeout=2)
            return
        pr = item.primary_pr
        if pr.status != "Needs Review":
            self.notify("PR is not in Needs Review status", severity="warning", timeout=2)
            return
        agent = AGENTS[self._agent_mode]
        pr_url = pr.url
        prompt = (
            f"Do a thorough code review of this PR: {pr_url} . "
            "Check for bugs, logic errors, security issues, and style. "
            "Leave your review as GitHub PR comments."
        )
        repo_name = pr.repo_name or GITHUB_REPO.split("/")[-1]
        repo_path = Path.home() / "Git" / repo_name
        if agent == "claude":
            args = ["claude", "--dangerously-skip-permissions", prompt]
        else:
            args = ["codex", "--full-auto", prompt]
        self._open_terminal(args, cwd=repo_path)
        self.notify(f"Launched {agent} review for #{pr.number}", timeout=3)

    def action_launch_implement(self) -> None:
        item = self.query_one(ItemTable).get_selected_item()
        if not item or not item.primary_issue:
            self.notify("No issue on this item", severity="warning", timeout=2)
            return
        issue = item.primary_issue
        issue_url = issue.url
        source = "GitHub issue" if issue.source == "github" else "Linear ticket"
        prompt = (
            f"Implement this {source}: {issue_url} . "
            f"Title: {issue.title}. "
            "Read the ticket details, plan the implementation, then execute."
        )
        repo_name = item.primary_pr.repo_name if item.primary_pr else GITHUB_REPO.split("/")[-1]
        repo_path = Path.home() / "Git" / repo_name
        agent = AGENTS[self._agent_mode]
        if agent == "claude":
            args = ["claude", "--permission-mode", "plan", prompt]
        else:
            args = ["codex", "--full-auto", prompt]
        self._open_terminal(args, cwd=repo_path)
        self.notify(f"Launched {agent} implement for {issue.id}", timeout=3)

    def action_settings(self) -> None:
        def _on_dismiss(changed: bool) -> None:
            if changed:
                self._do_refresh()

        self.push_screen(SettingsScreen(), callback=_on_dismiss)

    def _has_modal(self) -> bool:
        return len(self.screen_stack) > 1

    def action_maybe_quit(self) -> None:
        if self._has_modal():
            self.screen.dismiss()
        else:
            self.exit()

    def action_maybe_help(self) -> None:
        if self._has_modal():
            self.screen.dismiss()
        else:
            self.push_screen(HelpScreen())

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def _open_terminal(self, args: list[str], cwd: Path) -> None:
        ghostty = "/Applications/Ghostty.app/Contents/MacOS/ghostty"
        subprocess.Popen(
            [ghostty, f"--working-directory={cwd}", "-e"] + args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _open_url(self, url: str) -> None:
        subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    app = WorkTuiApp()
    app.run()


if __name__ == "__main__":
    main()
