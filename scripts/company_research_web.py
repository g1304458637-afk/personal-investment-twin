"""Same-origin local web host for the integrated workspace, never an account API."""
from __future__ import annotations

import json
import hashlib
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from toujing_core_runtime.company_research import CompanyResearchClient, CompanyResearchError, METHODS


def make_server(port: int, dist: Path, *, client=None):
    adapter = client or CompanyResearchClient()
    root = dist.resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send(self, status, payload, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            if self.command != "HEAD":
                try:
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def json(self, status, payload):
            self.send(status, json.dumps(payload, ensure_ascii=False, allow_nan=False).encode())

        def trusted_host(self):
            return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def do_GET(self):
            if not self.trusted_host():
                return self.json(403, {"error": {"code": "invalid_host"}})
            path = unquote(urlsplit(self.path).path)
            if path == "/api/workspace-status":
                return self.json(200, {"application": "toujing-company-integration",
                                       "source_id": hashlib.sha256(str(root).encode()).hexdigest()[:16]})
            if path.startswith("/api/"):
                return self.json(404, {"error": {"code": "unknown_endpoint"}})
            target = (root / path.lstrip("/")).resolve()
            if not target.is_relative_to(root):
                return self.json(403, {"error": {"code": "invalid_path"}})
            if not target.is_file():
                if Path(path).suffix:
                    return self.json(404, {"error": {"code": "asset_not_found"}})
                target = root / "index.html"
            try:
                self.send(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            except OSError:
                self.json(404, {"error": {"code": "asset_not_found"}})

        do_HEAD = do_GET

        def do_POST(self):
            allowed = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
            origin = self.headers.get("Origin")
            if (not self.trusted_host() or (origin is not None and origin not in allowed)
                    or self.headers.get("Sec-Fetch-Site") == "cross-site"):
                return self.json(403, {"error": {"code": "invalid_origin", "message": "仅允许本机投镜界面调用。"}})
            if self.path != "/api/company-research":
                return self.json(404, {"error": {"code": "unknown_endpoint"}})
            if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
                return self.json(415, {"error": {"code": "invalid_content_type"}})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 64_000:
                    return self.json(413, {"error": {"code": "request_too_large"}})
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict) or set(body) != {"method", "params"} or body["method"] not in METHODS:
                    raise ValueError("invalid method")
                result = adapter.call(body["method"], body["params"])
                self.json(200, {"ok": True, "result": result, "error": None})
            except CompanyResearchError as error:
                self.json(error.status, {"ok": False, "result": None, "error": {"code": error.code, "message": str(error)}})
            except (ValueError, TypeError, KeyError):
                self.json(422, {"ok": False, "error": {"code": "invalid_params", "message": "公司研究请求格式无效。"}})
            except Exception:
                self.json(500, {"ok": False, "error": {"code": "company_engine_error", "message": "公司研究暂不可用。"}})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
