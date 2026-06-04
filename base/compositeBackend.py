# -*- coding: utf-8 -*-
import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StoreBackend
from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model
from langgraph.store.memory import InMemoryStore


load_dotenv(find_dotenv())

# 1. 准备 Store
# InMemoryStore 这里模拟数据库。程序退出后，数据会消失。
store = InMemoryStore()

# 2. 配置 LLM
llm = init_chat_model(
    model=os.getenv("LLM_QWEN_MAX"),
    model_provider="openai",
)

# 3. 定义混合后端
# 3.1 本地文件系统后端：普通文件默认写到 agent_workspace
workspace_dir = Path("./agent_workspace").resolve()
if not workspace_dir.exists():
    workspace_dir.mkdir(parents=True, exist_ok=True)

fs_backend = FilesystemBackend(
    root_dir=workspace_dir,
    virtual_mode=True,
)

# 3.2 Store 后端：专门保存 /store/ 开头的虚拟文件
# namespace 类似数据库表名，这里把 Store 里的虚拟文件统一放到 ("filesystem",) 下面。
store_backend = StoreBackend(
    namespace=lambda ctx: ("filesystem",),
)

# 3.3 组合后端：
# - 默认：走 fs_backend，保存到本地 agent_workspace
# - /store/ 开头：走 store_backend，保存到 InMemoryStore
composite_backend_instance = CompositeBackend(
    default=fs_backend,
    routes={
        "/store/": store_backend,
    },
)

# 4. 创建 Agent
agent = create_deep_agent(
    model=llm,
    store=store,
    backend=composite_backend_instance,
    tools=[],
    system_prompt="""
你是一个智能助手，可以使用文件工具保存内容。

存储规则：
1. 普通文件：直接写文件名，例如 /report.txt，会保存到本地 agent_workspace。
2. 长期记忆/虚拟文件：写到 /store/ 开头的路径，例如 /store/user_profile.txt，
   会保存到 InMemoryStore 模拟数据库里。
""",
)


if __name__ == "__main__":
    print(f"本地工作目录：{workspace_dir}")
    print("混合存储规则：")
    print("1. /report.txt -> 本地 agent_workspace/report.txt")
    print("2. /store/user_profile.txt -> InMemoryStore namespace=('filesystem',), key='/user_profile.txt'")

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "请做两件事："
                        "1. 写一份 Python 简介并保存到 /python_intro.md；"
                        "2. 把'我叫大风子，我的幸运数字是 7'保存到 /store/user_profile.txt。"
                    ),
                }
            ]
        }
    )

    print("\n=== Agent 输出 ===")
    print(result["messages"][-1].content)

    local_file = workspace_dir / "python_intro.md"
    print("\n=== 本地文件检查 ===")
    if local_file.exists():
        print(f"本地文件已生成：{local_file}")
        print(local_file.read_text(encoding="utf-8")[:200])
    else:
        print("本地文件没有生成。")

    stored_file = store.get(("filesystem",), "/user_profile.txt")
    print("\n=== InMemoryStore 检查 ===")
    print(stored_file.value if stored_file else "Store 里没有数据。")
