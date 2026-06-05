import os
from pathlib import Path
from langchain.chat_models import init_chat_model
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv, find_dotenv

# 加载环境变量
load_dotenv(find_dotenv())

# ======================== 1. 设置 Backend ========================
# 使用 FilesystemBackend 连接到本地文件系统
# 假设 skills 目录在当前脚本同级目录下的 skills/ 中
current_dir = Path(__file__).parent.parent.resolve()
# 我们将 root_dir 设置为当前目录 (base)
# 注意：FilesystemBackend 的 root_dir 是物理路径的根
fs_backend = FilesystemBackend(root_dir=current_dir,virtual_mode=True)

# ======================== 2. 初始化 Agent ========================
llm = init_chat_model(
    model="qwen-max",
    model_provider="openai"
)

# 创建带 Skill 的 Agent
agent = create_deep_agent(
    model=llm,
    # 关键点1：注入文件系统后端
    backend=fs_backend,
    # 关键点2：告诉 Agent 在 /skills/ 目录下查找技能
    # 这里的 /skills/ 是相对于 backend root_dir 的路径
    # 物理路径为: base/skills/
    skills=["skills"],
    checkpointer=MemorySaver(),
    # System Prompt 可以很通用，具体的专业指令由 Skill 提供
    system_prompt="你是一个有用的 AI 助手。"
)

# ======================== 3. 运行演示 ========================
def demo():
    # 查询技能
    result = agent.invoke({
        "messages": [
            {
                "role": "user",
                "content": "请查询我有哪些技能?帮我罗列出来!!!"
            }
        ]
    }, config={"configurable": {"thread_id": "demo_1"}})

    print(f"结果:{result['messages'][-1].content}")

    # 场景 1: 文本 -> Emoji   🛏️⏰,🚌🏃‍♀️,┏┛墓┗┓...(((m-__-)m
    query1 = "从前有一个女生，他叫李名娟，他说他是一只大老虎，但是其实他是一只小猫咪。使用emoji-translator技能翻译！"
    print(f"\n[用户]: {query1}")
    result1 = agent.invoke(
        {"messages": [{"role": "user", "content": query1}]},
        config={"configurable": {"thread_id": "demo_1"}}
    )
    print(f"[Agent]: {result1['messages'][-1].content}")

    # 场景 2: Emoji -> 文本
    query2 = "🌧️🏠☕📖 使用emoji-translator技能翻译！"
    print(f"\n[用户]: {query2}")
    result2 = agent.invoke(
        {"messages": [{"role": "user", "content": query2}]},
        config={"configurable": {"thread_id": "demo_2"}}
    )
    print(f"[Agent]: {result2['messages'][-1].content}")

if __name__ == "__main__":
    demo()