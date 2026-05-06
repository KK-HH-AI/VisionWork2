import json
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from ..services.scanner import build_directory_tree
from ..services.analyzer import run_llm_analysis, should_stop
from ..services.simulator import run_simulated_analysis

active_connections = []


async def handle_websocket(websocket: WebSocket, valid_token: str):
    print(f"[WS] Incoming connection. valid_token={valid_token}")
    token = websocket.query_params.get("token")
    print(f"[WS] Token from client: {token}")
    if token != valid_token:
        print(f"[WS] Token mismatch! Closing connection.")
        await websocket.close(code=1008, reason="Invalid token")
        return

    await websocket.accept()
    print(f"[WS] Connection accepted")
    websocket.max_size = 10 * 1024 * 1024
    active_connections.append(websocket)

    analysis_task = None
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "scan_directory":
                folder_path = message.get("path")
                if not folder_path:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No path provided"
                    })
                    continue

                try:
                    tree = build_directory_tree(folder_path)
                    await websocket.send_json({
                        "type": "directory_tree",
                        "path": folder_path,
                        "tree": tree
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)
                    })

            elif message.get("type") == "simulate_analysis":
                folder_path = message.get("path")
                if not folder_path:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No path provided"
                    })
                    continue

                try:
                    await run_simulated_analysis(websocket, folder_path)
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)
                    })

            elif message.get("type") == "start_analysis":
                folder_path = message.get("path")
                profession = message.get("profession", "软件工程师")
                api_url = message.get("api_url", "")
                api_key = message.get("api_key", "")
                model_name = message.get("model_name", "gpt-3.5-turbo")
                stop_flag = message.get("stop_flag", "")

                if not folder_path:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No path provided"
                    })
                    continue

                if not api_url or not api_key:
                    await websocket.send_json({
                        "type": "error",
                        "message": "API URL and API Key are required"
                    })
                    continue

                print(f"[Backend] Starting analysis task with stop_flag: {stop_flag}")
                analysis_task = asyncio.create_task(
                    run_llm_analysis(
                        websocket, folder_path, profession,
                        api_url, api_key, model_name, stop_flag
                    )
                )

            elif message.get("type") == "stop_analysis":
                stop_flag = message.get("stop_flag", "")
                print(f"[Backend] Received stop_analysis request, stop_flag: {stop_flag}")
                if stop_flag:
                    should_stop[stop_flag] = True
                    print(f"[Backend] Set should_stop[{stop_flag}] = True")
                    print(f"[Backend] Current should_stop dict: {should_stop}")
                    await websocket.send_json({
                        "type": "stopped"
                    })
                else:
                    print(f"[Backend] ERROR: No stop_flag in stop_analysis request")
                    await websocket.send_json({
                        "type": "error",
                        "message": "No stop_flag provided"
                    })

            elif message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        if analysis_task and not analysis_task.done():
            analysis_task.cancel()
        if websocket in active_connections:
            active_connections.remove(websocket)
