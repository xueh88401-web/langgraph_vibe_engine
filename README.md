# Vibe Engine — LangGraph Multi-Agent System

基于 LangGraph 构建的多 Agent 协作系统，实现了一个类 Notion 工作区中的智能写作与创作引擎。系统采用 Master-SubAgent 架构，支持联网调研、AI 图像生成、画布文档管理和任务规划等能力。

## 架构概览

```
┌──────────────────┐
│     __start__     │
└────────┬─────────┘
         ▼
┌──────────────────┐
│   master_agent   │◄─────────────────────────────┐
└────────┬─────────┘                               │
         ▼                                         │
┌──────────────────┐                               │
│     route        │                               │
└──┬───┬───┬───┬───┘                               │
   │   │   │   │                                   │
   ▼   │   │   ▼                                   │
tools  │   │  __end__                              │
   │   │   │                                       │
   │   ▼   ▼                                       │
   │  research  image_generation                   │
   │  _subgraph  _subgraph                         │
   │   │         │                                 │
   └───┴─────────┴─────────────────────────────────┘
```

### 路由逻辑

- LLM 无 `tool_calls` → `__end__`（对话结束）
- `tool_calls` 包含 `research` → **Research SubGraph**
- `tool_calls` 包含 `image_generation` → **ImageGeneration SubGraph**
- 其他 → **Tools 节点**（普通工具执行）

## 核心模块

| 文件 | 说明 |
|---|---|
| `main.py` | 入口文件，支持交互式命令行和 LangGraph Studio |
| `agent.py` | Master Agent Graph 定义，包含路由逻辑和所有节点 |
| `research_graph.py` | Research SubAgent Graph，负责联网调研 |
| `image_graph.py` | ImageGeneration SubAgent Graph，负责 AI 图像生成 |
| `state.py` | 状态类型定义（`VibeMasterState`、`VibeResearchState`、`VibeImageGenState`） |
| `langgraph.json` | LangGraph Studio 配置文件 |

### 工具集 (`tools/`)

| 文件 | 工具 | 说明 |
|---|---|---|
| `web_tools.py` | `search_web`、`read_webpage` | 基于 Tavily API 的网页搜索和内容提取 |
| `canvas_tools.py` | `canvas_create`、`canvas_update`、`canvas_insert`、`canvas_delete`、`get_directory`、`read_document`、`search_in_workspace` | 类 Notion 画布文档的 CRUD 操作 |
| `image_tools.py` | `upload_image`、`text2img`、`img2img`、`finish_image_generation` | 图片上传（腾讯云 COS）及豆包 Seedream 3.0 生图 |
| `master_tools.py` | `research`、`image_generation`、`todo_write` | SubAgent 触发器和任务规划工具 |
| `research_tools.py` | `archive_source_into_scratchpad`、`finish_research_with_report` | Research SubAgent 专用的素材归档和报告终结工具 |

### Prompts (`prompts/`)

| 文件 | 说明 |
|---|---|
| `master.py` | Master Agent 系统提示词 |
| `research.py` | Research SubAgent 系统提示词 |
| `imagegeneration.py` | ImageGeneration SubAgent 系统提示词 |

## Agent 说明

### Master Agent

- **模型**: DeepSeek (`deepseek-chat`)
- **职责**: 理解用户意图，协调 SubAgent，管理画布文档，执行任务规划
- **特性**: 纯文本模型，不具备视觉能力；图像相关任务委派给 ImageGeneration SubAgent

### Research SubAgent

- **模型**: DeepSeek (`deepseek-chat`)
- **职责**: 执行联网调研任务，支持并行搜索 3-5 个查询，自动归档素材并生成调研报告
- **工作模式**:
  - `scratchpad`：一次性调研，结果存在内存中
  - `persist`：持久化调研，结果保存到画布文档
- **预算控制**: 通过 `budget_total` / `budget_used` 限制推理轮数

### ImageGeneration SubAgent

- **推理模型**: 豆包 Seed 2.0 Pro（多模态，支持看图 + Function Calling）
- **生图模型**: 豆包 Seedream 3.0（text2img / img2img）
- **工作方式**: 标准 ReAct 循环——自主生成图片、审查质量、不满意则修改 prompt 重试，最多 3 轮
- **特性**: 能真正看到生成的图片并做出质量判断

## 环境变量

在项目根目录创建 `.env` 文件：

```env
# DeepSeek API (Master Agent + Research SubAgent)
DEEPSEEK_API_KEY=your_deepseek_api_key

# 豆包/火山引擎 API (ImageGeneration SubAgent)
DOUBAO_API_KEY=your_doubao_api_key

# Tavily API (网页搜索)
TAVILY_API_KEY=your_tavily_api_key

# 腾讯云 COS (图片上传，可选)
SECRET_ID=your_tencent_secret_id
SECRET_KEY=your_tencent_secret_key
```

## 快速开始

### 1. 安装依赖

```bash
cd /Users/kker/project/langgraph_vibe_engine
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入 API Key
```

### 3. 交互式命令行

```bash
python main.py
```

启动后可直接对话，支持：
- 自然语言对话
- 联网调研（自动调用 Research SubAgent）
- AI 图片生成（自动调用 ImageGeneration SubAgent）
- 画布文档管理
- 发送图片路径进行图片编辑

### 4. LangGraph Studio（开发调试）

```bash
langgraph dev
```

`langgraph.json` 中注册了三个 Graph：
- `master` — 完整的 Master Agent Graph
- `research` — Research SubAgent Graph（可单独调试）
- `image` — ImageGeneration SubAgent Graph（可单独调试）

## 数据存储

- **画布文档**: 保存在 `.workspace.json` 文件中（已加入 `.gitignore`）
- **Todo 任务**: 运行时内存存储，通过 `state["todos"]` 在 Graph 各节点间同步
- **调研素材**: `scratchpad` 模式下存于内存，`persist` 模式下写入画布

## 技术栈

- **LangGraph** `1.0.8` — Agent Graph 编排框架
- **LangChain** — LLM 调用和工具定义
- **DeepSeek** — 文本推理模型
- **豆包 Seed 2.0 Pro** — 多模态推理模型（图像生成 Agent）
- **豆包 Seedream 3.0** — AI 生图模型
- **Tavily** — 联网搜索 API
- **腾讯云 COS** — 图片存储 CDN

