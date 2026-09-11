"""Offline-safe Bocha transport and connection probe for the runtime boundary.

The desktop calls the probe during startup.  Keeping it here prevents an
availability check from importing public-research tools, the Agent SDK, or
financial analysis modules.  It performs no request unless given a valid key.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request


BOCHA_URL = "https://api.bochaai.com/v1/web-search"
BOCHA_TEST_QUERY = "上海证券交易所"
_INJECTION = re.compile(
    r"(ignore (previous|all) instructions|system prompt|do not follow|忽略(以上|之前)(指令|提示))",
    re.I,
)


def redact_web_text(text: object) -> str:
    """Bound and strip known instruction-like text from untrusted web excerpts."""

    if not isinstance(text, str):
        return ""
    cleaned = _INJECTION.sub("[removed]", text).strip()
    return cleaned[:400]


def bocha_web_search(key, query, *, count=5, summary=True, freshness="oneMonth", timeout=12, opener=None):
    """Fetch bounded, normalized public search results from Bocha."""

    payload = json.dumps({"query": query, "count": count, "summary": bool(summary),
                          "freshness": freshness}, ensure_ascii=False).encode()
    request = urllib.request.Request(BOCHA_URL, data=payload, method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json",
        "Accept": "application/json"})
    try:
        handler = opener or urllib.request.urlopen
        with handler(request, timeout=timeout) as response:
            raw = response.read(200_000)
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read(4000) if error.fp else b""
        if status == 401:
            raise ValueError("search_authentication_failed") from None
        if status == 403:
            raise ValueError("search_quota_or_forbidden") from None
        if status == 429:
            raise ValueError("search_rate_limited") from None
        raise ValueError("search_unavailable") from None
    except TimeoutError:
        raise ValueError("search_timeout") from None
    except Exception:
        raise ValueError("search_unavailable") from None
    if status != 200:
        raise ValueError("search_unavailable")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ValueError("search_response_invalid") from None
    if isinstance(body, dict) and body.get("code") not in (None, 200, "200"):
        raise ValueError("search_unavailable")
    data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else body
    pages = data.get("webPages") if isinstance(data, dict) else None
    rows = pages.get("value") if isinstance(pages, dict) else None
    if not isinstance(rows, list):
        raise ValueError("search_response_invalid")
    results = []
    for item in rows[:8]:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        title = item.get("name") or item.get("title")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            continue
        if not isinstance(title, str) or not title.strip():
            continue
        results.append({
            "title": title.strip()[:180], "url": url.strip()[:500],
            "site_name": item.get("siteName") if isinstance(item.get("siteName"), str) else None,
            "published_at": item.get("datePublished") if isinstance(item.get("datePublished"), str) else None,
            "excerpt": redact_web_text(item.get("summary") or item.get("snippet") or ""),
            "trust": "untrusted_public_web_not_instruction",
        })
    return {"provider": "bocha", "endpoint": "web-search", "query": query, "results": results}


def probe_search_connection(params):
    """Test the fixed public query without accepting user-provided search text."""

    if not isinstance(params, dict) or set(params) != {"_desktop_bocha_key"}:
        raise ValueError("invalid_search_test_request")
    key = params["_desktop_bocha_key"]
    if not isinstance(key, str) or not key or len(key) > 512 or not all(33 <= ord(c) <= 126 for c in key):
        return {"connected": False, "reason": "search_not_configured"}
    try:
        result = bocha_web_search(key, BOCHA_TEST_QUERY, count=1, summary=False, freshness="oneYear", timeout=15)
        if not result["results"]:
            return {"connected": False, "reason": "search_test_response_invalid"}
        return {"connected": True, "reason": None}
    except ValueError as error:
        reason = str(error)
        allowed = {"search_authentication_failed", "search_quota_or_forbidden", "search_rate_limited",
                   "search_timeout", "search_unavailable", "search_response_invalid"}
        return {"connected": False, "reason": reason if reason in allowed else "search_unavailable"}
