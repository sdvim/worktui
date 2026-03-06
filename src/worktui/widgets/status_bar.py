from __future__ import annotations

from datetime import datetime

from textual.widgets import Static


class StatusBar(Static):
    """Bottom status bar with last poll time, counts, and key hints."""

    def update_status(
        self,
        item_count: int,
        last_poll: datetime | None = None,
        error: str | None = None,
        seconds_until_poll: int | None = None,
        agent: str | None = None,
    ) -> None:
        parts = []

        if last_poll:
            local_time = last_poll.astimezone()
            parts.append(f"Updated: {local_time.strftime('%I:%M %p')}")
        else:
            parts.append("Loading...")

        parts.append(f"{item_count} items")

        if seconds_until_poll is not None:
            parts.append(f"Next: {seconds_until_poll}s")

        if agent:
            parts.append(f"Agent: [bold]{agent}[/]")

        if error:
            parts.append(f"[bold red]ERR: {error}[/]")

        parts.append("q:quit  ?:help  r:refresh")

        self.update(" | ".join(parts))
