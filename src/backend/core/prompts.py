ANALYSIS_PROMPT = """你是一位{profession}。请分析以下代码文件，并生成结构化的分析笔记。

文件名：{filename}
文件路径：{filepath}

代码内容：
```
{code_content}
```

请按以下结构生成分析笔记（使用Markdown格式）：

## 模块概述
简要描述该文件/模块的整体功能和职责。

## 核心组件
列出关键的函数、类、接口及其作用。

## 依赖关系
分析该模块依赖的其他模块或外部库。

## 注意事项
指出代码中值得关注的设计模式、潜在问题或改进建议。
"""

SECOND_PASS_PROMPT = """你是一位{profession}。请基于以下代码项目的分析笔记，生成一个分析图指令序列。

## 项目笔记摘要
{notes_summary}

## 要求
请生成一个JSON数组，每个元素是一个画布指令。严格按照以下格式输出，只输出JSON数组，不要包含任何其他文字、解释或markdown标记。

支持的指令类型：

1. add_node: 添加节点
   {{"cmd": "add_node", "id": "唯一ID(英文)", "label": "节点标签(中文)", "type": "节点类型", "group": "分组", "description": "简要描述", "codeRef": [{{"file": "文件路径", "lines": [起始行, 结束行]}}]}}
   type可选值: module, function, class, data, config, interface, service, component
   group可选值: python, javascript, react, typescript, java, cpp, c, web, config, doc, data, image, other
   codeRef为可选字段，列出该节点关联的源代码文件及其行号范围。如果从笔记中能确定具体文件，请填写相对路径；如果不确定，可省略此字段。

2. add_edge: 添加连线
   {{"cmd": "add_edge", "source": "源节点ID", "target": "目标节点ID", "label": "关系描述(中文)"}}

3. layout: 自动布局
   {{"cmd": "layout", "algorithm": "dagre"}}

请根据你的职业视角({profession})，生成有意义的分析图：
- 后端开发工程师：生成模块调用关系图，展示各模块之间的依赖和调用关系
- 前端开发工程师：生成组件树和状态流转图
- 产品经理：生成功能结构图，展示功能模块的层次关系
- 架构师：生成系统架构图，展示系统分层和组件关系
- 数据分析师：生成数据流图，展示数据处理流程

注意：
- 节点数量控制在10-25个之间，选择最重要的模块/组件
- 边要体现模块间的真实关系（调用、依赖、数据流等）
- 最后一条指令必须是 layout
- 只输出JSON数组，不要包含```json```等标记"""
