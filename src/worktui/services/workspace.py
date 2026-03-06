from __future__ import annotations

import asyncio
import os
from pathlib import Path

from worktui.config import GITHUB_ORG
from worktui.models import AISession, RepoInfo, RepoWorktree


async def _run(cmd: list[str], cwd: str | None = None) -> str:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=cwd,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode(errors="replace")


async def _detect_sessions() -> list[tuple[AISession, str]]:
    """Return (AISession, cwd) pairs for running claude/codex processes."""
    ps_out = await _run(["ps", "-eo", "pid,%cpu,command"])
    candidates: list[tuple[int, float, str]] = []
    for line in ps_out.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid_s, cpu_s, cmd = parts
        # Filter to bare claude/codex commands, not subprocesses
        basename = cmd.split()[0].rsplit("/", 1)[-1]
        if basename not in ("claude", "codex"):
            continue
        # Skip if it looks like a wrapper (e.g. /bin/zsh -c claude ...)
        if "/bin/" in cmd.split()[0]:
            continue
        try:
            candidates.append((int(pid_s), float(cpu_s), basename))
        except ValueError:
            continue

    if not candidates:
        return []

    async def _get_cwd(pid: int, cpu: float, agent: str) -> tuple[AISession, str] | None:
        lsof_out = await _run(["lsof", "-a", "-d", "cwd", "-p", str(pid), "-Fn"])
        for lsof_line in lsof_out.splitlines():
            if lsof_line.startswith("n/"):
                cwd = lsof_line[1:]
                status = "working" if cpu > 1.0 else "idle"
                return AISession(pid=pid, agent=agent, status=status), cwd
        return None

    results = await asyncio.gather(
        *[_get_cwd(pid, cpu, agent) for pid, cpu, agent in candidates]
    )
    return [r for r in results if r is not None]


async def _find_org_repos(git_dir: Path) -> list[tuple[str, str]]:
    """Return (name, path) for repos belonging to GITHUB_ORG."""
    if not git_dir.is_dir():
        return []

    repos: list[tuple[str, str]] = []
    tasks = {}

    for entry in sorted(git_dir.iterdir()):
        git_path = entry / ".git"
        if not entry.is_dir() or not git_path.exists():
            continue
        # .git must be a directory (not a file, which indicates a worktree)
        if not git_path.is_dir():
            continue
        tasks[entry.name] = _run(["git", "remote", "-v"], cwd=str(entry))

    if not tasks:
        return []

    results = await asyncio.gather(*tasks.values())
    for name, output in zip(tasks.keys(), results):
        if GITHUB_ORG in output:
            repos.append((name, str(git_dir / name)))

    return repos


async def _get_worktrees(repo_path: str, repo_name: str) -> list[RepoWorktree]:
    """Parse git worktree list for a repo."""
    output = await _run(["git", "worktree", "list", "--porcelain"], cwd=repo_path)
    worktrees: list[RepoWorktree] = []
    current_path = ""
    current_branch = ""

    for line in output.splitlines():
        if line.startswith("worktree "):
            current_path = line[9:]
            current_branch = ""
        elif line.startswith("branch "):
            current_branch = line[7:].rsplit("/", 1)[-1]
        elif line.startswith("prunable"):
            current_path = ""
            current_branch = ""
        elif line == "" and current_path:
            # Derive suffix from path
            dir_name = Path(current_path).name
            if dir_name == repo_name:
                suffix = ""
            elif dir_name.startswith(repo_name + "-"):
                suffix = dir_name[len(repo_name) + 1:]
            else:
                suffix = dir_name

            worktrees.append(RepoWorktree(
                path=current_path,
                branch=current_branch or "HEAD",
                dirty=False,
                suffix=suffix,
            ))
            current_path = ""
            current_branch = ""

    # Handle last entry if no trailing blank line
    if current_path:
        dir_name = Path(current_path).name
        if dir_name == repo_name:
            suffix = ""
        elif dir_name.startswith(repo_name + "-"):
            suffix = dir_name[len(repo_name) + 1:]
        else:
            suffix = dir_name
        worktrees.append(RepoWorktree(
            path=current_path,
            branch=current_branch or "HEAD",
            dirty=False,
            suffix=suffix,
        ))

    return worktrees


async def _check_dirty(wt: RepoWorktree) -> None:
    """Check if worktree has uncommitted changes."""
    output = await _run(["git", "-C", wt.path, "status", "--porcelain"])
    wt.dirty = bool(output.strip())


async def scan_workspace() -> list[RepoInfo]:
    """Scan ~/Git for org repos, worktrees, dirty status, and AI sessions."""
    git_dir = Path.home() / "Git"

    sessions_task = _detect_sessions()
    repos_task = _find_org_repos(git_dir)
    sessions_with_cwd, repo_tuples = await asyncio.gather(sessions_task, repos_task)

    # Build session lookup by cwd
    session_map: dict[str, AISession] = {}
    for session, cwd in sessions_with_cwd:
        session_map[cwd] = session

    # Get worktrees for all repos in parallel
    wt_results = await asyncio.gather(
        *[_get_worktrees(path, name) for name, path in repo_tuples]
    )

    repos: list[RepoInfo] = []
    all_worktrees: list[RepoWorktree] = []
    for (name, path), worktrees in zip(repo_tuples, wt_results):
        repo = RepoInfo(name=name, path=path, worktrees=worktrees)
        repos.append(repo)
        all_worktrees.extend(worktrees)

    # Check dirty status for all worktrees in parallel
    await asyncio.gather(*[_check_dirty(wt) for wt in all_worktrees])

    # Match sessions to worktrees
    for wt in all_worktrees:
        if wt.path in session_map:
            wt.session = session_map[wt.path]

    # Sort repos by name, worktrees: main first, then by branch
    repos.sort(key=lambda r: r.name)
    for repo in repos:
        repo.worktrees.sort(key=lambda w: (w.suffix != "", w.branch))

    return repos
