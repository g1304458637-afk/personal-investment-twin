"""Bounded company-research adapter; account facts never cross this boundary.

The company engine keeps its Python environment, immutable model versions and
evidence store. Both desktop RPC and the local web workspace use this adapter.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

METHODS = (
    "company_research.status", "company_research.list", "company_research.load",
    "company_research.resolve", "company_research.build", "company_research.snapshot",
    "company_research.ask", "company_research.chat", "company_research.report",
)
MAX_RESPONSE = 32 * 1024 * 1024


class CompanyResearchError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 503):
        super().__init__(message)
        self.code, self.status = code, status


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _text(params, key, maximum=500):
    value = params.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{key} must be nonempty and at most {maximum} characters")
    return value.strip()


class CompanyResearchClient:
    def __init__(self, base_url=None, *, opener=None):
        self.base_url = base_url or os.environ.get("TOUJING_COMPANY_API_URL", "http://127.0.0.1:18024")
        parsed = urlparse(self.base_url)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
                or parsed.username or parsed.password or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment or not parsed.port):
            raise ValueError("Company engine must be an explicit 127.0.0.1 HTTP port")
        self.base_url = self.base_url.rstrip("/")
        # Never forward public-company requests through an ambient HTTP proxy,
        # and never follow a redirect out of this loopback service boundary.
        self.opener = opener or build_opener(ProxyHandler({}), _NoRedirect())

    def _request(self, path, body=None, *, html=False):
        request = Request(self.base_url + path,
                          data=None if body is None else json.dumps(body).encode(),
                          headers={"Accept": "text/html" if html else "application/json",
                                   "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=150 if path.endswith("/chat") else 45) as response:
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise CompanyResearchError("company_response_too_large", "公司资料超过本次读取上限。", 502)
                return raw.decode("utf-8") if html else json.loads(raw)
        except HTTPError as error:
            codes = {404: ("company_not_found", "未找到公司模型，请刷新列表。"),
                     409: ("company_not_ready", "公司模型尚未完成，或已有建模任务运行。"),
                     422: ("company_invalid_request", "公司查询或问题格式不受支持。"),
                     503: ("company_model_unavailable", "公司研究模型尚未配置或暂不可用。"),
                     502: ("company_provider_failed", "模型服务未返回可用的有据回答。")}
            code, message = codes.get(error.code, ("company_engine_error", "公司研究服务暂不可用，请稍后重试。"))
            raise CompanyResearchError(code, message, error.code) from error
        except (URLError, TimeoutError, ConnectionError, OSError) as error:
            raise CompanyResearchError("company_engine_unavailable", "公司研究引擎未连接，请通过整合版启动入口打开投镜。") from error
        except (ValueError, UnicodeError) as error:
            raise CompanyResearchError("company_invalid_response", "公司研究引擎返回了无法读取的资料。", 502) from error

    def call(self, method, params):
        if method not in METHODS:
            raise ValueError("unsupported company research method")
        if not isinstance(params, Mapping):
            raise ValueError("params must be an object")
        action = method.removeprefix("company_research.")
        keys = {"status": set(), "list": set(), "load": {"build_id"},
                "resolve": {"query"}, "build": {"query"}, "snapshot": {"build_id"},
                "ask": {"build_id", "question"}, "chat": {"build_id", "messages"},
                "report": {"build_id"}}[action]
        if set(params) != keys:
            raise ValueError("unexpected company research parameters")
        if action == "status":
            return self._request("/api/capabilities")
        if action == "list":
            return self._request("/api/builds?limit=100")
        if action in {"resolve", "build"}:
            query = _text(params, "query", 200)
            return self._request("/api/companies/resolve?" + urlencode({"query": query})) if action == "resolve" else self._request("/api/builds", {"query": query})
        build_id = _text(params, "build_id", 100)
        if not re.fullmatch(r"build_[A-Za-z0-9]+", build_id):
            raise ValueError("invalid company build id")
        path = f"/api/builds/{build_id}"
        if action == "load":
            analysis = self._request(path + "/analysis")
            graph = self._request(path + "/graph")
            if analysis.get("version_id") != graph.get("modelVersion", {}).get("id"):
                raise CompanyResearchError("company_version_mismatch", "财务与图谱版本不一致，请重新打开模型。", 409)
            return {"build_id": build_id, "analysis": analysis, "graph": graph}
        if action == "report":
            return {"html": self._request(path + "/report.html?lang=zh", html=True)}
        if action == "snapshot":
            return self._request(path + "/snapshot")
        if action == "ask":
            return self._request(path + "/ask", {"question": _text(params, "question")})
        messages = params.get("messages")
        if not isinstance(messages, list) or not 1 <= len(messages) <= 12:
            raise ValueError("messages must contain 1 to 12 turns")
        for item in messages:
            if (not isinstance(item, dict) or set(item) != {"role", "content"}
                    or item.get("role") not in {"user", "assistant"}):
                raise ValueError("invalid company chat turn")
            _text(item, "content", 4000)
        if messages[-1]["role"] != "user":
            raise ValueError("last company chat turn must be a user question")
        return self._request(path + "/chat", {"messages": messages})
