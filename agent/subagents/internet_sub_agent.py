from agent.load_prompt import sub_agent_configs
from tools.search import internet_search
from skills.registry import INTERNET_AGENT_SKILLS

# 定义互联网搜索子智能体的配置
internet_sub_agent = {
    "name": sub_agent_configs["tavily"]["name"],
    "description": sub_agent_configs["tavily"]["description"],
    "system_prompt": sub_agent_configs["tavily"]["system_prompt"],
    "tools": [internet_search],
    "skills": INTERNET_AGENT_SKILLS,

    # model 默认使用主智能体的模型配置，如果需要单独配置，可以在这里添加 model 字段
}

# 这个包对外只暴露 internet_sub_agent。其他子智能体在各自的模块中定义和暴露。
__all__ = ["internet_sub_agent"]
