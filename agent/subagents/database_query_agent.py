from agent.load_prompt import sub_agent_configs
from tools.database import execute_sql_query, get_table_data, list_sql_tables


database_query_agent = {
    "name": sub_agent_configs["db"]["name"],
    "description": sub_agent_configs["db"]["description"],
    "system_prompt": sub_agent_configs["db"]["system_prompt"],
    "tools": [list_sql_tables, get_table_data, execute_sql_query],
    # model 默认使用主智能体的模型配置，如果需要单独配置，可以在这里添加 model 字段
}

# 这个包对外只暴露 database_query_agent。其他子智能体在各自的模块中定义和暴露。
__all__ = ["database_query_agent"]
