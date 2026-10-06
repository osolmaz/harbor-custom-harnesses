"""Relay ACP between Harbor and hermes-acp and answer Harbor's model selection.

Harbor's ACP runner selects the model through a session config option in the
``model`` category. Hermes advertises its model only in the older ``models`` field,
so the relay adds one option that holds the pinned model to each new session and
answers the selection request itself. It accepts only the pinned model. Every other
message passes through unchanged, one JSON-RPC message per line.
"""

import asyncio
import json
import sys
from collections.abc import Callable, Sequence
from typing import Any

# One ACP message can carry a large tool result.
LINE_LIMIT = 64 * 1024 * 1024
INVALID_PARAMS = -32602


def model_option(model: str) -> dict[str, Any]:
    return {
        "id": "model",
        "name": "Model",
        "category": "model",
        "type": "select",
        "currentValue": model,
        "options": [{"value": model, "name": model}],
    }


def select_reply(message: dict[str, Any], model: str) -> dict[str, Any] | None:
    """Answer a model selection request; return None for every other message."""
    params = message.get("params")
    if message.get("method") != "session/set_config_option" or not isinstance(
        params, dict
    ):
        return None
    if params.get("configId") != "model":
        return None
    if params.get("value") == model:
        result = {"configOptions": [model_option(model)]}
        return {"jsonrpc": "2.0", "id": message.get("id"), "result": result}
    error = {"code": INVALID_PARAMS, "message": f"Only {model} is available"}
    return {"jsonrpc": "2.0", "id": message.get("id"), "error": error}


def add_model_option(message: dict[str, Any], model: str) -> dict[str, Any]:
    result = message.get("result")
    if isinstance(result, dict):
        options = [
            option
            for option in result.get("configOptions") or []
            if not (isinstance(option, dict) and option.get("id") == "model")
        ]
        result["configOptions"] = [*options, model_option(model)]
    return message


def parse(line: bytes) -> dict[str, Any] | None:
    try:
        message = json.loads(line)
    except ValueError:
        return None
    return message if isinstance(message, dict) else None


def encode(message: dict[str, Any]) -> bytes:
    return json.dumps(message, separators=(",", ":")).encode() + b"\n"


class Relay:
    def __init__(self, model: str, emit: Callable[[bytes], None]) -> None:
        self.model = model
        self.emit = emit
        self.new_sessions: set[object] = set()

    def from_client(self, line: bytes) -> bytes | None:
        """Return the line to forward to Hermes, or None after answering it."""
        message = parse(line)
        if message is None:
            return line
        reply = select_reply(message, self.model)
        if reply is not None:
            self.emit(encode(reply))
            return None
        if message.get("method") == "session/new":
            self.new_sessions.add(message.get("id"))
        return line

    def from_agent(self, line: bytes) -> bytes:
        message = parse(line)
        if message is None or "method" in message:
            return line
        request_id = message.get("id")
        if request_id not in self.new_sessions:
            return line
        self.new_sessions.discard(request_id)
        return encode(add_model_option(message, self.model))


async def pump_client(
    relay: Relay, client: asyncio.StreamReader, agent: asyncio.StreamWriter
) -> None:
    while line := await client.readline():
        forwarded = relay.from_client(line)
        if forwarded is not None:
            agent.write(forwarded)
            await agent.drain()
    agent.close()


async def pump_agent(relay: Relay, agent: asyncio.StreamReader) -> None:
    while line := await agent.readline():
        relay.emit(relay.from_agent(line))


async def relay(
    command: Sequence[str],
    env: dict[str, str],
    model: str,
    client: asyncio.StreamReader,
    emit: Callable[[bytes], None],
) -> int:
    """Run Hermes and relay its messages until it exits; return its exit code."""
    process = await asyncio.create_subprocess_exec(
        *command,
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        limit=LINE_LIMIT,
    )
    assert process.stdin is not None and process.stdout is not None
    session = Relay(model, emit)
    to_agent = asyncio.create_task(pump_client(session, client, process.stdin))
    await pump_agent(session, process.stdout)
    code = await process.wait()
    to_agent.cancel()
    return code


def write_stdout(data: bytes) -> None:
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


async def serve(command: Sequence[str], env: dict[str, str], model: str) -> int:
    """Relay between this process's standard streams and Hermes."""
    client = asyncio.StreamReader(limit=LINE_LIMIT)
    await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(client), sys.stdin
    )
    return await relay(command, env, model, client, write_stdout)
