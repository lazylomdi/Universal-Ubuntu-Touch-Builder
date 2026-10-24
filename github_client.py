"""
github_client.py — authenticated, disk-cached GitHub API client.

This is the fix for the persistent rate-limit problem. Unauthenticated
GitHub API requests are limited to 60/hr per IP. With a personal access
token (PAT) that rises to 5,000/hr — plenty for any reasonable ROM build
session. The cache means repeated searches for the same codename don't
burn API quota at all.

Token storage:
  1. GITHUB_TOKEN environment variable (best for CI / power users)
  2. ~/.config/romforge/github_token (prompted once, stored for future runs)
  3. No token — unauthenticated, 60/hr, rate-limit warnings shown

Cache:
  ~/.cache/romforge/api/<sha256_of_url>.json
  TTL: 1 hour for search results (enough to avoid redundant re-searches
  within a build session), 24 hours for release info (Magisk, etc.)
  Cache is per-user, not per-project — shared across workdirs.
"""

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


_CONFIG_DIR = Path.home() / ".config" / "romforge"
_CACHE_DIR  = Path.home() / ".cache"  / "romforge" / "api"
_TOKEN_FILE = _CONFIG_DIR / "github_token"
_SEARCH_TTL = 3600       # 1 hour
_RELEASE_TTL = 86400     # 24 hours

_token: str | None = None  # module-level cache of the resolved token


def _resolve_token() -> str | None:
    global _token
    if _token is not None:
        return _token or None   # empty string → no token
    # 1. Environment variable
    env = os.environ.get("GITHUB_TOKEN", "").strip()
    if env:
        _token = env
        return _token
    # 2. Stored token file
    if _TOKEN_FILE.exists():
        stored = _TOKEN_FILE.read_text().strip()
        if stored:
            _token = stored
            return _token
    _token = ""   # sentinel: we tried, no token
    return None


def set_token(token: str) -> None:
    """Store a GitHub PAT for future runs. Called from the TUI setup flow."""
    global _token
    token = token.strip()
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_text(token)
    _TOKEN_FILE.chmod(0o600)
    _token = token


def token_status() -> str:
    """Human-readable one-liner for display in the TUI."""
    tok = _resolve_token()
    if not tok:
        return "No token — rate limited to 60 req/hr (GITHUB_TOKEN or Settings → GitHub token)"
    masked = tok[:4] + "****" + tok[-4:] if len(tok) > 8 else "****"
    return f"Token set ({masked}) — 5,000 req/hr"


def _cache_key(url: str) -> Path:
    digest = hashlib.sha256(url.encode()).hexdigest()
    return _CACHE_DIR / f"{digest}.json"


def _from_cache(url: str, ttl: int) -> dict | None:
    path = _cache_key(url)
    if not path.exists():
        return None
    try:
        age = time.time() - path.stat().st_mtime
        if age > ttl:
            return None
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _to_cache(url: str, data: dict) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_key(url).write_text(json.dumps(data))
    except OSError:
        pass  # non-fatal: cache write failure just means no caching


def get(path: str, ttl: int = _SEARCH_TTL) -> dict:
    """
    Make an authenticated GET to api.github.com/<path>.
    Returns the parsed JSON dict. Raises RuntimeError on API errors
    (including rate limit) with a human-readable message.

    Uses disk cache: same path within TTL returns cached data, no API call.
    """
    url = f"https://api.github.com{path}"

    cached = _from_cache(url, ttl)
    if cached is not None:
        return cached

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "romforge/2.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    tok = _resolve_token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            # Warn if remaining calls are getting low
            remaining = resp.headers.get("X-RateLimit-Remaining", "?")
            reset_ts  = resp.headers.get("X-RateLimit-Reset", "0")
            if remaining != "?" and int(remaining) < 10:
                reset_in = max(0, int(reset_ts) - int(time.time()))
                print(f"  [github] ⚠ Only {remaining} API calls remaining "
                      f"(resets in {reset_in//60}m {reset_in%60}s). "
                      f"Set a GITHUB_TOKEN to get 5,000/hr.")
            _to_cache(url, data)
            return data
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()
            msg = json.loads(body).get("message", body)
        except Exception:
            msg = body or str(e)
        if e.code == 403 and "rate limit" in msg.lower():
            reset_ts = e.headers.get("X-RateLimit-Reset", "0")
            reset_in = max(0, int(reset_ts) - int(time.time()))
            raise RuntimeError(
                f"GitHub API rate limit exceeded. Resets in "
                f"{reset_in//60}m {reset_in%60}s.\n"
                f"Fix: set GITHUB_TOKEN or run Settings → GitHub token in the TUI.\n"
                f"A free PAT (no scopes needed) raises the limit to 5,000/hr."
            )
        raise RuntimeError(f"GitHub API error {e.code}: {msg}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error reaching GitHub: {e.reason}")


def search_repos(query: str, max_results: int = 10) -> list[dict]:
    """
    Search GitHub repositories. Returns a list of repository dicts
    (full_name, clone_url, html_url, stargazers_count, pushed_at).
    Returns [] on rate-limit or network error (caller decides how to
    surface this — don't crash the whole tool on a search failure).
    """
    import urllib.parse
    encoded = urllib.parse.quote(query)
    try:
        data = get(f"/search/repositories?q={encoded}&sort=stars&order=desc&per_page={max_results}")
        return data.get("items", [])
    except RuntimeError as e:
        print(f"  [github] Search failed: {e}")
        return []


def get_release(api_url: str) -> dict | None:
    """Fetch a release endpoint (e.g. Magisk latest release). Cached 24hr."""
    try:
        # api_url is a full URL like https://api.github.com/repos/.../releases/latest
        path = api_url.replace("https://api.github.com", "")
        return get(path, ttl=_RELEASE_TTL)
    except RuntimeError as e:
        print(f"  [github] Release fetch failed: {e}")
        return None


def clear_cache() -> int:
    """Delete all cached API responses. Returns number of files removed."""
    if not _CACHE_DIR.exists():
        return 0
    count = 0
    for f in _CACHE_DIR.glob("*.json"):
        f.unlink(missing_ok=True)
        count += 1
    return count
