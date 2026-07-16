import base64
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Annotated, Any

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from api.context import get_session_context
from api.monitor import monitor
from core.settings import get_settings

SUPPORTED_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _max_image_bytes() -> int:
    """读取单张图片大小上限，默认 10 MB。"""
    max_mb = get_settings().vision_max_image_mb
    return max(1, int(max_mb * 1024 * 1024))


def _resolve_image_path(image_path: str, session_dir: str | None) -> Path:
    """把 Agent 给出的本地或 Daytona 路径安全映射到当前会话目录。"""
    if not session_dir:
        raise ValueError("当前任务没有绑定会话目录，无法读取图片")

    session_root = Path(session_dir).resolve()
    normalized = image_path.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("图片路径不能为空")

    # Agent 在 Daytona 中看到的是远程路径，实际工具运行在后端主机，
    # 因此把远程工作区路径映射回当前会话目录。
    remote_prefix = "/home/daytona/workspace/"
    if normalized.startswith(remote_prefix):
        candidate = session_root / normalized.removeprefix(remote_prefix)
    else:
        raw_path = Path(normalized)
        if raw_path.is_absolute():
            candidate = raw_path
        else:
            parts = PurePosixPath(normalized).parts
            if session_root.name in parts or (parts and parts[0] == "output"):
                candidate = session_root / PurePosixPath(normalized).name
            else:
                candidate = session_root / Path(*parts)

    resolved = candidate.resolve()
    if not resolved.is_relative_to(session_root):
        raise PermissionError("只能分析当前会话工作目录中的图片")
    if not resolved.is_file():
        raise FileNotFoundError(f"图片不存在: {image_path}")

    suffix = resolved.suffix.lower()
    if suffix not in SUPPORTED_IMAGE_TYPES:
        supported = ", ".join(sorted(SUPPORTED_IMAGE_TYPES))
        raise ValueError(f"不支持的图片格式 {suffix or '(无后缀)'}，当前支持: {supported}")

    size = resolved.stat().st_size
    if size <= 0:
        raise ValueError("图片文件为空")
    if size > _max_image_bytes():
        raise ValueError(
            f"图片大小为 {size / 1024 / 1024:.1f} MB，超过 "
            f"{_max_image_bytes() / 1024 / 1024:.1f} MB 限制"
        )

    _verify_image_signature(resolved, suffix)
    return resolved


def _verify_image_signature(image_path: Path, suffix: str) -> None:
    """检查常见图片文件头，避免把任意文件伪装成图片发送给模型。"""
    header = image_path.read_bytes()[:16]
    valid = {
        ".png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": header.startswith(b"\xff\xd8\xff"),
        ".jpeg": header.startswith(b"\xff\xd8\xff"),
        ".webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP",
    }[suffix]
    if not valid:
        raise ValueError("图片文件内容与扩展名不匹配，无法分析")


def _build_data_url(image_path: Path) -> str:
    """把本地图片转换成 OpenAI 兼容接口接受的内联 Data URL。"""
    mime_type = SUPPORTED_IMAGE_TYPES[image_path.suffix.lower()]
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


@lru_cache(maxsize=1)
def get_vision_model() -> ChatOpenAI:
    """按需创建视觉模型客户端，避免项目启动时强制连接模型服务。"""
    settings = get_settings()
    model_name, base_url, api_key = settings.require_vision_credentials()

    return ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        timeout=settings.vision_request_timeout_seconds,
        max_retries=2,
    )


def _response_text(response: Any) -> str:
    """兼容字符串和标准内容块两种视觉模型返回格式。"""
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(part.strip() for part in parts if part.strip())
    return str(content).strip()


async def analyze_image_file(
    image_path: str,
    question: str,
    *,
    model: Any | None = None,
    session_dir: str | None = None,
) -> str:
    """执行图片分析的核心逻辑，独立出来便于测试。"""
    resolved = _resolve_image_path(
        image_path,
        session_dir if session_dir is not None else get_session_context(),
    )
    message = HumanMessage(
        content=[
            {"type": "text", "text": question.strip() or "请描述这张图片的关键信息。"},
            {
                "type": "image_url",
                "image_url": {"url": _build_data_url(resolved)},
            },
        ]
    )
    response = await (model or get_vision_model()).ainvoke([message])
    result = _response_text(response)
    if not result:
        raise RuntimeError("视觉模型没有返回可用的文本结果")
    return result


@tool
async def analyze_image(
    image_path: Annotated[str, "当前会话中图片的文件名或路径，支持 PNG、JPEG、WebP"],
    question: Annotated[str, "希望视觉模型重点识别或分析的问题"],
) -> str:
    """分析用户上传的图片，可用于看图描述、OCR、界面解读和故障现象识别。"""
    monitor.report_tool(
        tool_name="图片分析工具",
        args={"image_path": image_path, "question": question},
    )
    try:
        return await analyze_image_file(image_path, question)
    except Exception as error:
        return f"图片分析失败: {error}"
