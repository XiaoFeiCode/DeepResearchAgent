# 记忆设计说明

项目里有三类“记忆”，它们职责不同，不能混用。

## 短期记忆：Redis Checkpointer

短期记忆保存同一个 `thread_id` 下的 Agent 运行状态，包括消息上下文、任务步骤、工具调用状态和执行断点。

核心链路：

```text
前端 sessionStorage 保存 thread_id
  -> /api/task 传给后端
  -> run_deep_agent(configurable.thread_id)
  -> Redis Checkpointer 恢复或写入该线程状态
```

特点：

- 作用范围是一个 `thread_id`。
- 前后端重启后，只要 Redis 数据还在、`thread_id` 不变，就能继续恢复。
- 点击“新会话”会生成新的 `thread_id`，从而获得新的短期上下文。
- TTL 由 `REDIS_CHECKPOINT_TTL_MINUTES` 控制。

## 长期记忆：Milvus

长期记忆保存跨会话可复用的信息，例如用户偏好、规则、策略、模板和历史结论。

保存字段：

- `user_id`
- `memory_type`
- `content`
- `source_thread_id`
- `created_at`
- `vector`

每次新任务开始时，后端会用当前问题检索当前用户的长期记忆，并把相关结果注入到主 Agent prompt 中。长期记忆不依赖当前 `thread_id`，而是按 `user_id` 隔离。

## 聊天记录：MySQL

MySQL 保存前端可恢复的聊天记录，主要服务于 UI：

- 会话列表
- 刷新页面后的消息恢复
- 登录用户的会话隔离

它不是 Agent 推理时的核心上下文。Agent 真正恢复运行状态靠 Redis Checkpointer；跨会话经验靠 Milvus。

## 选择建议

| 数据类型 | 存储位置 |
| --- | --- |
| 当前对话上下文、任务计划、执行断点 | Redis |
| 稳定偏好、规则、策略、历史结论 | Milvus |
| 前端聊天列表和消息展示 | MySQL |
| 用户上传文件、报告产物 | `updated/`、`output/` |

