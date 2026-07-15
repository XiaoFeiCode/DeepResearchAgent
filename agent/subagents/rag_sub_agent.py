from agent.load_prompt import sub_agent_configs
from tools.ragflow import (
    create_ask_delete,
    create_ragflow_dataset,
    delete_ragflow_documents,
    get_assistant_list,
    inspect_ragflow_knowledge_base,
    list_ragflow_datasets,
    list_ragflow_documents,
    parse_ragflow_documents,
    setup_ragflow_knowledge_base,
    upload_ragflow_documents,
    search_ragflow_document_images,
)
from tools.multimodal import analyze_image
from skills.registry import RAGFLOW_AGENT_SKILLS

ragflow_config = sub_agent_configs["ragflow"]

rag_sub_agent = {
    "name": ragflow_config.get("name", ""),
    "description": ragflow_config.get("description", ""),
    "system_prompt": ragflow_config.get("system_prompt", ""),
    # RAGFlow 既负责向已有助手提问，也负责知识库和文档的基础管理。
    "tools": [
        get_assistant_list,
        create_ask_delete,
        list_ragflow_datasets,
        create_ragflow_dataset,
        list_ragflow_documents,
        upload_ragflow_documents,
        parse_ragflow_documents,
        delete_ragflow_documents,
        inspect_ragflow_knowledge_base,
        setup_ragflow_knowledge_base,
        analyze_image,
        search_ragflow_document_images,
    ],
    "skills": RAGFLOW_AGENT_SKILLS,
}

# 这个包对外只暴露 rag_sub_agent，其他子智能体在各自模块中定义。
__all__ = ["rag_sub_agent"]
