"""Desktop-only ephemeral credentials, never persisted or copied to os.environ."""
import asyncio

from agents import Agent, ModelSettings, Runner
from openai import AuthenticationError, RateLimitError

from src.agents.investment_coach import create_model_runtime


def desktop_runtime(key, factory=create_model_runtime):
    if not isinstance(key, str) or not key or len(key) > 512 or not all(33 <= ord(c) <= 126 for c in key):
        raise ValueError("model_not_configured")
    try:
        return factory(environment={"DEEPSEEK_API_KEY": key})
    except Exception:
        raise ValueError("model_configuration_failed") from None


async def _probe(key):
    runtime = desktop_runtime(key)
    try:
        # Same provider/model/Responses adapter; no account, retrieval or financial tool.
        agent = Agent(name="Connection check", instructions="Reply with OK only.",
                      model=runtime.model, tools=[],
                      model_settings=ModelSettings(reasoning=runtime.model_settings.reasoning))
        result = await asyncio.wait_for(Runner.run(agent, "Connection check", max_turns=1,
                                                 run_config=runtime.run_config), timeout=15)
        if not isinstance(result.final_output, str) or result.final_output.strip() != "OK":
            return {"connected": False, "reason": "model_test_response_invalid"}
        return {"connected": True, "reason": None}
    finally:
        # create_model_runtime owns a fresh AsyncOpenAI client for this probe.
        # SDK Model.close() is a no-op for HTTP Responses; close the injected client.
        await runtime.model._get_client().close()


def test_connection(params):
    """Only fixed public test text leaves the machine. Never propagate SDK bodies."""
    if not isinstance(params, dict) or set(params) != {"_desktop_model_key"}:
        raise ValueError("invalid_model_test_request")
    try:
        return asyncio.run(_probe(params["_desktop_model_key"]))
    except AuthenticationError:
        return {"connected": False, "reason": "model_authentication_failed"}
    except RateLimitError:
        return {"connected": False, "reason": "model_rate_limited"}
    except TimeoutError:
        return {"connected": False, "reason": "model_connection_timeout"}
    except Exception:
        return {"connected": False, "reason": "model_connection_failed"}
