"""The desktop handshake must not wait for financial/Agent imports."""

import subprocess
import sys


def test_handshake_and_account_listing_do_not_load_analytics(tmp_path):
    script = '''
import io, json, sys
from toujing_core_runtime.protocol import run
requests = [dict(protocol_version="1", request_id=str(i), method=method, params={})
            for i, method in enumerate(("runtime.handshake", "account.list", "runtime.shutdown"))]
output = io.StringIO()
run(io.StringIO("".join(json.dumps(r) + "\\n" for r in requests)), output, db_path=sys.argv[1])
responses = [json.loads(line) for line in output.getvalue().splitlines()]
assert len(responses) == 3 and all(r["ok"] for r in responses), responses
for name in ("vectorbt", "src.core.portfolio_replay", "src.episodes.position_episode",
             "src.agents.decision_review", "toujing_core_runtime.review"):
    assert name not in sys.modules, name
'''
    subprocess.run([sys.executable, "-c", script, str(tmp_path / "startup.sqlite3")], check=True)


def test_quotes_status_does_not_load_agent_or_analytics_runtime():
    script = '''
import io, json, sys
from toujing_core_runtime.protocol import run
requests = [dict(protocol_version="1", request_id=str(i), method=method, params={})
            for i, method in enumerate(("quotes.status", "runtime.shutdown"))]
output = io.StringIO()
run(io.StringIO("".join(json.dumps(r) + "\\n" for r in requests)), output)
responses = [json.loads(line) for line in output.getvalue().splitlines()]
assert len(responses) == 2 and all(r["ok"] for r in responses), responses
for name in sys.modules:
    assert not (name == "agents" or name.startswith(("agents.", "src.agents", "vectorbt", "fullanalysis"))), name
'''
    subprocess.run([sys.executable, "-c", script], check=True)


def test_search_status_invalid_key_does_not_load_agent_or_analytics_runtime():
    script = '''
import io, json, sys
from toujing_core_runtime.protocol import run
requests = [
    dict(protocol_version="1", request_id="search", method="search.test_connection",
         params={"_desktop_bocha_key": ""}),
    dict(protocol_version="1", request_id="shutdown", method="runtime.shutdown", params={}),
]
output = io.StringIO()
run(io.StringIO("".join(json.dumps(r) + "\\n" for r in requests)), output)
responses = [json.loads(line) for line in output.getvalue().splitlines()]
assert responses[0]["result"] == {"connected": False, "reason": "search_not_configured"}, responses
assert responses[1]["ok"] is True, responses
for name in sys.modules:
    assert not (name == "agents" or name.startswith(("agents.", "src.agents", "vectorbt", "fullanalysis"))), name
'''
    subprocess.run([sys.executable, "-c", script], check=True)


def test_market_gate_public_exports_remain_compatible():
    from src.market_data import EpisodeBuildGateResult, build_episode_when_market_ready
    from src.market_data.episode_gate import EpisodeBuildGateResult as Result
    from src.market_data.episode_gate import build_episode_when_market_ready as build
    assert EpisodeBuildGateResult is Result
    assert build_episode_when_market_ready is build
