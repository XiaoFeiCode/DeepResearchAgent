# 开发与验证

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
uv run python -m compileall -q agent agent_memory api ragflow skills tools utils tests
uv run python -m unittest discover -s tests -v
cd ui
npm run build
```

## 新增能力的推荐步骤

1. 先在 `tools/` 新增工具函数。
2. 在 `skills/` 新增或更新 `SKILL.md`，说明使用场景和边界。
3. 在对应子 Agent 配置中接入工具。
4. 如果需要前端入口，再新增 `api/services/`、`api/routers/` 和前端组件。
5. 增加最小测试，至少覆盖工具函数或 service 边界。

