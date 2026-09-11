"""Build the macOS Apple Silicon Toujing core sidecar reproducibly."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BINARY_NAME = "toujing-core"
SUPPORTED_TRIPLE = "aarch64-apple-darwin"


def target_triple() -> str:
    result = subprocess.run(
        ["rustc", "--print", "host-tuple"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build(mode: str) -> Path:
    triple = target_triple()
    if platform.system() != "Darwin" or platform.machine() != "arm64" or triple != SUPPORTED_TRIPLE:
        raise SystemExit(
            "Production Runtime v1 only builds on macOS Apple Silicon "
            f"({SUPPORTED_TRIPLE}); current target is {triple or 'unknown'}"
        )

    work_root = ROOT / "build" / "python-sidecar"
    dist_root = work_root / "dist"
    spec_root = work_root / "spec"
    shutil.rmtree(work_root, ignore_errors=True)
    dist_root.mkdir(parents=True)
    spec_root.mkdir(parents=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        f"--{mode}",
        "--console",
        "--noupx",
        "--target-arch",
        "arm64",
        "--name",
        BINARY_NAME,
        "--paths",
        str(ROOT),
        "--collect-data",
        "vectorbt",
        "--recursive-copy-metadata",
        "vectorbt",
        # Agents SDK dependencies inspect installed distribution metadata at import time.
        "--recursive-copy-metadata",
        "openai-agents",
        "--collect-data",
        "agents",
        # Only the quote modules we call; do not freeze the whole AKShare catalog.
        "--hidden-import",
        "akshare.stock.stock_info",
        "--hidden-import",
        "akshare.stock.stock_ask_bid_em",
        "--hidden-import",
        "akshare.stock_feature.stock_hist_em",
        "--hidden-import",
        "akshare.stock_fundamental.stock_finance_sina",
        "--collect-submodules",
        "akshare.utils",
        "--copy-metadata",
        "akshare",
        "--collect-data",
        "akshare",
        "--hidden-import",
        "curl_cffi",
        "--hidden-import",
        "curl_cffi.requests",
        "--collect-binaries",
        "curl_cffi",
        "--hidden-import",
        "akshare.utils.func",
        "--hidden-import",
        "akshare.utils.tqdm",
        "--hidden-import",
        "openpyxl",
        "--hidden-import",
        "lxml",
        "--hidden-import",
        "jsonpath",
        "--hidden-import",
        "tabulate",
        "--hidden-import",
        "_cffi_backend",
        "--collect-data",
        "certifi",
        "--collect-data",
        "curl_cffi",
        "--add-data",
        f"{ROOT / 'src' / 'agents' / 'dsa_vendor' / 'LICENSE'}:licenses/daily_stock_analysis",
        "--add-data",
        f"{ROOT / 'src' / 'agents' / 'dsa_vendor' / 'UPSTREAM.md'}:licenses/daily_stock_analysis",
        "--distpath",
        str(dist_root),
        "--workpath",
        str(work_root / "work"),
        "--specpath",
        str(spec_root),
        str(ROOT / "scripts" / "toujing_core_runtime_entry.py"),
    ]
    # Explicit Synthetic allowlist only; never package arbitrary account files.
    sys.path.insert(0, str(ROOT))
    from src.agents.desktop_demo_source import SOURCES
    for filename in sorted({name for source in SOURCES for name in (source.executions, source.prices)}):
        command[-1:-1] = ["--add-data", f"{ROOT / 'data' / 'sample' / filename}:data/sample"]
    subprocess.run(command, check=True, cwd=ROOT)

    built = dist_root / BINARY_NAME
    if mode == "onedir":
        built = built / BINARY_NAME
    if not built.is_file():
        raise SystemExit(f"PyInstaller did not create expected executable: {built}")
    if mode == "onedir":
        print(built)
        return built

    destination = ROOT / "apps" / "desktop" / "src-tauri" / "binaries" / f"{BINARY_NAME}-{triple}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, destination)
    destination.chmod(0o755)
    print(destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("onefile", "onedir"), default="onefile")
    args = parser.parse_args()
    build(args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
