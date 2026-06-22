from pathlib import Path

import yaml

# 1. 当前脚本所在目录
current_dir = Path(__file__).parent.parent

# 2. 拼接 YAML 文件名
yml_path = current_dir / 'prompt' / 'prompts.yml'


# 3. 读取 yml 文件 r读
def load_yaml(file_path):
    """
    加载 YAML 文件。
    yml_path: YAML 文件路径
    """
    with open(file_path, "r", encoding="utf-8") as f:
        # 使用 yaml.safe_load() 解析 YAML 文件, 避免 YAML 漏洞
        config = yaml.safe_load(f)
    return config


prompts = load_yaml(yml_path)

main_agent_config = prompts["main_agent"]
main_config = main_agent_config["system_prompt"]
sub_agent_configs = prompts["sub_agents"]


if __name__ == "__main__":
    print("主智能体系统提示词：", main_config)
    print("子智能体配置：", sub_agent_configs)
