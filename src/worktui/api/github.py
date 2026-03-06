from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from worktui.config import GITHUB_ORG, GITHUB_USER
from worktui.models import GitHubPR, LinearIssue, infer_pr_status

PR_JSON_FIELDS = "number,title,headRefName,state,reviewDecision,isDraft,reviews,updatedAt,url,author,body,statusCheckRollup"
SEARCH_FIELDS = "number,repository,state,updatedAt"


async def _run_gh(args: list[str]):
    proc = await asyncio.create_subprocess_exec(
        "gh", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"gh failed: {stderr.decode()}")
    text = stdout.decode().strip()
    if not text:
        return []
    return json.loads(text)


async def _search_prs(*extra_flags: str) -> list[dict]:
    return await _run_gh([
        "search", "prs",
        "--owner", GITHUB_ORG,
        *extra_flags,
        "--limit", "50",
        "--json", SEARCH_FIELDS,
    ])


async def _fetch_pr_detail(repo: str, number: int) -> dict | None:
    try:
        result = await _run_gh([
            "pr", "view", str(number), "-R", repo, "--json", PR_JSON_FIELDS,
        ])
        return result if isinstance(result, dict) else None
    except Exception:
        return None


def _parse_pr(item: dict) -> GitHubPR:
    updated = None
    if item.get("updatedAt"):
        updated = datetime.fromisoformat(item["updatedAt"].replace("Z", "+00:00"))

    is_draft = item.get("isDraft", False)
    review_decision = item.get("reviewDecision") or ""
    reviews = item.get("reviews") or []
    has_reviews = len(reviews) > 0
    author_login = item.get("author", {}).get("login", "")

    status = infer_pr_status(
        item.get("state", "OPEN"), is_draft, review_decision, has_reviews,
    )

    checks = item.get("statusCheckRollup") or []
    ci_pass = ci_fail = ci_pending = 0
    devin_reviewing = False
    for c in checks:
        name = c.get("name") or c.get("context") or ""
        conclusion = c.get("conclusion", "")
        state = c.get("state", "")
        if name == "Devin Review" and state == "PENDING":
            devin_reviewing = True
            ci_pending += 1
            continue
        if conclusion == "FAILURE":
            ci_fail += 1
        elif conclusion in ("SUCCESS", "NEUTRAL"):
            ci_pass += 1
        else:
            ci_pending += 1

    return GitHubPR(
        number=item["number"],
        title=item["title"],
        status=status,
        url=item["url"],
        author=author_login,
        head_branch=item.get("headRefName", ""),
        is_draft=is_draft,
        review_decision=review_decision,
        has_reviews=has_reviews,
        updated_at=updated,
        is_devin=author_login.lower() in ("devin-ai[bot]", "devin-ai-integration[bot]"),
        body=item.get("body", ""),
        ci_pass=ci_pass,
        ci_fail=ci_fail,
        ci_pending=ci_pending,
        devin_reviewing=devin_reviewing,
    )


async def fetch_github_prs() -> list[GitHubPR]:
    # Search across org for PRs involving this user
    # gh search doesn't support --state=all, so query open + recently closed separately
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    closed_since = cutoff.strftime("%Y-%m-%d")

    author_open, author_closed, assignee_open, review_data = await asyncio.gather(
        _search_prs("--author", GITHUB_USER, "--state=open"),
        _search_prs("--author", GITHUB_USER, "--state=closed", "--closed", f">={closed_since}"),
        _search_prs("--assignee", GITHUB_USER, "--state=open"),
        _search_prs("--review-requested", GITHUB_USER, "--state=open"),
    )

    seen: dict[str, dict] = {}
    for item in author_open + author_closed + assignee_open + review_data:
        repo = item.get("repository", {}).get("nameWithOwner", "")
        num = item["number"]
        key = f"{repo}#{num}"
        if key in seen:
            continue

        seen[key] = {"repo": repo, "number": num}

    # Fetch full details for each PR
    detail_tasks = [
        _fetch_pr_detail(info["repo"], info["number"])
        for info in seen.values()
    ]
    all_details = await asyncio.gather(*detail_tasks)

    return [_parse_pr(item) for item in all_details if item is not None]


ISSUE_SEARCH_FIELDS = "number,title,state,labels,updatedAt,url,repository"

GH_ISSUE_STATUS_MAP = {
    "OPEN": "Todo",
    "CLOSED": "Done",
}


async def fetch_github_issues() -> list[LinearIssue]:
    assigned_data, author_data = await asyncio.gather(
        _run_gh([
            "search", "issues",
            "--owner", GITHUB_ORG,
            "--assignee", GITHUB_USER,
            "--state=open",
            "--limit", "50",
            "--json", ISSUE_SEARCH_FIELDS,
        ]),
        _run_gh([
            "search", "issues",
            "--owner", GITHUB_ORG,
            "--author", GITHUB_USER,
            "--state=open",
            "--limit", "50",
            "--json", ISSUE_SEARCH_FIELDS,
        ]),
    )

    seen: dict[str, dict] = {}
    for item in assigned_data + author_data:
        repo = item.get("repository", {}).get("nameWithOwner", "")
        key = f"{repo}#{item['number']}"
        if key not in seen:
            seen[key] = item

    issues = []
    for item in seen.values():
        updated = None
        if item.get("updatedAt"):
            updated = datetime.fromisoformat(item["updatedAt"].replace("Z", "+00:00"))

        labels_raw = item.get("labels") or []
        labels = [l.get("name", "") for l in labels_raw if l.get("name")]

        issues.append(LinearIssue(
            id=f"GH-{item['number']}",
            title=item["title"],
            status=GH_ISSUE_STATUS_MAP.get(item.get("state", "OPEN"), "Todo"),
            url=item["url"],
            priority=0,
            source="github",
            labels=labels,
            updated_at=updated,
        ))

    return issues
