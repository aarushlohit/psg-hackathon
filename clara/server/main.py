"""CLARA server — FastAPI application with WebSocket endpoint.

NOTE: Do NOT add ``from __future__ import annotations`` here. It breaks
FastAPI WebSocket parameter injection, causing 403 errors.

Run standalone:  python -m clara.server.main [--host 0.0.0.0] [--port 9100]
"""

import argparse
import json
import logging
import sys

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from clara.config.logging import setup_logging
from clara.config.settings import settings
from clara.database.db import ClaraDB
from clara.server.protocol import Packet
from clara.server.websocket import ClaraHub

logger = logging.getLogger("clara.connections")


def build_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(title="CLARA Server", version="2.0.0")
    db = ClaraDB()
    db.connect()
    hub = ClaraHub(db)
    hub.start()

    @app.get("/status")
    async def status():
        return JSONResponse({
            "server": "CLARA",
            "version": "2.0.0",
            "clients": len(hub.clients),
            "status": "running",
        })

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        client = await hub.on_connect(ws)
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    pkt = Packet.from_json(raw)
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    await ws.send_text(Packet.error(f"Bad packet: {exc}").to_json())
                    continue
                await hub.handle_packet(client, pkt)
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.exception("WebSocket error: %s", exc)
        finally:
            await hub.on_disconnect(client)

    @app.on_event("shutdown")
    async def shutdown():
        hub.stop()

    # Store hub on app for test access
    app.state.hub = hub
    app.state.db = db
    return app


def run_server(host: str = "0.0.0.0", port: int = 9100) -> None:
    """Blocking entry point — start the CLARA server with uvicorn."""
    import uvicorn

    setup_logging()
    app = build_app()
    logger.info("Starting CLARA server on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info", ws="wsproto")


async def run_server_async(host: str = "0.0.0.0", port: int = 9100) -> None:
    """Non-blocking entry point (for embedding / tests)."""
    import uvicorn

    setup_logging()
    app = build_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", ws="wsproto")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CLARA Server")
    parser.add_argument("--host", default=settings.server.host)
    parser.add_argument("--port", type=int, default=settings.server.port)
    args = parser.parse_args()
    run_server(args.host, args.port)
