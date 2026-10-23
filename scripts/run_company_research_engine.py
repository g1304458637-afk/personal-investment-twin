"""Run the existing company engine in its own Python environment."""
import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--provider-env-file", type=Path)
    parser.add_argument("--port", type=int, default=18024)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if not (workspace / "src/cot/onboarding/service.py").is_file():
        parser.error("Company engine source was not found")
    sys.path.insert(0, str(workspace / "src"))
    if args.provider_env_file:
        from dotenv import dotenv_values
        # Reuse just the existing provider credential; never copy or log it.
        value = dotenv_values(args.provider_env_file, interpolate=False).get("DEEPSEEK_API_KEY")
        if value and not os.environ.get("DEEPSEEK_API_KEY"):
            os.environ["DEEPSEEK_API_KEY"] = value
    import uvicorn
    from cot.onboarding.service import BuildConfig, GenericBuildService
    from cot.serving.mvp_server import create_app
    config = BuildConfig(database=workspace / ".local/competition_mvp.db",
                         artifact_root=workspace / ".local/source_archive",
                         build_root=workspace / ".local/competition_builds")
    service = GenericBuildService(config)
    uvicorn.run(create_app(service=service, generic=True), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
