# VisionWork2

AI 驱动的代码/文件分析与流程图可视化工具。基于 LLM 智能体架构，自动解读项目文件并生成结构化流程图，帮助开发者快速理解复杂项目。

## 功能特性

### 核心能力
- **智能文件分析**：两阶段工作流——先信息收集（目录扫描、文件读取、模块分析），再批量生成流程图
- **流程图可视化**：基于 ReactFlow 的交互式画布，支持节点拖拽、缩放、编辑、自动布局
- **记忆图谱**：D3.js 力导向图展示所有已分析文件，支持检索路径高亮
- **实时聊天**：通过 WebSocket 与 AI 智能体对话，流式推送思考过程和执行结果
- **多会话管理**：独立的分析会话，支持创建、切换、历史恢复

### 画布操作
- 拖拽框选多个节点，批量删除
- 节点/连线双击编辑（标签、类型、颜色、富文本内容）
- 画布自动布局（dagre 布局引擎）
- 导出/导入 JSON 流程图
- 导出 PNG/JPG 图片
- 全屏模式

### 记忆系统
- 自动为分析过的文件生成 Markdown 笔记（存储到工作空间 memory 目录）
- 纯文本搜索记忆笔记（不依赖向量数据库）
- 笔记内容在线编辑
- 记忆图谱实时更新检索路径

### 技能系统
- 8 个内置工具（扫描目录、读取文件、分析模块、生成画布、绘制关系、搜索记忆、读取画布、最终回答）
- YAML 技能定义 + Python 工具实现分离
- skills_config.json 启用/禁用工具
- Skill 管理面板

## 技术架构

```
VisionWork2
├── electron/                    # Electron 桌面应用壳
│   ├── main.ts                  # 主进程：管理窗口、启动 Python 后端
│   └── preload.ts               # 预加载脚本
├── src/
│   ├── backend/                 # Python FastAPI 后端
│   │   ├── agent/               # LangGraph 智能体工作流
│   │   │   └── graph.py         # AgentState、plan/execute/observe 节点
│   │   ├── api/                 # REST + WebSocket 接口
│   │   │   ├── ws.py            # WebSocket 通信核心
│   │   │   ├── files.py         # 文件/目录扫描接口
│   │   │   ├── memory.py        # 记忆笔记接口
│   │   │   └── skills.py        # 技能配置接口
│   │   ├── core/                # 核心配置
│   │   │   ├── config.py        # 工作空间路径配置
│   │   │   └── prompts.py       # LLM 提示词模板
│   │   ├── tools/               # 工具实现（可调用技能）
│   │   │   ├── registry.py      # 工具注册中心（单例）
│   │   │   ├── scan.py          # 目录扫描
│   │   │   ├── read_file.py     # 文件读取
│   │   │   ├── analyze_module.py # 模块分析 + 记忆存储
│   │   │   ├── generate_canvas.py # 批量画布生成
│   │   │   ├── draw_relation.py  # 手动绘制关系
│   │   │   ├── search_memory.py  # 记忆搜索
│   │   │   ├── canvas_read.py    # 画布状态读取
│   │   │   ├── final_answer.py   # 最终答案输出
│   │   │   └── base.py          # 工具基类
│   │   ├── skills/              # 技能 YAML 定义
│   │   ├── services/            # 基础服务
│   │   ├── utils/               # 工具函数
│   │   └── main.py              # FastAPI 入口
│   └── frontend/                # React + TypeScript 前端
│       ├── components/          # UI 组件
│       │   ├── ChatView.tsx      # 聊天视图（Markdown 渲染）
│       │   ├── ReactFlowCanvas.tsx # 流程图画布
│       │   ├── MemoryGraph.tsx    # 记忆图谱（D3.js）
│       │   ├── DirectoryTree.tsx  # 目录树
│       │   ├── RightPanel.tsx     # 右侧面板
│       │   ├── SessionSidebar.tsx  # 会话管理
│       │   ├── SkillManager.tsx   # 技能管理
│       │   ├── ConfigPanel.tsx    # 配置面板
│       │   ├── CodeViewPanel.tsx  # 代码/笔记查看器
│       │   ├── MemoryFileModal.tsx # 记忆文件编辑
│       │   └── ProgressBar.tsx    # 进度条
│       ├── hooks/               # React Hooks
│       │   └── useWebSocket.ts   # WebSocket 连接管理
│       ├── utils/               # 工具函数
│       │   ├── constants.ts      # 颜色常量
│       │   ├── fileIcons.ts      # 文件图标映射
│       │   └── sessionStore.ts   # 会话持久化存储
│       ├── App.tsx               # 主应用组件
│       ├── styles.css            # 全局样式
│       └── types.ts              # TypeScript 类型定义
└── package.json                 # Node.js 依赖配置
```

## 快速开始

### 环境要求

- **Node.js** >= 18
- **Python** >= 3.10
- LLM API 服务（兼容 OpenAI API 格式，如 Qwen、DeepSeek 等）

### 安装

```bash
# 1. 克隆项目
git clone <repo-url>
cd VisionWork2

# 2. 安装前端依赖
npm install

# 3. 安装 Python 后端依赖
pip install -r requirements.txt
```

### 启动

**方式一：Electron 桌面应用（推荐）**

```bash
npm run electron:dev
```

Electron 会自动：
1. 编译 TypeScript 主进程代码
2. 启动 Vite 开发服务器（端口 5173）
3. 查找可用端口，启动 Python FastAPI 后端
4. 打开 Electron 窗口

**方式二：分别启动前后端**

```bash
# 终端 1：启动 Python 后端
python src/backend/main.py --port 8000 --token your-secret-token

# 终端 2：启动 Vite 开发服务器
npm run dev
```

然后在浏览器访问 `http://localhost:5173`。

### 使用流程

1. 启动应用后，点击左上角 **设置** 图标配置 LLM API 地址、密钥和模型名称
2. 点击 **+** 新建分析会话
3. 在左侧目录树中选择目标文件夹，点击扫描按钮
4. 在聊天框输入分析指令（如"分析这个项目结构"、"画出登录模块的流程图"）
5. AI 智能体自动扫描文件、生成分析笔记，最后在画布上绘制流程图
6. 可在画布上手动编辑节点、连线，导出 PNG/JPG/JSON

## AI 智能体工作流

```
用户指令 → plan_node（制定执行计划）
         → execute_node（逐步执行工具）
         → observe_node（反思评估）
         → 继续执行 / 输出最终报告
```

- **plan_node**：LLM 将用户指令分解为多个工具执行步骤
- **execute_node**：按计划依次调用工具（scan_directory → read_file → analyze_module → generate_canvas → final_answer）
- **observe_node**：评估执行结果，判断是否需要额外步骤

## 可用工具（技能）

| 工具 | 描述 |
|------|------|
| `scan_directory` | 扫描目录结构，返回文件列表 |
| `read_file` | 读取文件内容 |
| `analyze_module` | 分析文件并生成记忆笔记（Markdown） |
| `generate_canvas` | 批量生成流程图节点和连线 |
| `draw_relation` | 手动绘制节点间关系 |
| `search_memory` | 搜索已生成的记忆笔记 |
| `canvas_read` | 读取当前画布状态 |
| `final_answer` | 输出最终分析报告 |

## 配色说明

三栏面板使用彩色顶部横条区分：
- 左侧（聊天）：蓝色 `#4B8BBE`
- 中间（画布）：绿色 `#4CAF50`
- 右侧（记忆图谱）：紫色 `#8B5CF6`

记忆图谱节点使用语义化颜色：
- Python `#4B8BBE` | JavaScript `#F0DB4F` | TypeScript `#3178C6`
- Java `#ED8B00` | Web `#E34F26` | Data `#4CAF50`
- Config `#8B5CF6` | Doc `#06B6D4` | 其他 `#94A3B8`

## 技术栈

| 层级 | 技术 |
|------|------|
| 桌面壳 | Electron |
| 前端框架 | React 18 + TypeScript |
| 流程图 | ReactFlow + dagre |
| 图谱 | D3.js 力导向图 |
| 后端框架 | FastAPI |
| AI 编排 | LangGraph |
| LLM 接口 | langchain-openai（兼容 OpenAI API） |
| 代码编辑器 | Monaco Editor |
| 样式 | CSS Variables（深色/浅色主题） |
| 构建工具 | Vite |

## 打包为桌面安装包

VisionWork2 支持打包为可分发的桌面软件安装包（.exe / .dmg / .AppImage）。

### 前置条件

```bash
# 1. 确保 Python 后端依赖已安装
pip install -r requirements.txt

# 2. 确保 Node.js 依赖已安装
npm install
```

### 一键构建（Windows）

```bash
npm run build:win
```

输出目录：`release/` — 生成 `VisionWork2 Setup x.x.x.exe` NSIS 安装程序。

### 一键构建（macOS）

```bash
npm run build:mac
```

输出目录：`release/` — 生成 `.dmg` 磁盘映像。

### 构建流程详解

```
npm run build:backend    → PyInstaller 将 Python 后端打包为 backend-dist/backend.exe
npm run build            → Vite 将 React 前端构建为 dist/
npm run build:electron   → TypeScript 编译 Electron 主进程到 dist-electron/
electron-builder         → 将以上产物 + Electron 壳打包为安装程序
```

### 安装包内容

```
VisionWork2 Setup.exe
  └── VisionWork2.exe (Electron)
      ├── dist/           (前端静态文件)
      ├── dist-electron/  (Electron 主进程)
      └── resources/backend/backend.exe  (PyInstaller 打包的 Python 后端)
```

用户安装后双击桌面图标即可启动，无需安装 Python 或 Node.js。

## 项目结构说明

- WebSocket 通信采用线程安全队列（queue.Queue），子线程推送事件，主异步循环消费发送
- 工具注册采用单例模式（ToolRegistry），YAML 定义与 Python 实现分离
- 记忆笔记存储在工作空间 `workspace/` 目录下的 `memory/` 子目录
- 会话数据持久化在浏览器 IndexedDB

## License

MIT