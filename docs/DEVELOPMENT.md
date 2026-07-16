# 开发与验证

## 配置管理

运行配置统一定义在 `core/settings.py`。新增环境变量时，应先在
`AppSettings` 中声明类型、默认值和校验规则，再由业务模块通过
`get_settings()` 读取，不要在各模块中直接调用 `os.getenv()`。

## 后端依赖

```powershell
uv sync --locked
```

## 前端依赖

```powershell
cd ui
npm install
```

## 启动服务

后端：

```powershell
uv run python -m api.server
```

前端：

```powershell
cd ui
npm run dev
```

异步子 Agent 本地服务：

```powershell
uv run langgraph dev
```

## 常用验证命令

```powershell
uv pip check
uv run python -m compileall -q agent agent_memory api core observability skills tools tests
uvx ruff check agent agent_memory api core observability skills tools tests --select F
uvx vulture agent agent_memory api core observability skills tools --min-confidence 80
uv run python -m unittest discover -s tests -v
cd ui
npm run build
```

## 新增能力的推荐步骤

1. 先在 `tools/` 新增工具函数。
2. 在 `skills/` 新增或更新 `SKILL.md`，说明使用场景和边界。
3. 在对应子 Agent 配置中接入工具。
4. 如果需要前端入口，再新增 `api/services/`、`api/routers/`、`ui/src/api/` 和前端组件。
5. 增加最小测试，至少覆盖工具函数或 service 边界。
