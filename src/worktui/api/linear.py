from __future__ import annotations

from datetime import datetime, timezone

import httpx

from worktui.config import LINEAR_API_KEY
from worktui.models import LinearIssue

ENDPOINT = "https://api.linear.app/graphql"

QUERY = """
query AssignedIssues {
  viewer {
    assignedIssues(
      filter: {
        state: { type: { nin: ["canceled", "completed"] } }
      }
      orderBy: updatedAt
      first: 50
    ) {
      nodes {
        identifier
        title
        state { name }
        url
        updatedAt
        priority
        labels { nodes { name } }
        attachments { nodes { url } }
      }
    }
  }
}
"""


async def fetch_linear_issues() -> list[LinearIssue]:
    if not LINEAR_API_KEY:
        return []

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            ENDPOINT,
            json={"query": QUERY},
            headers={
                "Authorization": LINEAR_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()

    data = resp.json()
    nodes = data.get("data", {}).get("viewer", {}).get("assignedIssues", {}).get("nodes", [])

    issues = []
    for n in nodes:
        updated = None
        if n.get("updatedAt"):
            updated = datetime.fromisoformat(n["updatedAt"].replace("Z", "+00:00"))

        issues.append(LinearIssue(
            id=n["identifier"],
            title=n["title"],
            status=n["state"]["name"],
            url=n["url"],
            priority=n.get("priority", 0),
            labels=[l["name"] for l in n.get("labels", {}).get("nodes", [])],
            updated_at=updated,
            attachment_urls=[a["url"] for a in n.get("attachments", {}).get("nodes", [])],
        ))
    return issues
