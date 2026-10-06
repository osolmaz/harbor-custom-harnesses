import asyncio
import json
import subprocess
import sys
from pathlib import Path

from harbor_hermes_acp import relay

MODEL = "openai/deepseek-ai/DeepSeek-V4.1-Flash:novita"

# A fake hermes-acp: answers session/new with only the older models field and
# echoes every other request as its result.
FAKE_AGENT = """
import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "session/new":
        result = {"sessionId": "s", "models": {"currentModelId": "m"}}
    else:
        result = {"echo": message.get("method")}
    if "id" in message:
        reply = {"jsonrpc": "2.0", "id": message["id"], "result": result}
        print(json.dumps(reply), flush=True)
print("not json", flush=True)
sys.exit(4)
"""


def request(request_id: int, method: str, params: dict[str, object]) -> bytes:
    message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    return json.dumps(message).encode() + b"\n"


def select(request_id: int, value: str, config_id: str = "model") -> bytes:
    params = {"sessionId": "s", "configId": config_id, "value": value}
    return request(request_id, "session/set_config_option", params)


def test_select_reply_accepts_only_the_pinned_model() -> None:
    accepted = relay.select_reply(json.loads(select(1, MODEL)), MODEL)
    assert accepted == {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"configOptions": [relay.model_option(MODEL)]},
    }
    rejected = relay.select_reply(json.loads(select(2, "other")), MODEL)
    assert rejected is not None
    assert rejected["error"]["code"] == relay.INVALID_PARAMS


def test_select_reply_ignores_other_messages() -> None:
    assert relay.select_reply(json.loads(select(1, "x", "mode")), MODEL) is None
    assert relay.select_reply({"method": "session/set_config_option"}, MODEL) is None
    assert relay.select_reply(json.loads(request(1, "session/new", {})), MODEL) is None


def test_add_model_option_replaces_an_existing_model_option() -> None:
    other = {"id": "mode", "currentValue": "x"}
    message = {"id": 1, "result": {"configOptions": [other, {"id": "model"}]}}
    added = relay.add_model_option(message, MODEL)
    assert added["result"]["configOptions"] == [other, relay.model_option(MODEL)]
    assert relay.add_model_option({"id": 1, "error": {}}, MODEL) == {
        "id": 1,
        "error": {},
    }


def test_parse_keeps_only_json_objects() -> None:
    assert relay.parse(b'{"a": 1}\n') == {"a": 1}
    assert relay.parse(b"[1]\n") is None
    assert relay.parse(b"not json\n") is None


def test_from_agent_passes_notifications_and_unknown_lines() -> None:
    session = relay.Relay(MODEL, lambda data: None)
    notification = b'{"method": "session/update", "id": 1}\n'
    assert session.from_agent(notification) == notification
    assert session.from_agent(b"text\n") == b"text\n"
    assert session.from_client(b"text\n") == b"text\n"


async def run_relay(lines: list[bytes]) -> tuple[int, list[bytes]]:
    client = asyncio.StreamReader()
    for line in lines:
        client.feed_data(line)
    client.feed_eof()
    emitted: list[bytes] = []
    command = [sys.executable, "-c", FAKE_AGENT]
    code = await relay.relay(command, {}, MODEL, client, emitted.append)
    return code, emitted


def test_relay_adds_the_model_option_and_answers_selection() -> None:
    lines = [
        request(1, "initialize", {}),
        request(2, "session/new", {"cwd": "/app"}),
        select(3, MODEL),
        select(4, "other"),
        request(5, "session/prompt", {"sessionId": "s"}),
    ]
    code, emitted = asyncio.run(run_relay(lines))
    assert code == 4
    texts = [line for line in emitted if not line.startswith(b"not json")]
    messages = {message["id"]: message for message in map(json.loads, texts)}
    assert messages[1]["result"] == {"echo": "initialize"}
    assert messages[2]["result"]["configOptions"] == [relay.model_option(MODEL)]
    assert messages[2]["result"]["models"] == {"currentModelId": "m"}
    assert messages[3]["result"] == {"configOptions": [relay.model_option(MODEL)]}
    assert messages[4]["error"]["code"] == relay.INVALID_PARAMS
    assert messages[5]["result"] == {"echo": "session/prompt"}
    assert emitted[-1] == b"not json\n"


def test_serve_relays_the_process_streams(tmp_path: Path) -> None:
    script = tmp_path / "serve.py"
    script.write_text(
        "import asyncio, sys\n"
        "from harbor_hermes_acp.relay import serve\n"
        f"command = [sys.executable, '-c', {FAKE_AGENT!r}]\n"
        f"sys.exit(asyncio.run(serve(command, {{}}, {MODEL!r})))\n"
    )
    done = subprocess.run(
        [sys.executable, str(script)],
        input=request(1, "session/new", {}),
        capture_output=True,
        check=False,
    )
    assert done.returncode == 4
    first = json.loads(done.stdout.splitlines()[0])
    assert first["result"]["configOptions"] == [relay.model_option(MODEL)]
