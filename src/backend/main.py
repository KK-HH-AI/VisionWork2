import sys
import os
import argparse
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api.files import router as files_router
from backend.api.memory import router as memory_router
from backend.api.skills import router as skills_router
from backend.api.ws import handle_websocket

app = FastAPI()

valid_token = None


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    print(f"[WS] Endpoint called. valid_token={valid_token}")
    await handle_websocket(websocket, valid_token)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(files_router)
app.include_router(memory_router)
app.include_router(skills_router)


def main():
    global valid_token
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", type=str, required=True)
    args = parser.parse_args()

    valid_token = args.token
    print(f"Backend starting on port {args.port}", flush=True)

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
