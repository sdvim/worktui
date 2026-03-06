from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from worktui.api.github import fetch_github_issues, fetch_github_prs
from worktui.api.linear import fetch_linear_issues
from worktui.config import load_settings
from worktui.models import LinearIssue, WorkItem
from worktui.services.cache import save_cache
from worktui.services.linker import link_items


async def poll_once() -> tuple[list[WorkItem], str | None]:
    """Fetch all data and return (work_items, error_message)."""
    settings = load_settings()
    error = None
    issues: list[LinearIssue] = []
    prs = []

    tasks = {}
    if settings.get("enable_linear"):
        tasks["linear"] = fetch_linear_issues()
    if settings.get("enable_github_issues"):
        tasks["gh_issues"] = fetch_github_issues()
    tasks["gh_prs"] = fetch_github_prs()

    try:
        results = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True,
        )
        result_map = dict(zip(tasks.keys(), results))

        for key, result in result_map.items():
            if isinstance(result, BaseException):
                err_msg = f"{key}: {result}"
                error = err_msg if not error else f"{error} | {err_msg}"
            elif key == "gh_prs":
                prs = result
            else:
                issues.extend(result)

    except Exception as e:
        error = str(e)

    if issues or prs:
        try:
            save_cache(issues, prs)
        except Exception:
            pass

    work_items = link_items(issues, prs)
    return work_items, error
