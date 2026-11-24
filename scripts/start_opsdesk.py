
"""Start the local OpsDesk demonstration services on Windows."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

OLLAMA_URL = "http://127.0.0.1:11434"
API_URL = "http://127.0.0.1:8000"
WEB_URL = "http://127.0.0.1:8501"

# Your existing Ollama startup script.
OLLAMA_START = Path(r"E:\ollama\start-ollama-e.cmd")


def get_json(url):
    """Return JSON from a healthy HTTP endpoint."""
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status == 200:
                return json.load(response)
    except (OSError, ValueError):
        pass
    return None


def http_ready(url):
    """Check whether an HTTP endpoint responds successfully."""
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def occupied(port):
    """Check whether a local TCP port is already occupied."""
    try:
        with socket.create_connection(
            ("127.0.0.1", port), timeout=1
        ):
            return True
    except OSError:
        return False


def wait_until(test, seconds=30):
    """Wait for a service health check."""
    deadline = time.monotonic() + seconds

    while time.monotonic() < deadline:
        if test():
            return True
        time.sleep(1)

    return test()


def new_console(command, cwd, env):
    """Start a process in a separate Windows console."""
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():

    # -------- 1. Validate project files --------

    require(
        os.name == "nt",
        "This launcher is designed for Windows.",
    )
    require(
        PYTHON.is_file(),
        "Missing .venv\\Scripts\\python.exe",
    )
    require(
        ENV_FILE.is_file(),
        "Missing .env in project root",
    )
    require(
        (ROOT / "frontend" / "app.py").is_file(),
        "Missing frontend/app.py",
    )

    # -------- 2. Load configuration --------

    config = dotenv_values(ENV_FILE)

    required_keys = (
        "OPSDESK_USER_KEY",
        "OPSDESK_APPROVER_KEY",
        "OPSDESK_CHECKPOINT_BACKEND",
        "OPSDESK_TICKET_PLANNER",
        "OPSDESK_DB_PATH",
        "OPSDESK_CHECKPOINT_PATH",
    )

    for key in required_keys:
        value = (config.get(key) or "").strip()

        require(
            value and not value.startswith("replace_with"),
            f"Set {key} in .env",
        )

    require(
        config["OPSDESK_USER_KEY"]
        != config["OPSDESK_APPROVER_KEY"],
        "Employee and approver keys must be different.",
    )

    require(
        config["OPSDESK_CHECKPOINT_BACKEND"].lower() == "sqlite",
        "OPSDESK_CHECKPOINT_BACKEND must be sqlite.",
    )

    # Values from .env override old terminal variables.
    env = os.environ.copy()
    env.update({
        k: v
        for k, v in config.items()
        if v is not None
    })

    env["OPSDESK_API_BASE_URL"] = API_URL
    env["PYTHONUNBUFFERED"] = "1"

    # -------- 3. Check or start Ollama --------

    print("[1/3] Checking Ollama...")

    models_info = get_json(
        OLLAMA_URL + "/api/tags"
    )

    if models_info is None:

        require(
            not occupied(11434),
            "Port 11434 is occupied but Ollama is not responding.",
        )

        require(
            OLLAMA_START.is_file(),
            f"Missing Ollama start script: {OLLAMA_START}",
        )

        new_console(
            ["cmd.exe", "/k", str(OLLAMA_START)],
            OLLAMA_START.parent,
            env,
        )

        require(
            wait_until(
                lambda: get_json(
                    OLLAMA_URL + "/api/tags"
                ) is not None
            ),
            "Ollama did not become ready. Check its console.",
        )

        models_info = get_json(
            OLLAMA_URL + "/api/tags"
        )

    else:
        print("  Ollama is already running; reusing it.")

    names = [
        model.get("name", "")
        for model in models_info.get("models", [])
    ]

    print(
        "  Available models:",
        ", ".join(names) or "(none)",
    )

    def model_found(requested):
        requested = requested.lower()

        return any(
            name.lower() == requested
            or (
                ":" not in requested
                and name.lower() == requested + ":latest"
            )
            for name in names
        )

    for key, default in (
        ("OLLAMA_CHAT_MODEL", "qwen3:8b"),
        ("OLLAMA_EMBED_MODEL", "bge-m3"),
    ):
        requested = env.get(key, default)

        require(
            model_found(requested),
            f"Ollama cannot see {requested}. "
            "Check OLLAMA_MODELS and model directories.",
        )

    # -------- 4. Check or start FastAPI --------

    print("[2/3] Checking FastAPI...")

    if occupied(8000):

        info = get_json(
            API_URL + "/openapi.json"
        )

        title = (
            ((info or {}).get("info") or {})
            .get("title", "")
        )

        require(
            "opsdesk" in title.lower(),
            "Port 8000 belongs to another service. "
            "Stop it before launching OpsDesk.",
        )

        print(
            "  OpsDesk FastAPI is already running; reusing it."
        )

    else:

        new_console(
            [
                str(PYTHON),
                "-m", "uvicorn",
                "api.app:app",
                "--host", "127.0.0.1",
                "--port", "8000",
            ],
            ROOT,
            env,
        )

        require(
            wait_until(
                lambda: http_ready(
                    API_URL + "/health"
                )
            ),
            "FastAPI did not become ready. Check its console.",
        )

        print("  FastAPI is ready.")

    # -------- 5. Check or start Streamlit --------

    print("[3/3] Checking Streamlit...")

    if occupied(8501):

        require(
            http_ready(
                WEB_URL + "/_stcore/health"
            ),
            "Port 8501 is occupied, "
            "but Streamlit is not healthy.",
        )

        print(
            "  Port 8501 already runs Streamlit. "
            "Verify that it is OpsDesk."
        )

    else:

        new_console(
            [
                str(PYTHON),
                "-m", "streamlit",
                "run",
                str(ROOT / "frontend" / "app.py"),
                "--server.address", "127.0.0.1",
                "--server.port", "8501",
                "--server.headless", "true",
            ],
            ROOT,
            env,
        )

        require(
            wait_until(
                lambda: http_ready(
                    WEB_URL + "/_stcore/health"
                )
            ),
            "Streamlit did not become ready. Check its console.",
        )

        print("  Streamlit is ready.")

    # -------- 6. Open the frontend --------

    print("\nStartup checks finished:", WEB_URL)

    webbrowser.open(WEB_URL)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)