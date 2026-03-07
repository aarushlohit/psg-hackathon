"""CLARA server — FastAPI application with WebSocket endpoint.

Run standalone:
    python -m devhub.modules.clara.server.app [--host 0.0.0.0] [--port 9100]
"""

import argparse
import asyncio
import json
import logging
import sys

logger = logging.getLogger(__name__)


def _build_app():
    """Build and return the FastAPI application (import FastAPI lazily)."""
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import JSONResponse

    from devhub.modules.clara.database import ClaraDatabase
    from devhub.modules.clara.protocol import Action, Packet
    from devhub.modules.clara.server.hub import ClaraHub

    app = FastAPI(title="CLARA Server", version="2.0.0")
    db = ClaraDatabase()
    db.connect()
    hub = ClaraHub(db)

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

    return app


def run_server(host: str = "0.0.0.0", port: int = 9100) -> None:
    """Blocking entry point — start the CLARA server with uvicorn."""
    import uvicorn

    app = _build_app()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Starting CLARA server on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info", ws="wsproto")


async def run_server_async(host: str = "0.0.0.0", port: int = 9100) -> None:
    """Non-blocking entry point for embedding in a thread."""
    import uvicorn

    app = _build_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", ws="wsproto")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CLARA Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9100)
    args = parser.parse_args()
    run_server(args.host, args.port)
