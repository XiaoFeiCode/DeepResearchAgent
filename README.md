# DeepAgent Studio：多智能体驱动的企业级深度搜索与知识增强系统

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Vue 3](https://img.shields.io/badge/Vue.js-3-4FC08D?style=flat-square&logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-1C3C3C?style=flat-square)](https://langchain-ai.github.io/langgraph/)
[![DeepAgents](https://img.shields.io/badge/DeepAgents-Orchestration-EA580C?style=flat-square)](https://github.com/langchain-ai/deepagents)
[![MySQL](https://img.shields.io/badge/MySQL-Database-4479A1?style=flat-square&logo=mysql&logoColor=white)](https://www.mysql.com/)
[![RAGFlow](https://img.shields.io/badge/RAGFlow-Knowledge%20Base-00A6A6?style=flat-square)](https://github.com/infiniflow/ragflow)
[![uv](https://img.shields.io/badge/uv-Managed-DE5FE9?style=flat-square&logo=astral&logoColor=white)](https://docs.astral.sh/uv/)

一个融合 Multi-Agent + Agentic RAG + 工具调用编排 + 实时可视化执行过程的企业级 AI 搜索与知识系统。

## 系统定位
本项目面向 Agentic AI 与企业知识系统场景：
- 多智能体任务调度机制
- 工具调用与路由决策系统
- 可扩展的企业知识增强系统设计

## 功能截图

### 多智能体工作台

![多智能体深度搜索工作台](imgs_display/workbench.png)

### 智能体执行过程与回答

主智能体会拆解复杂任务并连续调用多个能力。下图中的任务依次使用了 RAGFlow 助手、知识库文档列表工具和 Markdown 生成工具，最终产物会出现在会话文件栏中。

![多工具协作执行结果](imgs_display/multi-tool-result.png)

### RAGFlow 知识库管理

前端可以直接查看知识库和文档列表、上传文件、提交解析以及删除文档。

![知识库管理](imgs_display/knowledge-base-management.png)

### RAGFlow 服务

RAGFlow 中配置的知识库与专业助手可以被项目中的 RAGFlow 子智能体调用。

![RAGFlow 知识库和助手](imgs_display/ragflow.png)

## 核心能力

- **多智能体路由**：主智能体根据任务类型选择数据库、RAGFlow 或互联网搜索助手。
- **结构化数据查询**：通过 SQLModel/SQLAlchemy 查询 MySQL，并限制 Agent 只执行只读查询。
- **企业知识库管理**：支持列出知识库、查看文档、上传并解析文档、重新解析和删除文档。
- **RAGFlow 助手问答**：自动获取助手列表，选择合适的专业助手并发起提问。
- **互联网搜索**：通过 Tavily 检索公开资料，并在回答中保留原始来源链接。
- **文件分析**：读取 Markdown、TXT、Word、PDF 和 Excel 文件。
- **文档生成**：生成 Markdown，并可在 Windows + Microsoft Word 环境中转换为 PDF。
- **双层会话记忆**：LangGraph SQLite Checkpointer 保存 Agent 执行上下文，MySQL 保存前端可恢复的会话与消息记录。
- **实时执行过程**：FastAPI WebSocket 向前端推送子智能体调用、工具调用和最终结果。
- **可控服务生命周期**：FastAPI `lifespan` 统一初始化共享服务，关闭时取消并等待 Agent 与 WebSocket 后台任务，随后释放 SQLite、连接和事件循环资源。
- **项目 Skill**：通过 `skills/*/SKILL.md` 为智能体注入领域路由和操作流程。

## 核心亮点
- 🧩 多智能体架构：基于 LangGraph / DeepAgents 实现主智能体 + 子智能体协同调度
- 🔀 Agentic RAG：支持基于任务的动态路由（SQL / RAG / Web）
- 🗂 多源数据融合：MySQL + RAGFlow + Tavily 联合检索
- 🧠 智能任务拆解：主智能体自动规划执行步骤并调用工具链
- 📡 实时流式输出：通过 WebSocket 展示 Agent 思考与执行过程
- 📚 企业级知识库：集成 RAGFlow 实现文档检索与问答
- 🧾 结构化生成：支持 Markdown 报告自动生成与导出
- 💾 会话记忆：SQLite 管理 Agent 检查点，MySQL 持久化聊天记录，实现 thread 级隔离和刷新恢复

## 系统架构

```mermaid
flowchart LR
    UI[Vue 工作台] <-->|REST + WebSocket| API[FastAPI 服务]
    UI --> SESSION[sessionStorage 当前 thread_id]
    API --> MAIN[主智能体]
    API --> HISTORY[(MySQL 会话记录)]
    MAIN --> DB[数据库查询助手]
    MAIN --> RAG[RAGFlow 助手]
    MAIN --> WEB[互联网搜索助手]
    MAIN --> DOC[文件与文档工具]
    DB --> MYSQL[(MySQL 业务数据)]
    RAG --> RF[(RAGFlow)]
    WEB --> TAVILY[Tavily]
    MAIN --> MEMORY[(SQLite Checkpoint)]
```

## 项目结构

```text
deep_agent_project/
├── agent/                 # 主智能体、模型和子智能体配置
├── api/
│   ├── routers/           # 任务、文件、RAGFlow 与 WebSocket 路由
│   ├── schemas/           # Pydantic 请求模型
│   ├── services/          # 后台任务、文件与 RAGFlow 业务逻辑
│   ├── monitor.py         # WebSocket 执行事件监控
│   └── server.py          # FastAPI 装配与 lifespan
├── prompt/                # 主智能体与子智能体提示词
├── skills/                # 项目内置 SKILL.md 工作流
├── tools/
│   ├── database/          # MySQL/SQLModel 查询工具
│   ├── document/          # Markdown 和 PDF 生成工具
│   ├── file/              # 本地文件读取工具
│   ├── ragflow/           # RAGFlow 知识库和助手工具
│   └── search/            # Tavily 互联网搜索工具
├── ui/src/
│   ├── components/        # 聊天、执行过程、会话文件与知识库组件
│   ├── styles/            # 工作台全局样式
│   ├── utils/             # 前端格式化函数
│   ├── types.ts           # 前端共享类型
│   └── App.vue            # 页面状态与组件编排
├── utils/                 # 路径与文档转换辅助模块
├── imgs_display/          # README 功能截图
├── pyproject.toml         # Python 直接依赖
└── uv.lock                # 可复现的 Python 依赖锁文件
```

运行时会自动创建 `runtime/`、`output/` 和 `updated/`。这些目录包含会话状态、生成文件和上传文件，默认不会提交到 Git。

后端路由只处理 HTTP/WebSocket 协议适配，具体操作由 `services/` 承担。前端 `App.vue` 保留状态与数据请求，各业务视图拆分到独立组件，便于继续扩展新工具和管理界面。

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- MySQL，可选；数据库查询和聊天记录持久化需要，未配置时聊天记录功能会降级
- RAGFlow，可选；知识库功能需要
- Tavily API Key，可选；联网搜索功能需要
- OpenAI 兼容的模型服务
- Microsoft Word，可选；当前 Markdown 转 PDF 工具使用 Word COM，仅支持 Windows

## 快速开始

### 1. 安装后端依赖

```powershell
uv sync --locked
```

`pyproject.toml` 是直接依赖清单，`uv.lock` 用于固定完整依赖版本。`requirements.txt` 由 uv 自动导出，仅用于兼容传统 pip 工作流。

### 2. 配置环境变量

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，填写你实际使用的模型服务和可选数据源：

| 变量 | 用途 | 是否必填 |
| --- | --- | --- |
| `OPENAI_BASE_URL` | OpenAI 兼容接口地址 | 是 |
| `OPENAI_API_KEY` | 模型服务 API Key | 是 |
| `LLM_MODEL` | 接口实际支持的模型名 | 是 |
| `TAVILY_API_KEY` | 互联网搜索 | 使用联网搜索时 |
| `MYSQL_HOST` / `MYSQL_PORT` | MySQL 地址 | 使用数据库工具时 |
| `MYSQL_USER` / `MYSQL_PASSWORD` | MySQL 凭据 | 使用数据库工具时 |
| `MYSQL_DATABASE` | MySQL 数据库名 | 使用数据库工具时 |
| `RAGFLOW_API_URL` | RAGFlow API 地址 | 使用知识库时 |
| `RAGFLOW_API_KEY` | RAGFlow API Key | 使用知识库时 |

不要提交真实的 `.env` 文件。

### 3. 启动后端

在项目根目录执行：

```powershell
uv run api/server.py
```

后端默认地址：`http://127.0.0.1:8000`

### 4. 启动前端

新开一个 PowerShell 窗口：

```powershell
cd ui
npm ci
npm run dev
```

前端默认地址：`http://127.0.0.1:5173`

## 内置 Skills

| Skill | 作用 |
| --- | --- |
| `structured-data-query` | 将具体内部数据问题优先路由到数据库 |
| `database-query` | 规定先看表、再看字段、最后执行只读 SQL 的流程 |
| `ragflow-knowledge-base` | 管理知识库、文档和 RAGFlow 助手问答流程 |
| `web-research` | 处理公开互联网信息并保留来源链接 |
| `document-generation` | 生成 Markdown/PDF 文档 |

Skill 是智能体的任务说明和决策流程，Tool 是真正执行数据库查询、上传文档或互联网搜索的代码。

## 使用示例

可以在前端输入：

```text
查看 RAGFlow 中有哪些知识库
```

```text
查询数据库里的库存记录
```

```text
搜索 LangGraph 的最新资料，并给出原始来源链接
```

同一标签页中的追问会复用当前 `thread_id`。前端将该 ID 保存在 `sessionStorage`，刷新页面后会从 MySQL 的 `agent_conversations` 和 `agent_messages` 表恢复聊天记录；LangGraph SQLite Checkpointer 则继续负责恢复 Agent 内部执行上下文。点击“新会话”会生成新的 `thread_id`，适合开始一个无关任务。关闭标签页后再次打开也会生成新会话，不会自动带入旧上下文。

## 开发验证

```powershell
uv lock --check
uv sync --locked
uv pip check
uv run python -m compileall -q agent api ragflow skills tools utils

cd ui
npm run build
```

## 当前边界

- 当前项目以本地单用户开发和能力展示为主，API 尚未加入登录、权限与限流。
- CORS 配置适合本地调试，不建议直接暴露到公网。
- SQLite Checkpointer 适合本地 Agent 检查点；多实例部署时应迁移到 Postgres 或 Redis 等共享 Checkpointer。
- MySQL 当前保存聊天正文但尚未加入用户账号字段；接入登录后应增加 `user_id` 并按用户校验会话访问权限。
- RAGFlow、MySQL、Tavily 等外部能力需要单独部署或申请对应服务。
- `ragflow/` 下的本地知识库原始资料默认被 Git 忽略，请根据数据授权自行准备测试文件。
