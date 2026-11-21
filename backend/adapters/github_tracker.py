import httpx
from typing import Dict, Any, Optional
from backend.adapters.tracker_base import TrackerAdapter, UnapprovedItemError
from backend.config import settings

class GitHubTracker(TrackerAdapter):
    """
    GitHub Issues tracker adapter.
    Creates an issue on the configured repository with labels and meeting backlinks.
    Strictly verifies approval_status == 'approved'.
    """
    def __init__(self, token: Optional[str] = None, repo: Optional[str] = None):
        self.token = token or settings.github_token
        self.repo = repo or settings.github_repo

    def create_task(self, item_payload: Dict[str, Any], approval_status: str) -> Dict[str, Any]:
        if approval_status != "approved":
            raise UnapprovedItemError(
                f"Security Gate Block: Cannot post to GitHub Issues when approval_status='{approval_status}'. "
                "Explicit human approval is strictly required."
            )

        title = item_payload.get("title", "Untitled Action Item")
        owner = item_payload.get("owner", "Unassigned")
        deadline = item_payload.get("deadline", "None")
        description = item_payload.get("description", "")
        evidence = item_payload.get("evidence", "")

        body = (
            f"### Action Item from Meeting\n\n"
            f"**Assignee:** @{owner}\n"
            f"**Due Date:** {deadline}\n\n"
            f"**Description:**\n{description}\n\n"
        )
        if evidence:
            body += f"> **Evidence Quote:**\n> {evidence}\n\n"
        body += "\n*Created automatically by ActionLoop with verified human confirmation.*"

        if not self.token or not self.repo:
            # Fallback for dry-run/demo or when credentials are not yet set
            fake_issue_num = 42
            return {
                "external_ref": f"GH-#{fake_issue_num}",
                "title": title,
                "url": f"https://github.com/{self.repo or 'example/repo'}/issues/{fake_issue_num}",
                "sync_status": "synced (simulated)"
            }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json"
        }
        url = f"https://api.github.com/repos/{self.repo}/issues"
        with httpx.Client() as client:
            resp = client.post(url, json={"title": title, "body": body, "labels": ["action-item"]}, headers=headers)
            if resp.status_code >= 400:
                raise RuntimeError(f"GitHub API error ({resp.status_code}): {resp.text}")
            data = resp.json()
            return {
                "external_ref": f"GH-#{data.get('number')}",
                "title": title,
                "url": data.get("html_url"),
                "sync_status": "synced"
            }

    def get_task(self, tracker_ref: str) -> Optional[Dict[str, Any]]:
        return None

    def test_connection(self) -> Dict[str, Any]:
        if not self.token or not self.repo:
            return {
                "status": "unconfigured",
                "provider": "GitHub Issues",
                "message": "GITHUB_TOKEN and GITHUB_REPO are required for live integration."
            }
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}
        try:
            with httpx.Client() as client:
                res = client.get(f"https://api.github.com/repos/{self.repo}", headers=headers, timeout=5.0)
                if res.status_code == 200:
                    return {"status": "connected", "provider": "GitHub Issues", "repo": self.repo}
                return {"status": "error", "provider": "GitHub Issues", "message": f"HTTP {res.status_code}"}
        except Exception as e:
            return {"status": "error", "provider": "GitHub Issues", "message": str(e)}
