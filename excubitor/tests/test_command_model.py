"""Real subprocess and HTTP transport checks, independent of any installed LLM."""

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from excubitor.command_model import CommandStructuredModel
from excubitor.development_adapters import make_runtime, normalize
from excubitor.development_runtime import BASELINE, LOCAL_BASELINE
from excubitor.local_development import LocalDevelopmentExecutor
from excubitor.runs import RunError

pytestmark = pytest.mark.skipif(os.name != "nt", reason="native Windows process transport")


def run():
    return SimpleNamespace(contract=SimpleNamespace(deadline=time.time() + 30))


def bridge(tmp_path, body):
    path = tmp_path / "client.py"
    path.write_text(body, encoding="utf-8")
    return CommandStructuredModel(
        [sys.executable, "-I", "-B", str(path)], tmp_path, environment=dict(os.environ), model="any-model"
    )


def test_fresh_process_receives_only_current_prompt_and_echoes_bound_response(tmp_path):
    model = bridge(
        tmp_path,
        """import json,sys
r=json.load(sys.stdin)
print(json.dumps({k:r[k] for k in ('protocol','id','model')} | {'output':{'seen':r['prompt']}}))
""",
    )
    for prompt in ("first unit", "second unit"):
        result, response = model.generate(run(), prompt, {}, threading.Event())
        assert result.drained and result.execution.exit_code == 0 and response == {"seen": prompt}
    requests = [json.loads(p.read_text()) for p in tmp_path.glob("model-*/request.json")]
    assert len({r["id"] for r in requests}) == 2
    assert {r["model"] for r in requests} == {"any-model"}


def test_wrong_request_identity_is_not_accepted(tmp_path):
    model = bridge(
        tmp_path,
        """import json,sys
r=json.load(sys.stdin); r['id']='another-request'
print(json.dumps({k:r[k] for k in ('protocol','id','model')} | {'output':{}}))
""",
    )
    with pytest.raises(RunError, match="invalid response"):
        model.generate(run(), "work", {}, threading.Event())


def test_malformed_bridge_reply_is_a_drained_retryable_failure(tmp_path):
    model = bridge(tmp_path, "print('not JSON')\n")
    result, response = model.generate(run(), "work", {}, threading.Event())
    assert response is None and result.drained
    assert result.execution.exit_code == 1 and result.retryable_error == "model-output"


def test_cancelled_model_process_drains_without_a_proposal(tmp_path):
    model = bridge(tmp_path, "import time\ntime.sleep(20)\n")
    cancel = threading.Event()
    timer = threading.Timer(0.4, cancel.set)
    timer.start()
    try:
        result, response = model.generate(run(), "work", {}, cancel)
    finally:
        timer.join()
    assert result.cancelled and result.drained and response is None


def test_local_executor_is_explicit_and_supports_stdin_without_vendor(tmp_path):
    candidate, evidence = tmp_path / "candidate", tmp_path / "evidence"
    candidate.mkdir()
    evidence.mkdir()
    with pytest.raises(RunError, match="explicit"):
        LocalDevelopmentExecutor(candidate, evidence, environment={}, baseline=BASELINE)
    executor = LocalDevelopmentExecutor(
        candidate, evidence, environment=dict(os.environ), baseline=LOCAL_BASELINE
    )
    result = executor.run(
        (sys.executable, "-I", "-B", "-c", "import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())"),
        stdin=b"binary\x00input",
        mode="read-only",
    )
    assert result.drained and result.execution.stdout == b"binary\x00input"
    assert result.execution.exit_code == 0


@pytest.fixture
def endpoint():
    received = []
    response = {"choices": [{"finish_reason": "stop", "message": {"content": '{"files":[],"command":[]}'}}]}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            raw = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1/chat/completions", received, response
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_http_adapter_uses_same_runtime_with_fresh_messages(endpoint, tmp_path):
    url, received, response = endpoint
    candidate, evidence = tmp_path / "candidate", tmp_path / "evidence"
    candidate.mkdir()
    evidence.mkdir()
    (candidate / "main.py").write_text("current source")
    settings = {
        "llm": {
            "adapter": "chat-completions",
            "endpoint": url,
            "api_key_env": "",
            "response_format": "json_schema",
            "model": "local-model",
        },
        "executor": {"adapter": "windows-process"},
        "editable": ["main.py"],
    }
    executor = LocalDevelopmentExecutor(
        candidate, evidence, environment=dict(os.environ), baseline=LOCAL_BASELINE
    )
    runtime = make_runtime(
        settings,
        candidate,
        evidence,
        executor=executor,
        environment=dict(os.environ),
        baseline=LOCAL_BASELINE,
    )
    for prompt in ("first", "second"):
        result, output = runtime._call(run(), prompt, threading.Event(), review=False)
        assert result.execution.exit_code == 0 and output == {"files": [], "command": []}
    assert len(received) == 2 and all(len(r["messages"]) == 1 for r in received)
    assert all(r["model"] == "local-model" and not r.get("tools") for r in received)
    assert "current source" in received[1]["messages"][0]["content"]
    response["choices"][0]["finish_reason"] = "length"
    result, output = runtime._call(run(), "third", threading.Event(), review=False)
    assert result.execution.exit_code != 0 and output is None


def test_mixed_descriptor_format_is_rejected_before_execution(tmp_path):
    with pytest.raises(RunError, match="separate llm"):
        normalize({"claude": sys.executable, "llm": {}, "executor": {}})
