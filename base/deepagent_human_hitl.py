
import os
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver  # 内存检查点，用于保存中断状态
from langgraph.types import Command  # 恢复执行的指令类型
from dotenv import load_dotenv, find_dotenv

# 加载环境变量（DASHSCOPE_API_KEY等），优先查找当前目录的.env文件
load_dotenv(find_dotenv())


# ======================== 1. 定义工具函数 ========================
# 装饰器@tool将普通函数转为LangChain可调用工具，函数文档字符串会作为工具描述给Agent
@tool
def delete_database(table_name: str):
    """
    高危操作：删除数据库表
    :param table_name: 要删除的表名
    :return: 操作结果提示
    """
    print(f"[工具执行] 删除表: {table_name}")
    return f"已成功删除表: {table_name}"


@tool
def select_data(table_name: str):
    """
    普通操作：查询指定表名的数据（无需审批）
    :param table_name: 要查询的表名
    :return: 操作结果提示
    """
    print(f"[工具执行] 查询指定表名数据: {table_name}")
    return f"查询数据成功：{table_name}"


@tool
def delete_file(file_name: str):
    """
    高危操作：删除文件
    :param file_name: 要删除的文件路径/名称
    :return: 操作结果提示
    """
    print(f"[工具执行] 删除文件: {file_name}")
    return f"已成功删除文件: {file_name}"


# ======================== 2. 核心配置 ========================
# 配置检查点（必须）：保存Agent中断时的状态，确保恢复执行时能衔接上下文
# 注意：InMemorySaver仅用于测试，生产环境建议使用RedisCheckpointer等持久化方案
checkpointer = InMemorySaver()

# 初始化大模型（通义千问）
llm = init_chat_model(
    model=os.getenv("LLM_QWEN_MAX"),          # 模型名称（从环境变量读取）
    model_provider="openai"                   # 兼容OpenAI格式的接口
)


# 创建deepagent
deep_agent = create_deep_agent(
    model = llm,
    tools = [delete_database, delete_file, select_data],
     # 中断配置：指定调用以下工具前触发人工审批（高危操作管控）
    interrupt_on={"delete_database": True, "delete_file": True},
    checkpointer=checkpointer,                  # 绑定检查点（中断恢复必备）
    system_prompt="所有的回答都使用中文！！"     # 系统提示词，规范Agent输出语言
)

# ======================== 3. 执行流程 ========================
# 会话配置：通过thread_id绑定会话，确保中断/恢复在同一个会话中执行
thread_config = {"configurable": {"thread_id": "safe_thread_1"}}

print("\n=== 第一阶段：触发工具调用（规划阶段）===")
# 第一次调用：Agent会规划操作序列，但触发中断后不会执行任何工具
result_1 = deep_agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "先把用户表(users)删了！在查询product表数据！最后把 user.txt 文件也删除了！"
            }
        ]
    },
    config=thread_config  # 绑定会话ID，确保状态可追溯
)
print("当前状态：智能体已暂停，等待人工确认。")

# 提取中断信息（核心：审批操作列表）
interrupts = result_1.get("__interrupt__")

if interrupts:
    # 解析中断数据：Interrupt对象 → value字典 → action_requests列表
    action_requests = interrupts[0].value['action_requests']
    # 打印需要审批的操作数量和名称（用于人工审批界面展示）
    print(f"需要审核动作数量{len(action_requests)} , 输出结果: {[action_request['name'] for action_request in action_requests]} ")

    # 模拟人工审批决策（生产环境需替换为人工交互/审批系统接口）
    # 注意：decisions顺序必须和action_requests一致
    decisions = [
        {"type": "reject"},  # 审批结果1：同意删除数据库表（delete_database）
        {"type": "reject"}    # 审批结果2：拒绝删除文件（delete_file）
    ]

    # 第二次调用：恢复执行，Agent会按审批结果执行操作
    result = deep_agent.invoke(
        # Command(resume)是DeepAgents专用的恢复指令
        Command(resume={
            "decisions": decisions  # 传入人工审批结果
        }),
        config=thread_config  # 必须使用同一个thread_id，否则无法恢复状态
    )

    # 打印最终执行结果（Agent的最终回复）
    print("\n=== 执行结果 ===")
    print(result["messages"][-1].content)