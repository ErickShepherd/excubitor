"""Standalone Chat Completions client for the command-json model protocol.

Runs in a bounded child process so a stalled HTTP request cannot hold the loop
controller after cancellation. No provider SDK or native coding app is required.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def validate_endpoint(endpoint):
    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > 8192:
        raise ValueError("endpoint must be a bounded URL")
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme not in ("https", "http")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.scheme == "http"
        and parsed.hostname not in ("localhost", "127.0.0.1", "::1")
    ):
        raise ValueError("use an HTTPS endpoint or loopback HTTP without URL credentials")
    return endpoint


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def complete(request, endpoint, api_key_env, response_format):
    validate_endpoint(endpoint)
    key = os.environ.get(api_key_env) if api_key_env else None
    if api_key_env and not key:
        raise ValueError("the selected API-key environment variable is missing")
    structured = {"type": response_format}
    if response_format == "json_schema":
        structured["json_schema"] = {"name": "ralph_proposal", "strict": True, "schema": request["schema"]}
    prompt = (
        "Return only a JSON object matching this schema. Do not use tools.\n"
        + json.dumps(request["schema"])
        + "\n"
        + request["prompt"]
    )
    payload = {
        "model": request["model"],
        "messages": [dict(role="user", content=prompt)],
        "response_format": structured,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    native = urllib.request.Request(
        endpoint, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.build_opener(NoRedirect()).open(native, timeout=150) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("model response exceeds two MiB")
    result = json.loads(raw)
    choices = result["choices"]
    if len(choices) != 1:
        raise ValueError("expected exactly one response")
    choice = choices[0]
    message = choice["message"]
    if choice["finish_reason"] != "stop" or message.get("tool_calls") or message.get("refusal"):
        raise ValueError("model did not finish a text-only proposal")
    output = json.loads(message["content"])
    if not isinstance(output, dict):
        raise ValueError("model proposal must be a JSON object")
    return {"protocol": request["protocol"], "id": request["id"], "model": request["model"], "output": output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--api-key-env", default="")
    parser.add_argument("--response-format", choices=("json_schema", "json_object"), default="json_schema")
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError("request too large")
        request = json.loads(raw)
        if request["protocol"] != "excubitor.model.v1":
            raise ValueError("unsupported model protocol")
        response = complete(request, args.endpoint, args.api_key_env, args.response_format)
        sys.stdout.write(json.dumps(response))
        return 0
    except urllib.error.HTTPError as error:
        # Do not persist provider error bodies, URLs, or authorization headers.
        print("Model endpoint returned HTTP " + str(error.code), file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        print("Model request failed or returned an incomplete response.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
