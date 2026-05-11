import json
import asyncio
import queue
import threading
import re
from fastapi import WebSocket, WebSocketDisconnect
from ..services.scanner import build_directory_tree
from ..services.analyzer import should_stop
from ..services.simulator import run_simulated_analysis
from ..agent.graph import build_initial_agent_state, build_agent_graph

active_connections = []

agent_stop_flags = {}


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

    stored_config = {
        "api_url": "",
        "api_key": "",
        "model_name": "gpt-3.5-turbo",
        "profession": "Software Engineer",
    }

    analysis_task = None
    current_agent_stop_flag = None

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
                profession = message.get("profession", "Software Engineer")
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

                print(f"[Backend] Starting agent analysis with stop_flag: {stop_flag}")
                import uuid
                current_agent_stop_flag = stop_flag if stop_flag else str(uuid.uuid4())[:8]
                agent_stop_flags[current_agent_stop_flag] = False

                analysis_task = asyncio.create_task(
                    _run_agent_loop(
                        websocket,
                        user_message=f"Please analyze the folder: {folder_path}",
                        project_path=folder_path,
                        api_url=api_url,
                        api_key=api_key,
                        model_name=model_name,
                        profession=profession,
                        stop_flag=current_agent_stop_flag,
                    )
                )

            elif message.get("type") == "stop_analysis":
                stop_flag = message.get("stop_flag", "")
                print(f"[Backend] Received stop_analysis request, stop_flag: {stop_flag}")
                if stop_flag:
                    should_stop[stop_flag] = True
                    agent_stop_flags[stop_flag] = True
                    print(f"[Backend] Set stop flags for: {stop_flag}")
                    await websocket.send_json({
                        "type": "stopped"
                    })
                else:
                    print(f"[Backend] ERROR: No stop_flag in stop_analysis request")
                    await websocket.send_json({
                        "type": "error",
                        "message": "No stop_flag provided"
                    })

            elif message.get("type") == "set_config":
                stored_config["api_url"] = message.get("api_url", stored_config["api_url"])
                stored_config["api_key"] = message.get("api_key", stored_config["api_key"])
                stored_config["model_name"] = message.get("model_name", stored_config["model_name"])
                stored_config["profession"] = message.get("profession", stored_config["profession"])
                print(f"[Backend] Config updated: model={stored_config['model_name']}, profession={stored_config['profession']}")
                await websocket.send_json({
                    "type": "config_saved"
                })

            elif message.get("type") == "stop_agent":
                if current_agent_stop_flag:
                    agent_stop_flags[current_agent_stop_flag] = True
                    print(f"[Backend] Agent stop flag set: {current_agent_stop_flag}")
                    await websocket.send_json({
                        "type": "agent_stopped"
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No active agent to stop"
                    })

            elif message.get("type") == "scan_request":
                folder_path = message.get("path", "")
                if not folder_path:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No path provided for scan_request"
                    })
                    continue

                api_url = message.get("api_url") or stored_config["api_url"]
                api_key = message.get("api_key") or stored_config["api_key"]
                model_name = message.get("model_name") or stored_config["model_name"]
                profession = message.get("profession") or stored_config["profession"]

                if not api_url or not api_key:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Please configure API URL and API Key first"
                    })
                    continue

                import uuid
                current_agent_stop_flag = str(uuid.uuid4())[:8]
                agent_stop_flags[current_agent_stop_flag] = False

                analysis_task = asyncio.create_task(
                    _run_agent_loop(
                        websocket,
                        user_message=f"Please analyze the folder: {folder_path}",
                        project_path=folder_path,
                        api_url=api_url,
                        api_key=api_key,
                        model_name=model_name,
                        profession=profession,
                        stop_flag=current_agent_stop_flag,
                    )
                )

            elif message.get("type") == "chat_message":
                content = message.get("content", "")

                api_url = message.get("api_url") or stored_config["api_url"]
                api_key = message.get("api_key") or stored_config["api_key"]
                model_name = message.get("model_name") or stored_config["model_name"]
                profession = message.get("profession") or stored_config["profession"]

                scan_pattern = re.compile(r"(?:please analyze|analyze|scan|analysis|分析|扫描)\s*(?:folder\s*)?[：:\s]*(.+)", re.IGNORECASE)
                is_scan_msg = bool(scan_pattern.search(content))

                if is_scan_msg and api_url and api_key:
                    match = scan_pattern.search(content)
                    folder_path = match.group(1).strip().strip('"').strip("'") if match else ""

                    import uuid
                    current_agent_stop_flag = str(uuid.uuid4())[:8]
                    agent_stop_flags[current_agent_stop_flag] = False

                    analysis_task = asyncio.create_task(
                        _run_agent_loop(
                            websocket,
                            user_message=content,
                            project_path=folder_path,
                            api_url=api_url,
                            api_key=api_key,
                            model_name=model_name,
                            profession=profession,
                            stop_flag=current_agent_stop_flag,
                        )
                    )
                elif api_url and api_key:
                    import uuid
                    current_agent_stop_flag = str(uuid.uuid4())[:8]
                    agent_stop_flags[current_agent_stop_flag] = False

                    analysis_task = asyncio.create_task(
                        _run_agent_loop(
                            websocket,
                            user_message=content,
                            project_path="",
                            api_url=api_url,
                            api_key=api_key,
                            model_name=model_name,
                            profession=profession,
                            stop_flag=current_agent_stop_flag,
                        )
                    )
                else:
                    await websocket.send_json({
                        "type": "chat_response",
                        "message": f"Hello! I'm your code analysis assistant. You said: {content}\n\nPlease configure API URL and API Key in settings to enable AI-powered analysis."
                    })

            elif message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        if analysis_task and not analysis_task.done():
            analysis_task.cancel()
        if current_agent_stop_flag:
            agent_stop_flags[current_agent_stop_flag] = True
        if websocket in active_connections:
            active_connections.remove(websocket)


async def _run_agent_loop(
    websocket: WebSocket,
    user_message: str,
    project_path: str,
    api_url: str,
    api_key: str,
    model_name: str,
    profession: str,
    stop_flag: str,
):
    event_queue = queue.Queue()

    initial_state = build_initial_agent_state(
        user_message=user_message,
        project_path=project_path,
        api_url=api_url,
        api_key=api_key,
        model_name=model_name,
        profession=profession,
        event_queue=event_queue,
    )

    graph = build_agent_graph()

    def run_graph():
        try:
            current_state = dict(initial_state)
            while True:
                if agent_stop_flags.get(stop_flag, False):
                    current_state["should_stop"] = True
                    event_queue.put({"type": "chat_response", "message": "Analysis stopped by user."})
                    break

                result = graph.invoke(current_state)
                current_state = dict(result)

                if current_state.get("should_stop"):
                    break
                if current_state.get("plan_complete", False):
                    break
        except Exception as e:
            event_queue.put({"type": "error", "message": str(e)})

    graph_thread = threading.Thread(target=run_graph, daemon=True)
    graph_thread.start()

    try:
        while True:
            try:
                msg = event_queue.get_nowait()
            except queue.Empty:
                if not graph_thread.is_alive():
                    try:
                        msg = event_queue.get_nowait()
                    except queue.Empty:
                        break
                await asyncio.sleep(0.05)
                continue

            msg_type = msg.get("type")

            if msg_type == "error":
                try:
                    await websocket.send_json(msg)
                except RuntimeError:
                    pass
                break

            try:
                await websocket.send_json(msg)
            except RuntimeError:
                break
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except RuntimeError:
            pass
    finally:
        if stop_flag in agent_stop_flags:
            del agent_stop_flags[stop_flag]