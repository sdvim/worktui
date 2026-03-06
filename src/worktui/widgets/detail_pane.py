from __future__ import annotations

from datetime import datetime, timezone

from textual.widgets import Static

from worktui.models import WorkItem


def _time_ago(dt: datetime | None) -> str:
    if not dt:
        return "unknown"
    now = datetime.now(timezone.utc)
    delta = now - dt
    minutes = int(delta.total_seconds() / 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


class DetailPane(Static):
    """Shows details for the selected work item."""

    def update_item(self, item: WorkItem | None) -> None:
        if not item:
            self.update("No item selected")
            return

        lines = []

        # Title line
        title = item.display_title
        lines.append(f"[bold]{item.display_id}[/]: {title}")

        # Status line
        parts = []
        if item.primary_issue:
            source_label = "GitHub" if item.primary_issue.source == "github" else "Linear"
            parts.append(f"{source_label}: {item.linear_status}")
        if item.prs:
            pr_strs = [f"#{p.number} ({p.status})" for p in item.prs]
            parts.append(f"PRs: {', '.join(pr_strs)}")
        if parts:
            lines.append(" | ".join(parts))

        # Labels + updated
        meta = []
        if item.primary_issue and item.primary_issue.labels:
            meta.append(f"Labels: {', '.join(item.primary_issue.labels)}")
        meta.append(f"Updated: {_time_ago(item.updated_at)}")
        lines.append(" | ".join(meta))

        self.update("\n".join(lines))
