# 项目结构说明

这个项目按“协议层、编排层、工具层、能力说明层、前端工作台”拆分。后续新增能力时，优先放到对应层级，避免所有逻辑继续堆到 `server.py`、`App.vue` 或单个工具文件里。

## 后端

```text
api/
├── routers/      # FastAPI 路由，只做协议适配、鉴权和参数转发
├── schemas/      # Pydantic 请求模型
├── services/     # 业务服务，封装任务、文件、会话、RAGFlow、鉴权等逻辑
├── context.py    # ContextVar，上下文绑定 thread_id、user_id、session_dir
├── monitor.py    # WebSocket 执行过程推送
├── security.py   # RBAC Scope 校验
└── server.py     # FastAPI 装配和 lifespan
```

路由层不要直接写复杂业务逻辑。新增接口时，推荐流程是：

1. 在 `api/schemas/` 定义请求体。
2. 在 `api/services/` 写具体业务。
3. 在 `api/routers/` 做鉴权、参数校验和调用 service。
4. 在 `api/server.py` 注册共享 service 或 router。

## Agent 编排

```text
agent/
├── main_agent.py          # 主 Agent 任务编排入口
├── factory.py             # Agent 构建、工具注册和 Redis 生命周期
├── runtime/
│   ├── session.py         # 会话工作区与上传文件准备
│   └── stream.py          # LangGraph 流式事件解析
├── async_graphs.py        # LangGraph Agent Server 使用的异步子 Agent Graph
├── sandbox.py             # Daytona 沙箱管理
├── llm.py                 # OpenAI 兼容模型初始化
└── subagents/             # 数据库、RAGFlow、互联网搜索子 Agent 配置
```

`main_agent.py` 只负责任务编排；Agent 构建放在 `factory.py`，会话和流式处理放在 `runtime/`。具体能力放到 `tools/`，能力使用说明放到 `skills/`。

## 共享基础层

```text
core/
├── settings.py    # 环境变量读取、类型转换和服务配置校验
└── paths.py       # 会话路径解析与越界保护
```

`core/` 只接收不依赖业务状态的后端共享能力，不放数据库、知识库或前端协议逻辑。业务模块统一通过 `get_settings()` 读取配置，不应各自调用 `os.getenv()`。

## 工具层

```text
tools/
├── database/      # MySQL / SQLModel 查询工具
├── document/      # Markdown、PDF 生成
├── file/          # 文件读取
├── memory/        # 长期记忆工具
├── ragflow/       # RAGFlow 知识库和助手工具
├── search/        # Tavily 联网搜索
└── skill/         # 外部 Skill 安装、校验和分配
```

工具函数应该保持“小而明确”：输入参数清楚、返回结构化结果、不要直接依赖前端状态。需要向前端展示执行过程时，通过 `api.monitor.monitor.report_tool()` 上报。

## Skills

```text
skills/
├── database-query/
├── document-generation/
├── long-term-memory/
├── ragflow-knowledge-base/
├── structured-data-query/
└── web-research/
```

Skill 不是工具函数，而是给 Agent 看的领域说明书。工具负责“能做什么”，Skill 负责“什么时候用、怎么用、边界是什么”。

## 前端

```text
ui/src/
├── api/
│   └── client.ts                # Axios 实例、鉴权头和接口封装
├── components/
│   ├── ChatPanel.vue
│   ├── ExecutionProcess.vue
│   ├── KnowledgeBaseManager.vue
│   ├── SessionFiles.vue
│   ├── WorkspaceDrawer.vue
│   └── WorkspaceRail.vue
├── styles/
├── composables/
│   ├── useImageAssets.ts        # 图片 Blob URL 与引用恢复
│   ├── useImageKnowledge.ts     # 图片知识库状态
│   └── useRagflowKnowledge.ts   # RAGFlow 管理状态
├── utils/
├── types.ts
└── App.vue
```

`App.vue` 负责会话状态、WebSocket 和组件编排。新增 HTTP 接口放到 `api/client.ts`；可复用业务状态放到 `composables/`；展示视图放到 `components/`；共享类型和纯格式化函数分别放到 `types.ts` 与 `utils/`。

## 运行目录

这些目录由运行时自动生成，不提交到 Git：

- `runtime/`：已安装的用户 Skill、异步 worker skill source、临时状态。
- `output/`：每个会话生成的文件。
- `updated/`：用户上传文件的临时保存区。
- `tmp/`：文档渲染等流程产生的临时文件。
- `.langgraph_api/`：本地 Agent Server 运行状态。
