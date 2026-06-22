import uuid
import asyncio
import uvicorn
from pathlib import Path
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import shutil

# 根据项目结构调整导入路径
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import agent runner and monitor
# 注意：agent.main_agent 导入时会初始化 main_agent，这可能需要几秒钟
from agent.main_agent import close_main_agent_resources, run_deep_agent
from api.monitor import manager
from tools.ragflow.base import (
    _find_dataset,
    _find_documents,
    _format_ragflow_error,
    _get_id,
    _get_name,
    _get_value,
    get_ragflow_client,
)

app = FastAPI(title="DeepAgents API")

# 挂载输出目录，以便前端访问生成的静态文件
# 假设输出目录位于项目根目录下的 output
output_dir = project_root / "output"
output_dir.mkdir(exist_ok=True)

# 定义上传目录 updated
updated_dir = project_root / "updated"
updated_dir.mkdir(exist_ok=True)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """
    服务启动时，获取当前运行的事件循环，并绑定到 WebSocket 管理器。
    确保后台线程能通过 run_coroutine_threadsafe 准确投递消息。
    """
    loop = asyncio.get_running_loop()
    manager.set_loop(loop)
    print(f"[Server] WebSocket Manager bound to loop: {id(loop)}")


@app.on_event("shutdown")
async def shutdown_event():
    """服务关闭时释放 Agent 运行时资源。"""
    await close_main_agent_resources()


class TaskRequest(BaseModel):
    query: str
    thread_id: str = None


class RagflowDocumentRequest(BaseModel):
    dataset_name_or_id: str
    document_names_or_ids: str


def _ragflow_dataset_payload(dataset):
    """把 RAGFlow SDK 对象整理成前端容易消费的字典。"""
    return {
        "id": _get_id(dataset),
        "name": _get_name(dataset, "未知知识库"),
        "description": _get_value(dataset, "description", "") or "",
        "doc_num": _get_value(dataset, "doc_num", 0),
        "chunk_num": _get_value(dataset, "chunk_num", 0),
        "language": _get_value(dataset, "language", ""),
        "parser_id": _get_value(dataset, "parser_id", ""),
    }


def _ragflow_document_payload(document):
    """把 RAGFlow 文档对象整理成前端列表项。"""
    return {
        "id": _get_id(document),
        "name": _get_name(document, "未知文档"),
        "run": _get_value(document, "run", None),
        "progress": _get_value(document, "progress", None),
        "chunk_count": _get_value(document, "chunk_count", None),
        "token_count": _get_value(document, "token_count", None),
        "create_date": _get_value(document, "create_date", ""),
        "update_date": _get_value(document, "update_date", ""),
    }


@app.post("/api/task")
async def run_task(request: TaskRequest):
    """
    智能体任务启动接口 (Run Agent Task)。

    目标：
    1. 接收用户的自然语言指令。
    2. 在后台异步启动 Agent 执行逻辑。
    3. 返回会话 ID，供前端通过 WebSocket 订阅实时进度。

    执行步骤：
    1. 获取或生成 thread_id。
    2. 触发异步任务 (asyncio.create_task)。
    3. 立即返回响应，不阻塞 HTTP 线程。

    Args:
        request (TaskRequest): 包含用户 query 和可选 thread_id 的请求体。
    """
    # 1. [ID 初始化]
    thread_id = request.thread_id or str(uuid.uuid4())

    # 2. [后台执行] 异步运行 Agent，不阻塞主线程
    # 注意：这里简单的使用 asyncio.create_task 触发，由 main_agent 内部负责实时推送
    asyncio.create_task(run_deep_agent(request.query, thread_id))

    # 3. [立即响应]
    return {"status": "started", "thread_id": thread_id}


@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...), thread_id: str = Form(...)):
    """
    文件上传接口 (File Upload)。

    目标：
    1. 接收用户上传的一个或多个文件。
    2. 保存到 `updated/session_{thread_id}` 目录。
    3. 供 Agent 在后续任务中读取和分析。

    Args:
        files (List[UploadFile]): 文件对象列表。
        thread_id (str): 关联的任务会话 ID。
    """
    # 1. [目录准备] 确保上传目录存在
    target_dir = updated_dir / f"session_{thread_id}"
    target_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    # 2. [保存] 遍历并写入文件
    for file in files:
        file_path = target_dir / file.filename
        # 使用二进制模式写入，支持各种文件格式 (图片、PDF、文本等)
        # shutil.copyfileobj 高效复制文件流，避免一次性加载大文件到内存
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(file.filename)

    # 3. [响应] 返回成功保存的文件列表
    return {"status": "uploaded", "files": saved_files}


@app.get("/api/ragflow/datasets")
async def list_ragflow_dataset_api():
    """列出当前 RAGFlow 账号可见的知识库。"""
    try:
        client = get_ragflow_client()
        datasets = client.list_datasets(page=1, page_size=100)
        return {"datasets": [_ragflow_dataset_payload(dataset) for dataset in datasets]}
    except Exception as e:
        return {"error": f"获取 RAGFlow 知识库失败: {e}"}


@app.get("/api/ragflow/documents")
async def list_ragflow_document_api(dataset_name_or_id: str):
    """列出指定知识库中的文档。"""
    try:
        client = get_ragflow_client()
        dataset = _find_dataset(client, dataset_name_or_id)
        if dataset is None:
            return {"error": f"未找到知识库: {dataset_name_or_id}"}

        documents = dataset.list_documents(page=1, page_size=1000)
        return {
            "dataset": _ragflow_dataset_payload(dataset),
            "documents": [_ragflow_document_payload(document) for document in documents],
        }
    except Exception as e:
        return {"error": f"获取 RAGFlow 文档失败: {e}"}


@app.post("/api/ragflow/documents/upload")
async def upload_ragflow_document_api(
    files: List[UploadFile] = File(...),
    dataset_name_or_id: str = Form(...),
    parse_after_upload: bool = Form(True),
):
    """把前端选择的文件直接上传到指定 RAGFlow 知识库。"""
    try:
        client = get_ragflow_client()
        dataset = _find_dataset(client, dataset_name_or_id)
        if dataset is None:
            return {"error": f"未找到知识库: {dataset_name_or_id}"}

        document_list = [
            {"display_name": file.filename, "blob": file.file}
            for file in files
        ]
        documents = dataset.upload_documents(document_list)
        document_ids = [_get_id(document) for document in documents if _get_id(document)]

        parse_status = None
        if parse_after_upload and document_ids:
            parse_status = dataset.parse_documents(document_ids)

        return {
            "status": "uploaded",
            "dataset": _ragflow_dataset_payload(dataset),
            "documents": [_ragflow_document_payload(document) for document in documents],
            "parse_status": parse_status,
        }
    except Exception as e:
        return {"error": _format_ragflow_error("上传 RAGFlow 文档", e)}


@app.post("/api/ragflow/documents/parse")
async def parse_ragflow_document_api(request: RagflowDocumentRequest):
    """重新解析指定知识库中的文档。"""
    try:
        client = get_ragflow_client()
        dataset = _find_dataset(client, request.dataset_name_or_id)
        if dataset is None:
            return {"error": f"未找到知识库: {request.dataset_name_or_id}"}

        documents, missing = _find_documents(dataset, request.document_names_or_ids)
        if not documents:
            return {"error": f"未找到文档: {', '.join(missing)}"}

        document_ids = [_get_id(document) for document in documents if _get_id(document)]
        parse_status = dataset.parse_documents(document_ids)
        return {
            "status": "parsed",
            "parse_status": parse_status,
            "missing": missing,
        }
    except Exception as e:
        return {"error": f"解析 RAGFlow 文档失败: {e}"}


@app.post("/api/ragflow/documents/delete")
async def delete_ragflow_document_api(request: RagflowDocumentRequest):
    """删除指定知识库中的文档。"""
    try:
        client = get_ragflow_client()
        dataset = _find_dataset(client, request.dataset_name_or_id)
        if dataset is None:
            return {"error": f"未找到知识库: {request.dataset_name_or_id}"}

        documents, missing = _find_documents(dataset, request.document_names_or_ids)
        if not documents:
            return {"error": f"未找到文档: {', '.join(missing)}"}

        document_ids = [_get_id(document) for document in documents if _get_id(document)]
        dataset.delete_documents(ids=document_ids)
        return {
            "status": "deleted",
            "deleted": [_ragflow_document_payload(document) for document in documents],
            "missing": missing,
        }
    except Exception as e:
        return {"error": f"删除 RAGFlow 文档失败: {e}"}


@app.get("/api/download")
async def download_file(path: str):
    """
    文件下载接口 (File Download)。

    目标：
    1. 根据绝对路径下载文件。
    2. 严格的安全检查，防止越权访问。

    Args:
        path (str): 文件的绝对路径 (通常从 list_files 接口获取)。
    """
    # 1. [安全检查] 路径解析与越权校验
    try:
        abs_path = Path(path).resolve()
        output_abs = output_dir.resolve()

        # 必须确保请求的文件在 output 目录下
        if not abs_path.is_relative_to(output_abs):
            return {"error": "拒绝访问: 只能下载输出目录下的文件"}
    except Exception:
        return {"error": "无效的路径参数"}

    # 2. [存在性检查]
    if not abs_path.exists():
        return {"error": "文件不存在"}

    # 3. [响应] 返回文件流 (浏览器自动触发下载)
    return FileResponse(abs_path, filename=abs_path.name)


@app.get("/api/files")
async def list_files(path: str):
    """
    文件列表查询接口 (File Explorer)。

    目标：
    1. 列出指定目录下的所有生成文件。
    2. 提供文件元数据（大小、时间、下载链接）。
    3. 严格的安全检查，防止路径遍历攻击。

    Args:
        path (str): 目标目录的绝对路径 (必须在 output 目录下)。
    """
    # 1. [调试] 打印请求路径
    print(f"[DEBUG] 请求文件列表: {path}")

    try:
        # 2. [解析] 获取绝对路径对象
        abs_path = Path(path).resolve()
        output_abs = output_dir.resolve()

        # 3. [安全] 检查路径是否越界 (Path Traversal Check)
        if not abs_path.is_relative_to(output_abs):
            print(f"[ERROR] 拒绝访问: {abs_path} 不在 {output_abs} 目录下")
            return {"error": "拒绝访问: 只能访问输出目录下的文件"}

    except Exception as e:
        print(f"[ERROR] 路径解析失败: {e}")
        return {"error": f"路径无效: {e}"}

    # 4. [检查] 目录是否存在
    if not abs_path.exists():
        return {"error": "目录不存在"}

    files = []
    try:
        # 5. [遍历] 递归查找所有文件
        for file_path in abs_path.rglob("*"):
            if file_path.is_file():
                # 计算相对路径，生成下载 URL
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "type": "file",
                    "path": str(file_path),
                    # "url": f"/outputs/{url_path}",
                    "size": stat.st_size,
                    "mtime": stat.st_mtime
                })

    except Exception as e:
        print(f"[ERROR] 遍历文件失败: {e}")
        return {"error": str(e)}

    # 6. [排序] 按修改时间倒序排列 (最新的在前)
    files.sort(key=lambda x: x.get("mtime", 0), reverse=True)
    print(f"[DEBUG] 找到 {len(files)} 个文件")
    return {"files": files}

# 当浏览器请求 ws://localhost:8000/ws/thread_123 时：
# 1. 路由匹配 ：FastAPI 发现这个 URL 匹配了你写的 @app.websocket("/ws/{thread_id}") 。
# 2. 创建对象 ：FastAPI (基于 Starlette) 会立刻在 主事件循环 中实例化一个 WebSocket 对象。
#    - 这个对象封装了底层的 TCP 连接、HTTP 握手信息、以及后续的消息收发方法 ( send_text , receive_text 等)。
# 3. 注入参数 ：FastAPI 自动把这个刚创建好的 WebSocket 对象，作为参数传给你的 websocket_endpoint(websocket, ...) 函数。
@app.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    """
    WebSocket 实时通讯核心接口 (Real-time Communication)。

    目标：
    1. 建立长连接，实现服务端与前端的双向通信。
    2. 绑定 `thread_id`，实现会话级消息隔离。
    3. 维持心跳 (Keep-Alive)，防止连接超时。

    执行步骤：
    1. 握手：接受 WebSocket 连接请求。
    2. 注册：将连接实例绑定到 `monitor.manager`，关联 `thread_id`。
    3. 循环：进入消息监听循环，处理前端发送的心跳或指令。
    4. 异常：捕获断开连接异常，清理资源。

    Args:
        websocket (WebSocket): WebSocket 连接实例。
        thread_id (str): 当前会话的唯一标识。
    """
    # 1. [注册] 建立连接并绑定到管理器
    await manager.connect(websocket, thread_id)

    try:
        # 2. [循环] 保持连接活跃
        while True:
            # 3. [监听] 接收前端消息 (通常是 ping 心跳)
            data = await websocket.receive_text()

            # 4. [响应] 回复 pong 消息
            await websocket.send_json({
                "type": "pong",
                "message": f"服务端已收到: {data}"
            })

    except WebSocketDisconnect:
        # 5. [清理] 客户端主动断开
        manager.disconnect(websocket, thread_id)
        print(f"[WebSocket] 客户端已断开: {thread_id}")

    except Exception as e:
        # 6. [异常] 发生错误时断开
        print(f"[WebSocket] 连接异常: {e}")
        manager.disconnect(websocket, thread_id)


if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
