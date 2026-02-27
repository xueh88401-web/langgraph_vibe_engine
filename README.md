<div align="center">

# 🧠 Vibe Engine

**基于 LangGraph 的多 Agent 协作系统**

*类 Notion 工作区中的智能写作与创作引擎*

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.0.8-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](./LICENSE)

</div>

---

## ✨ 特性

- 🤖 **Master-SubAgent 架构** — 主 Agent 协调调度，SubAgent 专注执行
- 🔍 **联网调研** — 基于 Tavily 的并行搜索，自动归档素材并生成调研报告
- 🎨 **AI 图像生成** — 豆包 Seedream 3.0 生图 + 多模态审查，自动重试直到满意
- 📝 **画布文档管理** — 类 Notion 的文档 CRUD，支持目录浏览和全文搜索
- 📋 **任务规划** — 内置 Todo 系统，自动拆解复杂任务

---

## 🏗️ 架构概览

```
                    ┌──────────────┐
                    │   __start__  │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
              ┌─────│ master_agent │◄──────────────────┐
              │     └──────┬───────┘                    │
              │            ▼                            │
              │     ┌──────────────┐                    │
              │     │    route     │                    │
              │     └──┬───┬───┬──┘                    │
              │        │   │   │                       │
              ▼        ▼   │   ▼                       │
          __end__   tools  │  research_subgraph        │
                       │   │        │                  │
                       │   ▼        │                  │
                       │  image_generation_subgraph    │
                       │        │                      │
                       └────────┴──────────────────────┘
```

### 路由逻辑

| 条件 | 目标 |
|---|---|
| LLM 无 `tool_calls` | `__end__`（对话结束） |
| 包含 `research` 调用 | 🔍 Research SubGraph |
| 包含 `image_generation` 调用 | 🎨 ImageGeneration SubGraph |
| 其他工具调用 | 🔧 Tools 节点（普通工具执行） |

---

## 🤖 Agent 详解

### 🧑‍💼 Master Agent

> **模型**: DeepSeek (`deepseek-chat`)

- 理解用户意图，协调 SubAgent，管理画布文档，执行任务规划
- 纯文本模型，不具备视觉能力；图像相关任务委派给 ImageGeneration SubAgent

### 🔍 Research SubAgent

> **模型**: DeepSeek (`deepseek-chat`)

- 执行联网调研任务，支持并行搜索 3–5 个查询
- 自动归档素材并生成调研报告
- **工作模式**:
  - `scratchpad` — 一次性调研，结果存在内存中
  - `persist` — 持久化调研，结果保存到画布文档
- **预算控制**: 通过 `budget_total` / `budget_used` 限制推理轮数

### 🎨 ImageGeneration SubAgent

> **推理模型**: 豆包 Seed 2.0 Pro（多模态） · **生图模型**: 豆包 Seedream 3.0

- 标准 ReAct 循环 — 自主生成图片、审查质量、不满意则修改 prompt 重试
- 能真正「看到」生成的图片并做出质量判断，最多 3 轮迭代

---

## 📁 项目结构

```
langgraph_vibe_engine/
├── main.py                 # 入口文件（命令行 & LangGraph Studio）
├── agent.py                # Master Agent Graph 定义
├── research_graph.py       # Research SubAgent Graph
├── image_graph.py          # ImageGeneration SubAgent Graph
├── state.py                # 状态类型定义
├── langgraph.json          # LangGraph Studio 配置
│
├── tools/
│   ├── web_tools.py        # search_web · read_webpage
│   ├── canvas_tools.py     # 画布文档 CRUD · 目录 · 搜索
│   ├── image_tools.py      # 图片上传(COS) · text2img · img2img
│   ├── master_tools.py     # SubAgent 触发器 · todo_write
│   └── research_tools.py   # 素材归档 · 报告终结
│
├── prompts/
│   ├── master.py           # Master Agent 系统提示词
│   ├── research.py         # Research SubAgent 系统提示词
│   └── imagegeneration.py  # ImageGeneration SubAgent 系统提示词
│
├── requirements.txt
├── LICENSE
└── .env                    # 环境变量（需自行创建）
```

---

## 🚀 快速开始

### 1️⃣ 安装依赖

```bash
pip install -r requirements.txt
```

### 2️⃣ 配置环境变量

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

### 3️⃣ 启动交互式命令行

```bash
python main.py
```

支持：自然语言对话 · 联网调研 · AI 图片生成 · 画布文档管理 · 图片编辑

### 4️⃣ LangGraph Studio（开发调试）

```bash
langgraph dev
```

`langgraph.json` 中注册了三个可独立调试的 Graph：

| Graph | 说明 |
|---|---|
| `master` | 完整的 Master Agent Graph |
| `research` | Research SubAgent Graph |
| `image` | ImageGeneration SubAgent Graph |

---

## 💾 数据存储

| 数据 | 存储方式 |
|---|---|
| 📝 画布文档 | `.workspace.json`（已加入 `.gitignore`） |
| 📋 Todo 任务 | 运行时内存，通过 `state["todos"]` 跨节点同步 |
| 🔍 调研素材 | `scratchpad` 模式 → 内存 / `persist` 模式 → 画布 |

---

## 🛠️ 技术栈

| 技术 | 用途 |
|---|---|
| [LangGraph](https://github.com/langchain-ai/langgraph) `1.0.8` | Agent Graph 编排框架 |
| [LangChain](https://github.com/langchain-ai/langchain) | LLM 调用和工具定义 |
| [DeepSeek](https://deepseek.com) | 文本推理模型 |
| [豆包 Seed 2.0 Pro](https://www.volcengine.com) | 多模态推理模型 |
| [豆包 Seedream 3.0](https://www.volcengine.com) | AI 生图模型 |
| [Tavily](https://tavily.com) | 联网搜索 API |
| [腾讯云 COS](https://cloud.tencent.com/product/cos) | 图片存储 CDN |

---

<div align="center">

**MIT License** · Made with ❤️ by [xueh88401-web](https://github.com/xueh88401-web)

</div>
