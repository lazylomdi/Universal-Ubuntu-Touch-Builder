"""Optional, read-only GitHub source discovery. Results are candidates, never compatibility proof."""
from __future__ import annotations
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

def discover_github_candidates(query: str, timeout: float = 8.0, opener=None) -> dict:
    """Search GitHub repositories without cloning or executing returned code."""
    query = query.strip()
    if not query:
        return {"status": "UNKNOWN", "query": query, "candidates": [], "error": "empty query"}
    url = "https://api.github.com/search/repositories?q=" + quote(query) + "&per_page=10"
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "AndroidBuilder-UT-readiness/1.0",
    })
    open_url = opener or urlopen
    try:
        with open_url(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        candidates = []
        for item in payload.get("items", []):
            candidates.append({
                "full_name": item.get("full_name"),
                "url": item.get("html_url"),
                "default_branch": item.get("default_branch"),
                "updated_at": item.get("updated_at"),
                "description": item.get("description"),
                "evidence_status": "CANDIDATE",
                "warning": "Repository metadata is not proof of device match, buildability, or hardware support.",
            })
        return {"status": "CANDIDATE" if candidates else "UNKNOWN",
                "query": query, "candidates": candidates, "error": None}
    except HTTPError as exc:
        status = "RATE_LIMITED" if exc.code == 403 or exc.code == 429 else "UNAVAILABLE"
        return {"status": status, "query": query, "candidates": [],
                "error": f"GitHub API returned HTTP {exc.code}"}
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "UNAVAILABLE", "query": query, "candidates": [],
                "error": f"Source discovery failed: {type(exc).__name__}"}
