from __future__ import annotations

from datetime import datetime, timezone

from rich.text import Text
from textual.widgets import DataTable

from worktui.config import GITHUB_USER, load_starred
from worktui.models import GitHubPR, WorkItem

PR_STATUS_STYLES: dict[str, tuple[str, str]] = {
    "Needs Review": ("bold white on red", ""),
    "Changes Requested": ("bold yellow", ""),
    "In Review": ("cyan", ""),
    "Draft": ("dim", ""),
    "Approved": ("green", ""),
    "Merged": ("magenta", ""),
    "Closed": ("dim red", ""),
}

LINEAR_STATUS_STYLES: dict[str, tuple[str, str]] = {
    "Urgent": ("bold white on red", ""),
    "In Progress": ("bold cyan", ""),
    "In Review": ("cyan", ""),
    "Todo": ("yellow", ""),
    "Backlog": ("dim", ""),
    "Triage": ("dim yellow", ""),
}


def _alias_name(name: str) -> str:
    if "devin-ai" in name.lower():
        return "devin"
    return name


def _actionable_owner(item: WorkItem) -> str:
    pr = item.primary_pr
    if not pr or pr.status in ("Merged", "Closed"):
        return ""
    is_mine = pr.author.lower() == GITHUB_USER.lower()
    if is_mine:
        # Your PR: you act on changes requested, draft, approved
        if pr.status in ("Changes Requested", "Draft", "Approved"):
            return "you"
        return ""  # Waiting on reviewers
    # Their PR: you act when it needs review, otherwise they do
    if pr.status == "Needs Review":
        return "you"
    return _alias_name(pr.author)


def _styled(value: str, styles: dict[str, tuple[str, str]]) -> Text:
    if not value:
        return Text("")
    style_info = styles.get(value)
    if style_info:
        return Text(value, style=style_info[0])
    return Text(value)


def _ci_text(pr: GitHubPR) -> str:
    """Plain-text CI indicator for width calculation."""
    if pr.devin_reviewing:
        return " Devin: Reviewing..."
    total = pr.ci_pass + pr.ci_fail + pr.ci_pending
    if total == 0:
        return ""
    parts = []
    if pr.ci_pass:
        parts.append(f"\u2714{pr.ci_pass}")
    if pr.ci_fail:
        parts.append(f"\u2716{pr.ci_fail}")
    if pr.ci_pending:
        parts.append(f"?{pr.ci_pending}")
    return " " + "/".join(parts)


def _append_ci_icons(text: Text, pr: GitHubPR) -> None:
    """Append styled CI indicators to a Rich Text object."""
    if pr.devin_reviewing:
        text.append(" Devin: Reviewing...", style="italic magenta")
        return
    total = pr.ci_pass + pr.ci_fail + pr.ci_pending
    if total == 0:
        return
    text.append(" ")
    parts = []
    if pr.ci_pass:
        parts.append((f"\u2714{pr.ci_pass}", "green"))
    if pr.ci_fail:
        parts.append((f"\u2716{pr.ci_fail}", "bold red"))
    if pr.ci_pending:
        parts.append((f"?{pr.ci_pending}", "yellow"))
    for i, (s, style) in enumerate(parts):
        if i > 0:
            text.append("/", style="dim")
        text.append(s, style=style)


def _activity_text(item: WorkItem) -> str:
    dt = item.updated_at
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    delta = now - dt
    minutes = int(delta.total_seconds() / 60)
    if minutes < 1:
        return "now"
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    return f"{days}d"


def _styled_activity(item: WorkItem) -> Text:
    label = _activity_text(item)
    if not label:
        return Text("")
    dt = item.updated_at
    if dt:
        days = (datetime.now(timezone.utc) - dt).days
        if days > 30:
            return Text(label, style="bold red")
        if days > 7:
            return Text(label, style="yellow")
    return Text(label, style="dim")


class ItemTable(DataTable):
    """Main table showing all work items."""

    _work_items: list[WorkItem]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._work_items = []
        self.cursor_type = "row"
        self.zebra_stripes = True

    # DataTable adds 1 char padding on each side of every cell (2 per column),
    # plus 1 char per column divider (n_cols - 1 dividers + potential border).
    _CELL_PADDING = 2  # per column
    _N_COLS = 5
    _TABLE_OVERHEAD = _CELL_PADDING * _N_COLS + _N_COLS  # padding + dividers/border

    def _col_widths(self, items: list[WorkItem]) -> dict[str, int]:
        """Compute column widths: fixed cols fit content, Title gets the rest."""
        starred = load_starred()
        id_w = max((len(i.display_id) + (2 if i.star_id in starred else 0) for i in items), default=4)
        owner_w = max((len(_actionable_owner(i)) for i in items), default=5)
        status_w = max((len(self._status_text(i)) for i in items), default=6)
        activity_w = max((len(_activity_text(i)) for i in items), default=3)
        total = self.size.width or self.app.size.width
        title_w = max(total - id_w - owner_w - status_w - activity_w - self._TABLE_OVERHEAD, 20)
        return {"id": id_w, "owner": owner_w, "status": status_w, "activity": activity_w, "title": title_w}

    @staticmethod
    def _status_text(item: WorkItem) -> str:
        """Plain-text length of the status column for width calculation."""
        devin_pr = next((p for p in item.prs if p.devin_reviewing), None)
        if devin_pr:
            return f"Devin: Reviewing... #{devin_pr.number}"
        s = item.unified_status or ""
        if item.primary_pr:
            s += f" #{item.primary_pr.number}"
            s += _ci_text(item.primary_pr)
        return s

    def on_mount(self) -> None:
        self._id_col = self.add_column("ID", key="ID", width=8)
        self._title_col = self.add_column("Title", key="Title", width=40)
        self._owner_col = self.add_column("Owner", key="Owner", width=8)
        self._status_col = self.add_column("Status", key="Status", width=20)
        self._activity_col = self.add_column("Activity", key="Activity", width=5)
        self._resize_timer = None

    def on_resize(self) -> None:
        if self._resize_timer is not None:
            self._resize_timer.stop()
        self._resize_timer = self.set_timer(0.3, self._apply_resize)

    def _apply_resize(self) -> None:
        self._resize_timer = None
        if self._work_items:
            self.update_items(self._work_items)

    def _sync_col_widths(self, items: list[WorkItem]) -> None:
        widths = self._col_widths(items)
        for key, attr in [("id", "_id_col"), ("title", "_title_col"),
                          ("owner", "_owner_col"), ("status", "_status_col"),
                          ("activity", "_activity_col")]:
            col = self.columns.get(getattr(self, attr))
            if col:
                col.width = widths[key]

    def update_items(self, items: list[WorkItem]) -> None:
        cursor_row = self.cursor_row
        self.clear()
        self._work_items = items
        starred = load_starred()

        widths = self._col_widths(items) if items else None
        self._sync_col_widths(items)
        title_max = (widths["title"] - 1) if widths else 40
        for item in items:
            title = item.display_title
            if len(title) > title_max:
                title = title[: title_max - 3] + "..."
            devin_pr = next((p for p in item.prs if p.devin_reviewing), None)
            if devin_pr:
                status = Text(f"Devin: Reviewing... ", style="italic magenta")
                status.append(f"#{devin_pr.number}", style="dim")
            else:
                status_styles = PR_STATUS_STYLES if item.prs else LINEAR_STATUS_STYLES
                status = _styled(item.unified_status, status_styles)
                if item.primary_pr:
                    pr = item.primary_pr
                    status.append(f" #{pr.number}", style="dim")
                    _append_ci_icons(status, pr)
            id_cell = Text("")
            if item.star_id in starred:
                id_cell.append("\u2605 ", style="yellow")
            id_cell.append(item.display_id)
            self.add_row(
                id_cell,
                title,
                _actionable_owner(item),
                status,
                _styled_activity(item),
            )

        if self._work_items and cursor_row >= 0:
            target = min(cursor_row, len(self._work_items) - 1)
            self.move_cursor(row=target)

    def get_selected_item(self) -> WorkItem | None:
        if not self._work_items:
            return None
        idx = self.cursor_row
        if 0 <= idx < len(self._work_items):
            return self._work_items[idx]
        return None
