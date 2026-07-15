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
├── main_agent.py          # 主 Agent 运行入口，绑定 thread_id、user_id、沙箱和记忆
├── async_graphs.py        # LangGraph Agent Server 使用的异步子 Agent Graph
├── sandbox.py             # Daytona 沙箱管理
├── llm.py                 # OpenAI 兼容模型初始化
└── subagents/             # 数据库、RAGFlow、互联网搜索子 Agent 配置
```

`main_agent.py` 负责运行时上下文和主流程，不适合继续堆具体工具逻辑。具体能力应该放到 `tools/`，能力使用说明放到 `skills/`。

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
├── components/
│   ├── ChatPanel.vue
│   ├── ExecutionProcess.vue
│   ├── KnowledgeBaseManager.vue
│   ├── SessionFiles.vue
│   ├── WorkspaceDrawer.vue
│   └── WorkspaceRail.vue
├── styles/
├── utils/
├── types.ts
└── App.vue
```

`App.vue` 负责全局状态、接口调用和组件编排。新增视图时优先拆成组件；接口返回数据类型放到 `types.ts`，格式化函数放到 `utils/`。

## 运行目录

这些目录由运行时自动生成，不提交到 Git：

- `runtime/`：已安装的用户 Skill、异步 worker skill source、临时状态。
- `output/`：每个会话生成的文件。
- `updated/`：用户上传文件的临时保存区。
- `.langgraph_api/`：本地 Agent Server 运行状态。

