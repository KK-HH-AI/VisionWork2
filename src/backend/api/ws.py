import json
import asyncio
import queue # 队列
import threading # 线程
from fastapi import WebSocket, WebSocketDisconnect

# 导入业务逻辑层
from ..services.scanner import build_directory_tree
from ..agent.graph import build_initial_agent_state, build_agent_graph

# 维护活跃的 WebSocket 连接
active_connections = []
# 存储每个分析任务的停止标识（key: stop_flag, value: 是否停止）
agent_stop_flags = {}
# 全局停止标志字典，key 为 stop_flag，value 为 bool
should_stop = {}


async def handle_websocket(websocket: WebSocket, valid_token: str):
    """
    【函数功能】
    WebSocket 连接总入口，负责鉴权、消息分发、连接管理

    【输入】
    websocket: FastAPI WebSocket 对象，负责和客户端双向通信
    valid_token: 服务启动时传入的合法 token，用于鉴权

    【输出】
    无返回值，通过 websocket.send_json() 向客户端发送消息

    【中间过程】
    1. 从客户端连接 URL 中获取 token 并校验
    2. 校验失败 → 关闭连接
    3. 校验成功 → 接受连接，加入活跃列表
    4. 进入循环，持续接收客户端 JSON 消息
    5. 根据消息 type 执行不同业务逻辑
    6. 客户端断开 → 清理任务与连接
    """
    print(f"[WS] Incoming connection. valid_token={valid_token}")

    # 从客户端连接参数获取 token
    token = websocket.query_params.get("token")
    print(f"[WS] Token from client: {token}")

    # ===================== 鉴权 =====================
    # 中间过程：对比客户端 token 和服务端合法 token
    if token != valid_token:
        print(f"[WS] Token mismatch! Closing connection.")
        await websocket.close(code=1008, reason="Invalid token")
        return

    # 中间过程：接受客户端 WebSocket 连接
    await websocket.accept()
    print(f"[WS] Connection accepted")

    # 限制最大消息大小 10MB
    websocket.max_size = 10 * 1024 * 1024

    # 加入全局活跃连接列表
    active_connections.append(websocket)

    # 本地缓存客户端配置（API 地址、密钥、模型名）
    stored_config = {
        "api_url": "",
        "api_key": "",
        "model_name": "qwen-plus",
    }

    # 当前正在运行的 AI 分析任务
    analysis_task = None

    # 当前任务的唯一停止标识
    current_agent_stop_flag = None

    # ===================== 循环处理消息 =====================
    try:
        # 中间过程：无限循环接收客户端消息
        while True:
            # 输入：从客户端接收文本消息
            data = await websocket.receive_text()
            # 中间过程：把 JSON 字符串转成字典
            message = json.loads(data)

            # ===================== 消息类型：扫描目录 =====================
            if message.get("type") == "scan_directory":
                # 输入：客户端传来的路径
                folder_path = message.get("path")

                if not folder_path:
                    await websocket.send_json({"type": "error", "message": "No path provided"})
                    continue

                try:
                    # 中间过程：调用扫描工具生成目录树
                    tree = build_directory_tree(folder_path)
                    # 输出：返回目录树给客户端
                    await websocket.send_json({
                        "type": "directory_tree",
                        "path": folder_path,
                        "tree": tree
                    })
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

            # ===================== 消息类型：启动 AI 分析 =====================
            elif message.get("type") == "start_analysis":
                # 输入：目录、API 配置、停止标志
                folder_path = message.get("path")
                api_url = message.get("api_url", "")
                api_key = message.get("api_key", "")
                model_name = message.get("model_name", "gpt-3.5-turbo")
                stop_flag = message.get("stop_flag", "")

                if not folder_path:
                    await websocket.send_json({"type": "error", "message": "No path provided"})
                    continue
                if not api_url or not api_key:
                    await websocket.send_json({"type": "error", "message": "API URL and API Key are required"})
                    continue

                # 取消上一个还在跑的任务
                if analysis_task and not analysis_task.done():
                    print("[ws.py] 取消上一个分析任务")
                    analysis_task.cancel()
                    if current_agent_stop_flag:
                        agent_stop_flags[current_agent_stop_flag] = True

                # 生成唯一任务id，客户端要停止这个任务就，要靠这个id
                import uuid
                current_agent_stop_flag = stop_flag if stop_flag else str(uuid.uuid4())[:8]
                agent_stop_flags[current_agent_stop_flag] = False

                # 中间过程：创建异步任务执行 AI 分析
                analysis_task = asyncio.create_task(
                    _run_agent_loop(
                        websocket=websocket,
                        user_message=f"请分析文件夹: {folder_path}",
                        project_path=folder_path,
                        api_url=api_url,
                        api_key=api_key,
                        model_name=model_name,
                        stop_flag=current_agent_stop_flag,
                    )
                )

            # ===================== 消息类型：停止分析 =====================
            elif message.get("type") == "stop_analysis":
                # 输入：要停止的任务标志
                stop_flag = message.get("stop_flag", "")
                if stop_flag:
                    # 中间过程：设置停止标志
                    should_stop[stop_flag] = True
                    agent_stop_flags[stop_flag] = True
                    await websocket.send_json({"type": "stopped"})
                else:
                    await websocket.send_json({"type": "error", "message": "No stop_flag provided"})

            # ===================== 消息类型：保存配置 =====================
            elif message.get("type") == "set_config":
                # 输入：客户端的 API 配置
                stored_config["api_url"] = message.get("api_url", stored_config["api_url"])
                stored_config["api_key"] = message.get("api_key", stored_config["api_key"])
                stored_config["model_name"] = message.get("model_name", stored_config["model_name"])
                await websocket.send_json({"type": "config_saved"})

            # ===================== 消息类型：停止当前 AI 任务 =====================
            elif message.get("type") == "stop_agent":
                if current_agent_stop_flag:
                    # 中间过程：设置当前任务停止标志
                    agent_stop_flags[current_agent_stop_flag] = True
                    await websocket.send_json({"type": "agent_stopped"})
                else:
                    await websocket.send_json({"type": "error", "message": "No active agent to stop"})

            # ===================== 消息类型：快捷扫描 =====================
            elif message.get("type") == "scan_request":
                folder_path = message.get("path", "")
                if not folder_path:
                    await websocket.send_json({"type": "error", "message": "No path provided"})
                    continue

                # 输入：优先使用消息中的配置，否则用缓存配置
                api_url = message.get("api_url") or stored_config["api_url"]
                api_key = message.get("api_key") or stored_config["api_key"]
                model_name = message.get("model_name") or stored_config["model_name"]

                if not api_url or not api_key:
                    await websocket.send_json({"type": "error", "message": "Please configure API first"})
                    continue

                import uuid
                current_agent_stop_flag = str(uuid.uuid4())[:8]
                agent_stop_flags[current_agent_stop_flag] = False

                # 中间过程：启动分析任务
                analysis_task = asyncio.create_task(
                    _run_agent_loop(
                        websocket=websocket,
                        user_message=f"请分析文件夹: {folder_path}",
                        project_path=folder_path,
                        api_url=api_url,
                        api_key=api_key,
                        model_name=model_name,
                        stop_flag=current_agent_stop_flag,
                    )
                )

            # ===================== 消息类型：聊天消息 =====================
            elif message.get("type") == "chat_message":
                # 输入：聊天内容、项目路径、画布信息、API 配置
                content = message.get("content", "")
                folder_path = message.get("path", "")
                canvas_context = message.get("canvas_context", "")
                canvas_nodes = message.get("canvas_nodes", [])
                canvas_edges = message.get("canvas_edges", [])
                api_url = message.get("api_url") or stored_config["api_url"]
                api_key = message.get("api_key") or stored_config["api_key"]
                model_name = message.get("model_name") or stored_config["model_name"]

                # 取消上一个还在跑的任务，避免旧任务的事件覆盖新任务的检索路径
                if analysis_task and not analysis_task.done():
                    print("[ws.py] 取消上一个分析任务")
                    analysis_task.cancel()
                    # 标记旧任务为已停止
                    if current_agent_stop_flag:
                        agent_stop_flags[current_agent_stop_flag] = True

                if api_url and api_key:
                    import uuid
                    current_agent_stop_flag = str(uuid.uuid4())[:8]
                    agent_stop_flags[current_agent_stop_flag] = False

                    # 中间过程：启动聊天 AI 任务
                    analysis_task = asyncio.create_task(
                        _run_agent_loop(
                            websocket=websocket,
                            user_message=content,
                            project_path=folder_path,
                            api_url=api_url,
                            api_key=api_key,
                            model_name=model_name,
                            stop_flag=current_agent_stop_flag,
                            canvas_context=canvas_context,
                            canvas_nodes=canvas_nodes,
                            canvas_edges=canvas_edges,
                        )
                    )
                else:
                    await websocket.send_json({
                        "type": "chat_response",
                        "message": f"You said: {content}\nPlease configure API first."
                    })

            # ===================== 心跳包 =====================
            elif message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    # 客户端断开连接
    except WebSocketDisconnect:
        # 中间过程：清理任务
        if analysis_task and not analysis_task.done():
            analysis_task.cancel()
        # 中间过程：标记任务停止
        if current_agent_stop_flag:
            agent_stop_flags[current_agent_stop_flag] = True
        # 中间过程：从活跃列表移除
        if websocket in active_connections:
            active_connections.remove(websocket)

async def _run_agent_loop(
    websocket: WebSocket,
    user_message: str,
    project_path: str,
    api_url: str,
    api_key: str,
    model_name: str,
    stop_flag: str,
    canvas_context: str = "",
    canvas_nodes: list = None,
    canvas_edges: list = None,
):
    """
    【函数功能】
    AI 智能体核心执行函数，运行工作流、推送实时结果到客户端

    【输入】
    websocket: 通信对象
    user_message: 用户输入的指令（决定流程图绘制方向）
    project_path: 项目路径
    api_url: AI 接口地址
    api_key: AI 密钥
    model_name: 模型名称
    stop_flag: 任务唯一停止标志
    canvas_context: 画布上下文（前端流程图）
    canvas_nodes: 流程图节点
    canvas_edges: 流程图连线

    【输出】
    无返回值，通过 event_queue → websocket 发送实时消息给客户端

    【中间过程】
    1. 创建线程安全队列，用于子线程和主线程通信
    2. 构建 AI 初始状态
    3. 构建 AI 执行流程图（graph）
    4. 启动子线程执行同步的 graph.run()
    5. 主线程循环从队列取消息 → 发送给客户端
    6. 任务结束/异常 → 清理停止标志
    """
    # 中间过程：创建线程安全队列，用于子线程推送消息
    event_queue = queue.Queue()

    # 中间过程：构建 AI 初始状态
    initial_state = build_initial_agent_state(
        user_message=user_message,
        project_path=project_path,
        api_url=api_url,
        api_key=api_key,
        model_name=model_name,
        event_queue=event_queue,
        canvas_context=canvas_context,
        canvas_nodes=canvas_nodes or [],
        canvas_edges=canvas_edges or [],
    )

    # 中间过程：构建 AI 执行流程图
    graph = build_agent_graph()

    def run_graph():# 这里是同步的，阻塞的
        """
        【内部函数功能】
        在子线程中同步运行 AI 工作流（防止阻塞 WebSocket）

        【中间过程】
        1. 循环执行 AI 流程图
        2. 检查停止标志
        3. 产生结果 → 放入队列
        4. 异常 → 放入错误消息
        """
        try:
            # 初始化当前状态，从初始状态深拷贝一份
            current_state = dict(initial_state)

            while True:
                # 检查是否需要停止
                if agent_stop_flags.get(stop_flag, False):
                    current_state["should_stop"] = True
                    event_queue.put({"type": "chat_response", "message": "Analysis stopped by user."})
                    break

                # 流式执行 AI 流程图
                for chunk in graph.stream(current_state):
                    node_name = list(chunk.keys())[0]
                    current_state = dict(chunk[node_name])

                    if agent_stop_flags.get(stop_flag, False):
                        current_state["should_stop"] = True
                        event_queue.put({"type": "chat_response", "message": "Analysis stopped by user."})
                        break

                # 任务完成或停止 → 退出
                if current_state.get("should_stop") or current_state.get("plan_complete", False):
                    break

        except Exception as e:
            # 异常放入队列，通知前端
            event_queue.put({"type": "error", "message": str(e)})

    # 中间过程：启动子线程运行 AI 流程图（daemon=True 主线程退出则自动销毁）
    graph_thread = threading.Thread(target=run_graph, daemon=True)
    graph_thread.start()

    try:
        # 中间过程：循环从队列取消息，实时推送给客户端
        while True:
            try:
                msg = event_queue.get_nowait()
            except queue.Empty:
                # 队列为空，检查线程是否结束
                if not graph_thread.is_alive():
                    # 线程已退出，但可能还有残留事件，再尝试取一次
                    try:
                        msg = event_queue.get_nowait()
                    except queue.Empty:
                        break  # 确实没事件了，退出
                else:
                    await asyncio.sleep(0.05)
                    continue

            # 输出：把队列消息发给客户端
            msg_type = msg.get("type")
            if msg_type == "error":
                await websocket.send_json(msg)
                break
            try:
                await websocket.send_json(msg)
            except RuntimeError:
                break

    except asyncio.CancelledError:
        # 任务被取消，静默退出，不发送额外事件
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except RuntimeError:
            pass

    finally:
        # 中间过程：任务结束，清理停止标志
        if stop_flag in agent_stop_flags:
            del agent_stop_flags[stop_flag]