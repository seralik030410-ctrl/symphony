"""Frozen FastAPI entry point. Readiness/shutdown use the private parent pipe."""
import asyncio
import json
import os
import socket
import sys
import threading

import uvicorn

PROTOCOL = 1
MAX_CONTROL_BYTES = 20_000


def read_bootstrap(stream) -> dict:
    line = stream.readline(MAX_CONTROL_BYTES + 1)
    try:
        if len(line) > MAX_CONTROL_BYTES or not line.endswith(b"\n"):
            raise ValueError
        value = json.loads(line)
        if not isinstance(value, dict) or value.get("protocol") != PROTOCOL:
            raise ValueError
        if set(value) != {"protocol", "openai_api_key"}:
            raise ValueError
        key = value["openai_api_key"]
        if not isinstance(key, str) or len(key) > 4096:
            raise ValueError
        return value
    except (ValueError, TypeError, UnicodeError):
        # Never echo a malformed payload: it can contain a secret.
        raise ValueError("Invalid desktop bootstrap protocol") from None


class DesktopServer(uvicorn.Server):
    async def startup(self, sockets=None):
        await super().startup(sockets=sockets)
        if self.started and not self.should_exit:
            ports = {socket.getsockname()[1] for server in self.servers for socket in server.sockets}
            print(json.dumps({"event": "symphony.ready", "protocol": PROTOCOL, "port": next(iter(ports))}), flush=True)


def watch_parent(stream, server, loop):
    while True:
        line = stream.readline(MAX_CONTROL_BYTES + 1)
        # A closed pipe means the parent crashed. Stop the server as well.
        if not line or line == b'{"command":"shutdown"}\n' or len(line) > MAX_CONTROL_BYTES:
            loop.call_soon_threadsafe(setattr, server, "should_exit", True)
            return


def main() -> None:
    bootstrap = read_bootstrap(sys.stdin.buffer)
    os.environ["SYMPHONY_DESKTOP"] = "1"
    os.environ.pop("SYMPHONY_OPENAI_API_KEY", None)
    from backend.config import Settings

    settings = Settings.from_env()
    settings.host = "127.0.0.1"
    settings.openai_api_key = bootstrap.pop("openai_api_key")
    # Bind before opening/migrating a database. A second instance must neither
    # navigate to a foreign server nor interrupt the first instance's turns.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform == "win32":
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    listener.bind((settings.host, settings.port))
    listener.listen(128)
    listener.setblocking(False)
    from backend.main import create_app

    server = DesktopServer(uvicorn.Config(create_app(settings), host=settings.host, port=settings.port,
                                        access_log=False, log_level="warning", timeout_graceful_shutdown=10))

    async def serve():
        watcher = threading.Thread(target=watch_parent, args=(sys.stdin.buffer, server, asyncio.get_running_loop()), daemon=True)
        watcher.start()
        await server.serve(sockets=[listener])

    try:
        asyncio.run(serve())
    finally:
        listener.close()


if __name__ == "__main__":
    main()
