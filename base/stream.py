from typing import Literal

from langchain.chat_models import init_chat_model
from deepagents import create_deep_agent
from dotenv import find_dotenv, load_dotenv
from langchain_core.tools import tool
from tavily import TavilyClient

import os
from pprint import pformat

# 使用 find_dotenv() 自动查找 .env 文件，无论你在哪个目录下运行脚本都能正确加载环境变量
load_dotenv(find_dotenv())

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


@tool
def internet_search(
    query: str,
    max_results: int = 10,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """
    互联网搜索工具！
    :param query: 搜索关键字
    :param max_results: 返回结果数量
    :param topic: 主题类型
    :param include_raw_content: False精简 True 返回详细结果
    :return: 搜索结果列表
    """
    print(
        f"进行网络搜索！搜索条件：{query},"
        f"搜索主题类别:{topic},"
        f"搜索最大的条数：{max_results}"
    )
    return tavily_client.search(
        query=query,
        max_results=max_results,
        topic=topic,
        include_raw_content=include_raw_content,
    )


# 极简初始化（自动读取OPENAI环境变量）
llm = init_chat_model(
    model=os.getenv("LLM_QWEN_MAX"),
    model_provider="openai"
)

# 功能等价于langchain的 create_agent
deep_agent = create_deep_agent(
    model=llm,
    tools=[internet_search],
    subagents=[],
    system_prompt="""
      你是一位专家级研究员。你的任务是进行深入研究并撰写一份精美的报告。
      你有权使用 internet_search 工具来收集信息。
    """
)


def print_message(node_name, message):
    message_type = message.__class__.__name__
    content = getattr(message, "content", "")
    tool_calls = getattr(message, "tool_calls", None) or []

    print(f"\n本次处理的节点类型：{node_name}")
    print(f"消息类型：{message_type}")

    if node_name == "tools" or message_type == "ToolMessage":
        tool_name = getattr(message, "name", None)
        tool_call_id = getattr(message, "tool_call_id", None)
        print("节点分类：工具返回")
        if tool_name:
            print(f"工具名称：{tool_name}")
        if tool_call_id:
            print(f"工具调用ID：{tool_call_id}")
    else:
        print("节点分类：模型输出")

    if tool_calls:
        print("模型准备调用的工具：")
        for index, tool_call in enumerate(tool_calls, start=1):
            if isinstance(tool_call, dict):
                name = tool_call.get("name")
                args = tool_call.get("args")
                tool_id = tool_call.get("id")
            else:
                name = getattr(tool_call, "name", None)
                args = getattr(tool_call, "args", None)
                tool_id = getattr(tool_call, "id", None)

            print(f"  {index}. 工具名称：{name}")
            if tool_id:
                print(f"     工具调用ID：{tool_id}")
            print(f"     工具参数：{pformat(args, width=120)}")

    if content:
        print("消息内容：")
        print(content if isinstance(content, str) else pformat(content, width=120))
    else:
        print("消息内容：<空>")


prompt = input("输入你关系的问题：")
final_answer = None
for chunk in deep_agent.stream(
    {
        "messages": [
            {"role": "user", "content": prompt}
        ]
    },
    stream_mode="updates",
):
    for node_name, state in chunk.items():
        # 如果 state 为空，或者 state 里面没有 messages 的话，跳过
        if not state or "messages" not in state:
            continue

        messages = state["messages"]
        if not messages:
            continue

        last_msg = messages[-1]
        print_message(node_name, last_msg)

        content = getattr(last_msg, "content", "")
        if last_msg.__class__.__name__ == "AIMessage" and content:
            final_answer = content

"""
结果数据说明
 {
    "messages": [
        # 第0条：你的提问（HumanMessage）
        HumanMessage(content='搜索宇树机器人的新闻！'),
        # 第1条：Agent 调用工具的指令（AIMessage，内容为空，仅触发工具）
        AIMessage(content='', tool_calls=[{'name':'internet_search', ...}]),
        # 第2条：工具返回的搜索结果（ToolMessage，一堆JSON数据）
        ToolMessage(content='{"query":"宇树机器人 新闻","results":[...]}'),
        # 第3条：Agent 整理后的最终回复（AIMessage，这是你要的内容）
        AIMessage(content='以下是关于宇树机器人的一些最新新闻：...')
    ]
}
"""
if final_answer:
    print("\n最终回答：")
    print(final_answer)
else:
    print("\n没有收到模型最终回答。")
