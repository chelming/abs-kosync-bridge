"""Tests for reports_site/respond-finding.ps1 (Phase 13 maintainer response helper)."""

import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

_SCRIPT = str(
    Path(__file__).resolve().parent.parent / "reports_site" / "respond-finding.ps1"
)
_POWERSHELL = "powershell.exe"


def _powershell_available() -> bool:
    try:
        subprocess.run(
            [_POWERSHELL, "-NoProfile", "-Command", "exit 0"],
            capture_output=True,
            timeout=10,
        )
        return True
    except FileNotFoundError:
        return False


_skip = not _powershell_available()


class _MockHandler(BaseHTTPRequestHandler):
    """Collects the most recent request for inspection by tests."""

    last_method: str = ""
    last_path: str = ""
    last_headers: dict = {}
    last_body: bytes = b""
    # Class-level config set by each test before starting the server
    respond_code: int = 200
    respond_body: dict = {"ok": True}

    def do_PATCH(self):  # noqa: N802 – http.server naming
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _MockHandler.last_method = "PATCH"
        _MockHandler.last_path = self.path
        _MockHandler.last_headers = dict(self.headers)
        _MockHandler.last_body = body
        payload = json.dumps(self.respond_body).encode()
        self.send_response(self.respond_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    # Suppress noisy request logs
    def log_message(self, fmt, *args):  # noqa: D102
        pass


class _BaseTestCase(unittest.TestCase):
    """Shared setUp / helper methods for respond-finding.ps1 tests."""

    server: HTTPServer
    server_thread: threading.Thread
    base_url: str

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _MockHandler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        _MockHandler.respond_code = 200
        _MockHandler.respond_body = {"ok": True}
        _MockHandler.last_method = ""
        _MockHandler.last_path = ""
        _MockHandler.last_headers = {}
        _MockHandler.last_body = b""

        self._token_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._token_dir.cleanup()

    def _run_ps(self, args: list[str], token_content: str = "test-token-abc") -> subprocess.CompletedProcess:
        """Write a temp token file, invoke the script, return the result."""
        token_dir = Path(self._token_dir.name)
        token_file = token_dir / "diagnostics-read.key"
        token_file.write_text(token_content, encoding="utf-8")

        cmd = [
            _POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-File", _SCRIPT,
        ] + args

        env = os.environ.copy()
        env["USERPROFILE"] = str(token_dir)  # point default token lookup here

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        return result

    def _run_ps_with_endpoint(
        self,
        finding_id: int,
        message: str,
        extra_args: list[str] | None = None,
        token_content: str = "test-token-abc",
        endpoint: str | None = None,
    ) -> subprocess.CompletedProcess:
        args = [
            "-Endpoint", endpoint or self.base_url,
            "-TokenFile", str(Path(self._token_dir.name) / "diagnostics-read.key"),
            str(finding_id),
            message,
        ]
        if extra_args:
            args = extra_args + args
        # Write token first
        token_dir = Path(self._token_dir.name)
        (token_dir / "diagnostics-read.key").write_text(token_content, encoding="utf-8")
        return self._run_ps(args, token_content)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@unittest.skipIf(_skip, "powershell.exe not available")
class TestValidInvocation(_BaseTestCase):
    """Valid PATCH sends the right path, Bearer header, body, and prints success."""

    def test_sends_correct_request_and_prints_success(self):
        _MockHandler.respond_code = 200
        _MockHandler.respond_body = {"ok": True}

        msg = 'Bug will be fixed in the next "beta".\nLine two.'
        result = self._run_ps_with_endpoint(4, msg)

        # Script exited 0
        self.assertEqual(result.returncode, 0, result.stderr)

        # stdout contains success, does NOT contain the token
        self.assertEqual(result.stdout.strip(), "Response saved for finding #4.")
        self.assertNotIn("test-token-abc", result.stdout)

        # stderr does NOT contain the token
        self.assertNotIn("test-token-abc", result.stderr)

        # HTTP details
        self.assertEqual(_MockHandler.last_method, "PATCH")
        self.assertEqual(_MockHandler.last_path, "/api/v1/findings/4")

        # Bearer header present, token not echoed in body (PS 5.1 sends capital-A Authorization)
        auth = _MockHandler.last_headers.get("Authorization", "")
        self.assertEqual(auth, "Bearer test-token-abc")

        # Body contains exact response_md with quotes and newline preserved
        body = json.loads(_MockHandler.last_body)
        self.assertEqual(body["response_md"], msg)


@unittest.skipIf(_skip, "powershell.exe not available")
class TestEmptyMessage(_BaseTestCase):
    """Empty message is rejected before any HTTP request."""

    def test_empty_message_fails(self):
        _MockHandler.respond_code = 200
        result = self._run_ps_with_endpoint(4, "   ")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("empty", result.stderr.lower())
        # No HTTP request should have been made
        self.assertEqual(_MockHandler.last_method, "")


@unittest.skipIf(_skip, "powershell.exe not available")
class TestOverlongMessage(_BaseTestCase):
    """Message over 10000 chars is rejected before any HTTP request."""

    def test_overlong_message_fails(self):
        _MockHandler.respond_code = 200
        msg = "x" * 10001
        result = self._run_ps_with_endpoint(4, msg)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("10000", result.stderr)
        self.assertEqual(_MockHandler.last_method, "")


@unittest.skipIf(_skip, "powershell.exe not available")
class TestUpstreamError(_BaseTestCase):
    """Non-2xx from server: exit 1, no token in stdout/stderr."""

    def test_upstream_error_no_token_leak(self):
        _MockHandler.respond_code = 500
        _MockHandler.respond_body = {"ok": False, "error": "internal"}

        result = self._run_ps_with_endpoint(
            4,
            "Bug will be fixed.",
            token_content="secret-leaky-token-999",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("secret-leaky-token-999", result.stdout)
        self.assertNotIn("secret-leaky-token-999", result.stderr)
        self.assertIn("500", result.stderr)


if __name__ == "__main__":
    unittest.main()
