from __future__ import annotations

import re

from worktui.models import GitHubPR, LinearIssue, WorkItem

ISSUE_PATTERN = re.compile(r"ENG-\d+", re.IGNORECASE)
LINEAR_URL_PATTERN = re.compile(r"linear\.app/[^/]+/issue/(ENG-\d+)", re.IGNORECASE)
GH_ISSUE_URL_PATTERN = re.compile(r"github\.com/[^/]+/[^/]+/issues/(\d+)")


def _extract_issue_ids_from_text(text: str, issue_map: dict[str, object]) -> set[str]:
    ids = set()
    for m in ISSUE_PATTERN.finditer(text):
        ids.add(m.group(0).upper())
    for m in LINEAR_URL_PATTERN.finditer(text):
        ids.add(m.group(1).upper())
    for m in GH_ISSUE_URL_PATTERN.finditer(text):
        gh_id = f"GH-{m.group(1)}"
        if gh_id in issue_map:
            ids.add(gh_id)
    return ids


def link_items(issues: list[LinearIssue], prs: list[GitHubPR]) -> list[WorkItem]:
    issue_map = {i.id: i for i in issues}
    pr_map = {p.number: p for p in prs}

    # Build adjacency: issue_id <-> pr_number
    edges: dict[str, set[int]] = {i.id: set() for i in issues}
    pr_edges: dict[int, set[str]] = {p.number: set() for p in prs}

    for issue in issues:
        # Linear attachment URLs linking to PRs
        for url in issue.attachment_urls:
            if "github.com" in url and "/pull/" in url:
                try:
                    pr_num = int(url.rstrip("/").split("/pull/")[-1].split("/")[0].split("#")[0])
                    if pr_num in pr_map:
                        edges[issue.id].add(pr_num)
                        pr_edges[pr_num].add(issue.id)
                except (ValueError, IndexError):
                    pass
        # GitHub issues: link via PR body "closes #N" / "fixes #N" / bare "#N"
        if issue.source == "github":
            gh_num = issue.id.removeprefix("GH-")
            for pr in prs:
                if pr.body and f"#{gh_num}" in pr.body:
                    edges[issue.id].add(pr.number)
                    pr_edges[pr.number].add(issue.id)

    for pr in prs:
        # PR title
        for issue_id in _extract_issue_ids_from_text(pr.title, issue_map):
            if issue_id in issue_map:
                edges[issue_id].add(pr.number)
                pr_edges[pr.number].add(issue_id)

        # Branch name
        for issue_id in _extract_issue_ids_from_text(pr.head_branch, issue_map):
            if issue_id in issue_map:
                edges[issue_id].add(pr.number)
                pr_edges[pr.number].add(issue_id)

        # PR body
        if pr.body:
            for issue_id in _extract_issue_ids_from_text(pr.body, issue_map):
                if issue_id in issue_map:
                    edges[issue_id].add(pr.number)
                    pr_edges[pr.number].add(issue_id)

    # Build connected components via BFS
    visited_issues: set[str] = set()
    visited_prs: set[int] = set()
    work_items: list[WorkItem] = []

    for issue_id in issue_map:
        if issue_id in visited_issues:
            continue
        component_issues: list[str] = []
        component_prs: list[int] = []
        queue_issues = [issue_id]
        queue_prs: list[int] = []

        while queue_issues or queue_prs:
            while queue_issues:
                iid = queue_issues.pop()
                if iid in visited_issues:
                    continue
                visited_issues.add(iid)
                component_issues.append(iid)
                for pn in edges.get(iid, set()):
                    if pn not in visited_prs:
                        queue_prs.append(pn)

            while queue_prs:
                pn = queue_prs.pop()
                if pn in visited_prs:
                    continue
                visited_prs.add(pn)
                component_prs.append(pn)
                for iid in pr_edges.get(pn, set()):
                    if iid not in visited_issues:
                        queue_issues.append(iid)

        work_items.append(WorkItem(
            issues=[issue_map[i] for i in component_issues],
            prs=[pr_map[p] for p in component_prs],
        ))

    # Orphan PRs
    for pr in prs:
        if pr.number not in visited_prs:
            work_items.append(WorkItem(prs=[pr]))

    return work_items
