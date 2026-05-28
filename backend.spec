# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for VisionWork2 Python backend
Entry point: src/backend/main.py
Output: backend-dist/backend.exe (Windows) / backend-dist/backend (macOS/Linux)
"""

import sys
import os
from pathlib import Path

# ---- 确定项目根 ----
# SPECPATH 是 PyInstaller 内置变量，指向 spec 文件所在目录
_PROJECT_ROOT = Path(SPECPATH)

# ---- 入口脚本 ----
ENTRY_SCRIPT = str(_PROJECT_ROOT / 'src' / 'backend' / 'main.py')

# ---- 需要包含的隐式导入 (防止 PyInstaller 遗漏) ----
HIDDEN_IMPORTS = [
    # LangChain / LangGraph
    'langchain',
    'langchain_openai',
    'langchain_core',
    'langchain_core.messages',
    'langchain_core.language_models',
    'langgraph',
    'langgraph.graph',
    'langgraph.checkpoint',
    # FastAPI / Uvicorn
    'uvicorn',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.logging',
    'fastapi',
    'fastapi.middleware',
    'fastapi.middleware.cors',
    'starlette',
    # ChromaDB
    'chromadb',
    'chromadb.config',
    'chromadb.db',
    'chromadb.api',
    # Sentence Transformers
    'sentence_transformers',
    # HTTP / 网络
    'httpx',
    'httpcore',
    'aiohttp',
    'websockets',
    # 工具
    'yaml',
    'pydantic',
    'pydantic_core',
    'tiktoken',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
    'json',
    'hashlib',
    'asyncio',
    'concurrent.futures',
]

# ---- 需要收集的数据文件 (不含代码，如模型权重、模板等) ----
DATAS = [
    # chromadb 的配置文件
    ('chromadb', 'chromadb'),
]

# ---- 排除不需要的模块 (减小体积) ----
EXCLUDES = [
    'tkinter',
    'unittest',
    'test',
    'pdb',
    'setuptools',
    'pip',
    'IPython',
    'jupyter',
    'notebook',
    'matplotlib',
    'numpy.random._examples',
    'torch',
    'torchvision',
    'torchaudio',
    'tensorflow',
    'scipy',
    'pandas.tests',
    'PIL',
    'cv2',
    'sklearn',
    'sqlalchemy.testing',
]

# ---- PyInstaller 配置 ----
a = Analysis(
    [ENTRY_SCRIPT],
    pathex=[str(_PROJECT_ROOT), str(_PROJECT_ROOT / 'src')],
    binaries=[],
    datas=[(str(_PROJECT_ROOT / 'src' / 'backend' / 'skills'), 'backend/skills')],
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # 不弹出控制台窗口 (Windows)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)