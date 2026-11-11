"""Opt-in isolated Docker test: HUGO_DOCKER_SMOKE=1, image hugo:local built."""
import os
import socket
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.passwords import hash_password


@pytest.mark.skipif(os.getenv("HUGO_DOCKER_SMOKE") != "1", reason="Docker smoke is opt-in")
def test_docker_start_login_and_update():
    root = Path(__file__).resolve().parents[1]
    project = "hugo-smoke-" + uuid4().hex[:10]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    password = "smoke-test-password-only"
    env = dict(os.environ, DB_PASSWORD="smoke-db-password", DB_USER="hugo", DB_NAME="hugo",
               OPENAI_API_KEY="sk-smoke-no-model-calls", HUGO_PASSWORD_HASH=hash_password(password),
               HUGO_COOKIE_SECURE="false", WEB_PORT=f"127.0.0.1:{port}", HUGO_IMAGE="hugo:local",
               SCHEDULER_HOUR=str((datetime.now(ZoneInfo("Europe/Berlin")).hour + 2) % 24), SCHEDULER_MINUTE="0")
    command = ["docker", "compose", "--env-file", ".env.prod.template", "-p", project, "-f", "compose.prod.yaml"]

    def compose(*args):
        result = subprocess.run(command + list(args), cwd=root, env=env, capture_output=True, text=True, timeout=240)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    try:
        compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "180")
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=20) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/conversations").status_code == 401
            response = client.post("/ui/login", data={"password": password, "remember": "on"},
                                   headers={"Origin": f"http://127.0.0.1:{port}"})
            assert response.status_code == 303
            assert "Max-Age=" in response.headers["set-cookie"]
            assert client.get("/ui/chat").status_code == 200
            compose("exec", "-T", "worker", "python", "-c",
                    "from pathlib import Path; import urllib.request; "
                    "Path('/home/hugo/.cache/huggingface/smoke').touch(); "
                    "urllib.request.urlopen('https://example.com', timeout=20)")
            compose("stop", "web", "worker")
            compose("run", "--rm", "--no-deps", "migrate")
            compose("up", "-d", "--no-deps", "--force-recreate", "--wait", "web", "worker")
            assert client.get("/ui/chat").status_code == 200
            assert "Scheduler started" in compose("logs", "worker")
    finally:
        # Only resources belonging to this randomly named test project are removed.
        compose("down", "--volumes", "--remove-orphans")
