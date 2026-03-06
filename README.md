# worktui

Terminal dashboard for Linear issues and GitHub PRs, with workspace visibility into git worktrees and active AI coding sessions.

## Setup

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

### Environment variables

Set these in `.zshenv` or equivalent:

| Variable | Required | Description |
|---|---|---|
| `LINEAR_API_KEY` | For Linear integration | Linear API key |
| `WORKTUI_GITHUB_ORG` | Yes | GitHub org to scan (default: `courtyard-nft`) |
| `WORKTUI_GITHUB_REPO` | Yes | Default repo for actions (default: `courtyard-nft/courtyard-frontend`) |
| `WORKTUI_GITHUB_USER` | Yes | Your GitHub username (default: `sdvim`) |
| `WORKTUI_POLL_INTERVAL` | No | Seconds between refreshes (default: `45`) |

GitHub CLI (`gh`) must be installed and authenticated.

## Running

```sh
uv run worktui
```

Dev mode with hot reload:

```sh
uv run dev
```

## Keybindings

| Key | Action |
|---|---|
| `j` / `k` | Navigate down / up |
| `g` / `G` | Jump to top / bottom |
| `Enter` | Open primary item in browser |
| `o` | Open PR in browser |
| `i` | Open Linear issue in browser |
| `/` | Focus filter input |
| `Esc` | Clear filter / close panel |
| `x` | Toggle star |
| `v` | Cycle view: All > Starred > Issues > PRs > Devin |
| `s` | Cycle sort: PR Status > Activity > Linear Status > Type |
| `a` | Cycle agent: claude > codex |
| `w` | Toggle workspace panel |
| `R` | Launch AI code review |
| `I` | Launch AI implement |
| `r` | Force refresh |
| `S` | Settings |
| `?` | Help |
| `q` | Quit (closes workspace panel first if open) |

## Workspace panel

Press `w` to show a bottom panel with:

- Org repos and their git worktrees
- Branch names and dirty/clean status
- Active `claude` / `codex` sessions with working/idle status (based on CPU usage)
- Worktree suffixes for linked worktrees (e.g. `repo-aaa` shows as `(aaa)`)

The panel refreshes on each poll cycle.
