from langchain.chat_models import init_chat_model
from deepagents import create_deep_agent
import os
from dotenv import load_dotenv, find_dotenv
import json

load_dotenv(find_dotenv())

# 极简初始化（自动读取OPENAI环境变量）
llm = init_chat_model(
    model=os.getenv("LLM_QWEN_MAX"),
    temperature=0.1,  # 自定义温度（更严谨的回答）
    model_provider="openai"
)

# 1. 定义子智能体：天气助手
weather_agent = {
    "name": "weather_helper",
    "description": "用于查询天气信息。当用户询问天气时，请调用此助手。",
    "system_prompt": "你是一个天气助手。无论用户问哪个城市的天气，你都统一回答：'今日天气晴朗，气温 25 度，适合出游。'",
    "tools": []  # 这里不需要额外工具，仅靠 prompt 回复
}

# 2. 定义子智能体：计算助手
math_agent = {
    "name": "math_helper",
    "description": "用于处理数学计算问题。",
    "system_prompt": "你是一个严谨的数学助手。请帮助用户计算数学问题。",
    "tools": []
}

# 3. 定义子智能体：翻译助手
translate_agent = {
    "name": "translator",
    "description": "用于中英互译任务。",
    "system_prompt": "你是一个翻译助手。如果是中文请翻译成英文，如果是英文请翻译成中文。",
    "tools": []
}

# 4. 创建主智能体，并注册子智能体
main_agent = create_deep_agent(
    model=llm,
    tools=[],  # 主智能体本身不带工具，依靠子智能体
    subagents=[weather_agent, math_agent, translate_agent],
    system_prompt="你是一个全能管家。你会根据用户的需求，调度不同的助手来解决问题。"
)


# 5. 可视化运行 (Stream)
# 使用 stream() 替代 invoke()，可以实时打印出智能体的“调度”过程，看到它如何分发任务
def test_stream(query):
    print(f"\n>>> 提问: {query}")
    # 遍历流式输出
    for chunk in main_agent.stream({"messages": [{"role": "user", "content": query}]}):
        # chunk 是一个字典，键是节点名 (如 'model', 'tools')，值是该节点的状态更新
        for node_name, state in chunk.items():
            if not state or "messages" not in state: continue
            messages = state["messages"]
            if messages and isinstance(messages, list):
                last_msg = messages[-1]
                # 1. 模型节点 (model)：决定下一步行动
                if node_name == "model":
                    # 如果有 tool_calls，说明模型决定调用工具或子智能体
                    if last_msg.tool_calls:
                        for tool_call in last_msg.tool_calls:
                            if tool_call['name'] == 'task':
                                sub_agent = tool_call['args'].get('subagent_type')
                                print(f"[模型决策] 呼叫子智能体: {sub_agent}")
                            else:
                                print(f"[模型决策] 调用工具: {tool_call['name']},参数为：{tool_call['args']}")
                    # 如果没有 tool_calls 且有 content，说明是最终回复
                    elif last_msg.content:
                        print(f"[最终回复] {last_msg.content}")

                # 2. 工具节点 (tools)：显示工具/子智能体的执行结果
                elif node_name == "tools":
                    content_preview = ''
                    if len(last_msg.content) > 100:
                        # 取前100个字符 + 省略号（截断预览）
                        content_preview = last_msg.content[:100] + "..."
                    else:
                        # 内容较短，直接完整显示
                        content_preview = last_msg.content
                    print(f"[执行结果] {content_preview}")
test_stream("北京今天天气怎么样？")
test_stream("100 + 256 等于多少？")