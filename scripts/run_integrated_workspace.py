"""One local entry point: Toujing UI plus the current company research engine.

Only starts owned child processes. It neither installs dependencies nor changes
an installed app, account database, provider key file, or the original project.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company-workspace", type=Path)
    parser.add_argument("--provider-env-file", type=Path)
    parser.add_argument("--port", type=int, default=18022)
    parser.add_argument("--engine-port", type=int, default=18024)
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    if not all(1 <= port <= 65535 for port in (args.port, args.engine_port)) or args.port == args.engine_port:
        parser.error("Use two distinct local ports between 1 and 65535")
    config_path = ROOT / ".local/company-integration.json"
    config = json.loads(config_path.read_text()) if config_path.is_file() else {}
    workspace = (args.company_workspace or Path(config.get("workspace", ROOT.parent / "CompanyTwin_问答完善工作区"))).resolve()
    provider_env = args.provider_env_file or (Path(config["provider_env_file"]) if config.get("provider_env_file") else None)
    python = workspace / ".venv/bin/python"
    if not python.is_file() or not (workspace / "src/cot/serving/mvp_server.py").is_file():
        parser.error("Company research workspace or its Python environment is missing")
    if provider_env and not provider_env.is_file():
        parser.error("The selected provider environment file does not exist")
    for port in (args.port, args.engine_port):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                if port == args.port:
                    from urllib.request import build_opener, ProxyHandler
                    try:
                        with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:{port}/api/workspace-status", timeout=2) as response:
                            running = json.load(response)
                        expected = hashlib.sha256(str((ROOT / "apps/desktop/dist").resolve()).encode()).hexdigest()[:16]
                        if running.get("application") == "toujing-company-integration" and running.get("source_id") == expected:
                            url = f"http://127.0.0.1:{args.port}/#/company-research"
                            print(f"投镜整合版已运行：{url}", flush=True)
                            if args.open_browser:
                                webbrowser.open(url)
                            return
                    except (OSError, ValueError):
                        pass
                parser.error(f"Local port {port} is already in use; the existing process was left running")
    if not args.no_build:
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "apps/desktop", check=True)
    dist = ROOT / "apps/desktop/dist"
    if not (dist / "index.html").is_file():
        parser.error("Build the Toujing desktop frontend first")
    config_path.parent.mkdir(exist_ok=True)
    config_path.write_text(json.dumps({"workspace": str(workspace), "provider_env_file": str(provider_env) if provider_env else None}, ensure_ascii=False, indent=2) + "\n")
    config_path.chmod(0o600)
    command = [str(python), str(ROOT / "scripts/run_company_research_engine.py"), "--workspace", str(workspace), "--port", str(args.engine_port)]
    if provider_env:
        command += ["--provider-env-file", str(provider_env)]
    engine = subprocess.Popen(command, cwd=workspace)
    server = None
    try:
        os.environ["TOUJING_COMPANY_API_URL"] = f"http://127.0.0.1:{args.engine_port}"
        from toujing_core_runtime.company_research import CompanyResearchClient, CompanyResearchError
        from scripts.company_research_web import make_server
        client = CompanyResearchClient()
        for _ in range(100):
            if engine.poll() is not None:
                raise SystemExit("Company research engine did not start")
            try:
                status = client.call("company_research.status", {})
                if status.get("application") != "company-operating-twin":
                    raise SystemExit("Unexpected service on the research port")
                break
            except CompanyResearchError:
                time.sleep(.2)
        else:
            raise SystemExit("Company research engine startup timed out")
        from toujing_community.service import CommunityService
        community = CommunityService(ROOT / ".local/community/community.sqlite3", [f"http://127.0.0.1:{args.port}", f"http://localhost:{args.port}"])
        server = make_server(args.port, dist, client=client, community=community)
        print(f"投镜整合版：http://127.0.0.1:{args.port}/#/company-research", flush=True)
        if args.open_browser:
            webbrowser.open(f"http://127.0.0.1:{args.port}/#/company-research")
        server.serve_forever(poll_interval=.5)
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.server_close()
        engine.terminate()
        try:
            engine.wait(timeout=15)
        except subprocess.TimeoutExpired:
            engine.kill()
            engine.wait()


if __name__ == "__main__":
    main()
