from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from worktui.models import GitHubPR, LinearIssue, WorkItem
from worktui.services.linker import link_items

CACHE_PATH = Path.home() / ".cache" / "worktui" / "data.json"


def save_cache(issues: list[LinearIssue], prs: list[GitHubPR]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "issues": [
            {
                "id": i.id,
                "title": i.title,
                "status": i.status,
                "url": i.url,
                "priority": i.priority,
                "source": i.source,
                "labels": i.labels,
                "updated_at": i.updated_at.isoformat() if i.updated_at else None,
                "attachment_urls": i.attachment_urls,
            }
            for i in issues
        ],
        "prs": [
            {
                "number": p.number,
                "title": p.title,
                "status": p.status,
                "url": p.url,
                "author": p.author,
                "head_branch": p.head_branch,
                "is_draft": p.is_draft,
                "review_decision": p.review_decision,
                "has_reviews": p.has_reviews,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "is_devin": p.is_devin,
                "body": p.body,
                "ci_pass": p.ci_pass,
                "ci_fail": p.ci_fail,
                "ci_pending": p.ci_pending,
                "devin_reviewing": p.devin_reviewing,
            }
            for p in prs
        ],
    }
    CACHE_PATH.write_text(json.dumps(data))


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    return datetime.fromisoformat(val)


def load_cache() -> tuple[list[WorkItem], datetime | None] | None:
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    cached_at = _parse_dt(data.get("cached_at"))

    issues = [
        LinearIssue(
            id=i["id"],
            title=i["title"],
            status=i["status"],
            url=i["url"],
            priority=i["priority"],
            source=i.get("source", "linear"),
            labels=i.get("labels", []),
            updated_at=_parse_dt(i.get("updated_at")),
            attachment_urls=i.get("attachment_urls", []),
        )
        for i in data.get("issues", [])
    ]

    prs = [
        GitHubPR(
            number=p["number"],
            title=p["title"],
            status=p["status"],
            url=p["url"],
            author=p["author"],
            head_branch=p["head_branch"],
            is_draft=p["is_draft"],
            review_decision=p["review_decision"],
            has_reviews=p["has_reviews"],
            updated_at=_parse_dt(p.get("updated_at")),
            is_devin=p.get("is_devin", False),
            body=p.get("body", ""),
            ci_pass=p.get("ci_pass", 0),
            ci_fail=p.get("ci_fail", 0),
            ci_pending=p.get("ci_pending", 0),
            devin_reviewing=p.get("devin_reviewing", False),
        )
        for p in data.get("prs", [])
    ]

    work_items = link_items(issues, prs)
    return work_items, cached_at
