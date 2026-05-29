# ----------------------------------------------------------------------
# 通用文件分析提示词
# 不再限定于代码分析，可处理文档、配置、数据等各类文件
# ----------------------------------------------------------------------
GENERAL_ANALYSIS_PROMPT = """请分析以下文件内容，并生成结构化的分析笔记。

文件名：{filename}
文件路径：{filepath}

文件内容：
```
{content}
```

请按以下结构生成分析笔记（使用Markdown格式）：

## 文件概述
简要描述该文件的整体内容和用途。说明文件类型（代码/文档/配置/数据等）。

## 关键内容
提取文件中的关键信息、核心概念、重要数据、主要逻辑或结构要点。

## 关键实体
列出文件中涉及的主要实体，根据文件类型灵活选择：
- 代码文件：函数、类、接口、模块
- 文档文件：主题、章节、核心观点
- 配置文件：配置项、环境、参数
- 数据文件：字段、表结构、数据模式

## 关系与联系
分析该文件内容与其他文件或模块可能存在的关联关系。
"""

# ----------------------------------------------------------------------
# 画布批量生成提示词（方案C核心）
# 在所有文件分析完成后，基于笔记摘要一次性生成完整流程图
# ----------------------------------------------------------------------
CANVAS_GENERATION_PROMPT = """你是一个流程图绘制助手。基于以下项目分析笔记和用户意图，生成一个完整的流程图指令序列。

## 用户意图
{user_intent}

## 项目笔记摘要
{notes_summary}

## 指令格式要求
请生成一个JSON数组，每个元素是一个画布指令。支持的指令类型：

1. add_node: 添加节点
   {{"cmd": "add_node", "id": "唯一ID(英文)", "label": "节点名称", "type": "节点类型", "group": "分组", "description": "简要描述"}}
   type可选值: module, function, class, data, config, interface, service, component, document, concept, process
   group可选值: python, javascript, react, typescript, java, cpp, c, web, config, doc, data, image, backend, frontend, other

2. add_edge: 添加连线
   {{"cmd": "add_edge", "source": "源节点ID", "target": "目标节点ID", "label": "关系描述"}}

3. layout: 自动布局
   {{"cmd": "layout", "algorithm": "dagre"}}

## 绘制原则
- 根据用户意图决定流程图的结构和重点
- 节点数量控制在10-25个之间，选择最重要的模块/概念/实体
- 边要体现真实的关系（调用、依赖、包含、引用、数据流等）
- 最后一条指令必须是 layout
- 只输出JSON数组，不要包含```json```等标记
"""

ENTITY_DESCRIPTION_PROMPT = """用一句话中文描述以下代码元素的功能，不超过30个词。
代码元素类型：{type}
名称：{name}
所在代码片段：
{code_snippet}"""

FALLBACK_EXTRACTION_PROMPT = """请分析以下代码文件，提取所有实体和关系，以JSON格式输出。

文件名：{filename}
文件路径：{filepath}

代码内容：
```
{content}
```

请输出一个JSON对象，包含 entities 和 relations 两个数组，格式如下：
{{
  "entities": [
    {{
      "id": "{filename}:实体名（如 {filename}:ClassName.methodName）",
      "type": "function|method|class|variable|import",
      "name": "简短名称",
      "file": "{filename}",
      "line_start": 行号,
      "line_end": 行号,
      "description": "一句话描述"
    }}
  ],
  "relations": [
    {{
      "source_id": "调用方实体id",
      "target_id": "被调用方实体id",
      "type": "calls|inherits|imports|contains",
      "description": "可选关系描述"
    }}
  ]
}}

注意：
- 只输出JSON，不要包含```json```等标记
- 实体id格式：{filename}:实体名
- 确保行号准确
"""

FALLBACK_NOTE_PROMPT = """请基于以下实体信息，生成该文件的结构化分析笔记（Markdown格式）。

文件名：{filename}
文件路径：{filepath}

## 已提取的实体
{entities_summary}

请按以下结构生成分析笔记：

## 文件概述
简要描述该文件的整体内容和用途。

## 关键实体
列出主要实体及其功能描述。

## 关系与联系
分析该文件内容与其他文件或模块可能存在的关联关系。
"""