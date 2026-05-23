import sys
import os
import argparse

# 把项目根目录（src/）加入 Python 搜索路径，必须在 import backend 之前
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入 FastAPI 核心框架 + WebSocket 支持
import uvicorn
from fastapi import FastAPI, WebSocket

# 导入跨域中间件，解决前端访问后端的跨域问题
from fastapi.middleware.cors import CORSMiddleware

# 导入业务模块路由：文件、记忆、技能三个功能模块
from backend.api.files import router as files_router
from backend.api.memory import router as memory_router
from backend.api.skills import router as skills_router
from backend.api.ws import handle_websocket # WebSocket 真正的处理逻辑函数

# 创建 FastAPI 应用实例
app = FastAPI()

# 全局变量，用于存储启动时传入的认证token，前端请求时需要携带该token
valid_token = None

# ===================== WebSocket 接口 =====================
# 注册 WebSocket 接口，访问路径：/ws
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    print(f"[WS] Endpoint called. valid_token={valid_token}")
    await handle_websocket(websocket, valid_token)

# ===================== 跨域配置 =====================
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r'https?://(localhost|127\.0\.0\.1)(:\d+)?',  # 仅允许本地连接，支持任意端口
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================== 挂载业务接口 =====================
# 把文件相关的接口注册到主应用
app.include_router(files_router)
# 把记忆相关的接口注册到主应用
app.include_router(memory_router)
# 把技能相关的接口注册到主应用
app.include_router(skills_router)

# ===================== 服务启动入口 =====================
def main():
    # 声明使用全局变量 valid_token
    global valid_token
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser()
    # 必须传入 --port：服务启动的端口号
    parser.add_argument("--port", type=int, required=True)
    # 必须传入 --token：WebSocket 认证用的令牌
    parser.add_argument("--token", type=str, required=True)
    # 解析命令行输入的参数
    args = parser.parse_args()

    valid_token = args.token
    print(f"Backend starting on port {args.port}", flush=True)

    # 启动 Uvicorn 服务器，运行 FastAPI 服务
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
 

if __name__ == "__main__":
    main()
