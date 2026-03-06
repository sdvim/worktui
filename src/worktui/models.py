from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LinearIssue:
    id: str  # ENG-XXXX or GH-123
    title: str
    status: str
    url: str
    priority: int
    source: str = "linear"  # "linear" or "github"
    labels: list[str] = field(default_factory=list)
    updated_at: datetime | None = None
    attachment_urls: list[str] = field(default_factory=list)


@dataclass
class GitHubPR:
    number: int
    title: str
    status: str  # inferred status
    url: str
    author: str
    head_branch: str
    is_draft: bool
    review_decision: str
    has_reviews: bool
    updated_at: datetime | None = None
    is_devin: bool = False
    body: str = ""
    ci_pass: int = 0
    ci_fail: int = 0
    ci_pending: int = 0
    devin_reviewing: bool = False

    @property
    def display_id(self) -> str:
        return f"#{self.number}"

    @property
    def repo_name(self) -> str:
        """Extract repo name from URL, e.g. 'courtyard-frontend'."""
        # url like https://github.com/org/repo/pull/123
        parts = self.url.split("/")
        try:
            idx = parts.index("pull")
            return parts[idx - 1]
        except (ValueError, IndexError):
            return ""


def infer_pr_status(state: str, is_draft: bool, review_decision: str, has_reviews: bool) -> str:
    if state == "MERGED":
        return "Merged"
    if state == "CLOSED":
        return "Closed"
    if is_draft:
        return "Draft"
    if review_decision == "APPROVED":
        return "Approved"
    if review_decision == "CHANGES_REQUESTED":
        return "Changes Requested"
    if has_reviews:
        return "In Review"
    return "Needs Review"


@dataclass
class AISession:
    pid: int
    agent: str  # "claude" or "codex"
    status: str  # "working" or "idle"


@dataclass
class RepoWorktree:
    path: str
    branch: str
    dirty: bool
    suffix: str  # e.g. "aaa" from courtyard-frontend-aaa, "" for main
    session: AISession | None = None


@dataclass
class RepoInfo:
    name: str
    path: str
    worktrees: list[RepoWorktree] = field(default_factory=list)


@dataclass
class WorkItem:
    issues: list[LinearIssue] = field(default_factory=list)
    prs: list[GitHubPR] = field(default_factory=list)

    @property
    def primary_issue(self) -> LinearIssue | None:
        return self.issues[0] if self.issues else None

    @property
    def primary_pr(self) -> GitHubPR | None:
        if not self.prs:
            return None
        # Prefer an open PR over merged/closed
        for p in self.prs:
            if p.status not in ("Merged", "Closed"):
                return p
        return self.prs[0]

    @property
    def display_type(self) -> str:
        has_issue = bool(self.issues)
        has_pr = bool(self.prs)
        if has_issue and has_pr:
            return "Issue+PR"
        if has_issue:
            return "Issue"
        pr = self.primary_pr
        if pr and pr.is_devin:
            return "PR(Dvn)"
        return "PR"

    @property
    def display_id(self) -> str:
        if self.primary_issue:
            return self.primary_issue.id
        if self.primary_pr:
            return "NO-TASK"
        return ""

    @property
    def star_id(self) -> str:
        """Unique ID for starring. Uses issue ID or PR number."""
        if self.primary_issue:
            return self.primary_issue.id
        if self.primary_pr:
            return f"PR-{self.primary_pr.number}"
        return ""

    @property
    def display_title(self) -> str:
        if self.primary_issue:
            return self.primary_issue.title
        if self.primary_pr:
            return self.primary_pr.title
        return ""

    @property
    def linear_status(self) -> str:
        if self.primary_issue:
            return self.primary_issue.status
        return ""

    @property
    def pr_status(self) -> str:
        if self.primary_pr:
            return self.primary_pr.status
        return ""

    @property
    def updated_at(self) -> datetime | None:
        dates = []
        for i in self.issues:
            if i.updated_at:
                dates.append(i.updated_at)
        for p in self.prs:
            if p.updated_at:
                dates.append(p.updated_at)
        return max(dates) if dates else None

    @property
    def primary_url(self) -> str:
        if self.primary_pr:
            return self.primary_pr.url
        if self.primary_issue:
            return self.primary_issue.url
        return ""

    @property
    def issue_url(self) -> str | None:
        return self.primary_issue.url if self.primary_issue else None

    @property
    def unified_status(self) -> str:
        if self.prs:
            return self.pr_status
        return self.linear_status

    @property
    def pr_url(self) -> str | None:
        return self.primary_pr.url if self.primary_pr else None
