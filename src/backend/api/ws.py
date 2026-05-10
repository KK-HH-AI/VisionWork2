import json
import asyncio
import re
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from ..services.scanner import build_directory_tree
from ..services.analyzer import run_llm_analysis, should_stop
from ..services.simulator import run_simulated_analysis
from ..agent.graph import build_initial_state, process_user_input
from ..tools.registry import tool_registry

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

            elif message.get("type") == "scan_request":
                folder_path = message.get("path", "")
                if not folder_path:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No path provided for scan_request"
                    })
                    continue

                async def _send_func(msg):
                    await websocket.send_json(msg)

                state = build_initial_state(
                    user_message=f"请分析文件夹：{folder_path}",
                    folder_path=folder_path,
                )
                result_state = await process_user_input(state, send_func=_send_func)

                await websocket.send_json({
                    "type": "chat_response",
                    "message": result_state["response_message"],
                })

                if result_state.get("scan_result"):
                    try:
                        tree = json.loads(result_state["scan_result"])
                        await websocket.send_json({
                            "type": "directory_tree",
                            "path": folder_path,
                            "tree": tree,
                        })
                    except json.JSONDecodeError:
                        pass

            elif message.get("type") == "chat_message":
                content = message.get("content", "")

                scan_pattern = re.compile(r"(?:请分析|扫描|scan|分析)\s*(?:文件夹)?[：:\s]*(.+)", re.IGNORECASE)
                is_scan_msg = bool(scan_pattern.search(content))

                if is_scan_msg:
                    async def _send_func(msg):
                        await websocket.send_json(msg)

                    state = build_initial_state(user_message=content)
                    result_state = await process_user_input(state, send_func=_send_func)

                    await websocket.send_json({
                        "type": "chat_response",
                        "message": result_state["response_message"],
                    })

                    if result_state.get("scan_result"):
                        try:
                            tree = json.loads(result_state["scan_result"])
                            await websocket.send_json({
                                "type": "directory_tree",
                                "path": result_state.get("folder_path", ""),
                                "tree": tree,
                            })
                        except json.JSONDecodeError:
                            pass
                else:
                    await websocket.send_json({
                        "type": "chat_response",
                        "message": f"您好！我是您的代码分析助手。您说：{content}"
                    })

                    import asyncio as _asyncio
                    await _asyncio.sleep(0.5)

                    canvas_commands = [
                        {"cmd": "add_node", "id": "node-main", "label": "入口模块", "type": "module", "group": "python"},
                        {"cmd": "add_node", "id": "node-core", "label": "核心引擎", "type": "module", "group": "python"},
                        {"cmd": "add_node", "id": "node-utils", "label": "工具函数", "type": "function", "group": "python"},
                        {"cmd": "add_edge", "source": "node-main", "target": "node-core", "label": "调用"},
                        {"cmd": "add_edge", "source": "node-core", "target": "node-utils", "label": "依赖"},
                        {"cmd": "layout"},
                    ]

                    for cmd in canvas_commands:
                        await websocket.send_json({
                            "type": "canvas_command",
                            "command": cmd,
                        })
                        await _asyncio.sleep(0.3)

            elif message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        if analysis_task and not analysis_task.done():
            analysis_task.cancel()
        if websocket in active_connections:
            active_connections.remove(websocket)
