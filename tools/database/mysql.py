from typing import Any

from langchain_core.tools import tool
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

from api.monitor import monitor
from core.settings import get_settings

# SQLModel 底层仍然使用 SQLAlchemy Engine。这里先设为 None，
# 等真正调用数据库工具时再初始化，避免导入模块阶段就强制连接/校验数据库配置。
_engine = None


def get_database_url() -> str:
    """从统一配置生成 MySQL 连接 URL。"""
    return get_settings().mysql_url()


def get_engine():
    """获取全局数据库 Engine，并使用懒加载避免重复创建连接池。"""
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_database_url(),
            # 连接池中常驻连接数，避免每次工具调用都重新建立 MySQL 连接。
            pool_size=5,
            # 高峰期允许临时额外创建的连接数。
            max_overflow=10,
            # 使用连接前先探活，避免拿到已被 MySQL 服务端断开的旧连接。
            pool_pre_ping=True,
        )
    return _engine


def list_table_names(session: Session) -> list[str]:
    """查询当前数据库中所有表名。"""
    result = session.exec(text("SHOW TABLES"))
    return [row[0] for row in result.all()]


def quote_identifier(identifier: str) -> str:
    """安全包装 MySQL 标识符，例如表名或字段名。"""
    return f"`{identifier.replace('`', '``')}`"


def result_to_dict(columns: list[str], rows: list[Any]) -> dict[str, Any]:
    """把 SQLAlchemy Row 结果转换成普通 dict/list，方便 Agent 和前端 JSON 化。"""
    return {
        "columns": columns,
        "rows": [list(row) for row in rows],
    }


def ensure_select_query(query: str) -> str:
    """只允许执行只读 SELECT 查询，防止 Agent 修改或删除数据库数据。"""
    sql = query.strip().rstrip(";")
    if not sql:
        raise ValueError("SQL query cannot be empty.")

    if not sql.lower().startswith("select"):
        raise ValueError("Only SELECT queries are allowed.")

    return sql


@tool
def list_sql_tables() -> str:
    """列出当前 MySQL 数据库中的所有数据表。"""
    # 上报工具调用事件，前端可以通过 WebSocket 看到数据库工具正在执行。
    monitor.report_tool(tool_name="列出数据库表工具", args={})

    # SQLModel 的 Session 负责管理一次数据库会话；with 退出时会自动释放连接。
    with Session(get_engine()) as session:
        table_names = list_table_names(session)

    if not table_names:
        return "数据库中没有找到数据表."

    return f"可用的数据库表: {', '.join(table_names)}"


@tool
def get_table_data(table_name: str) -> dict[str, Any] | str:
    """读取指定数据表的前 100 行，用于快速预览字段和样例数据。"""
    monitor.report_tool(tool_name="读取数据表内容工具", args={"table_name": table_name})

    with Session(get_engine()) as session:
        # 表名不能像普通值一样参数化绑定，所以先用 SHOW TABLES 做白名单校验。
        table_names = list_table_names(session)
        if table_name not in table_names:
            return f"表 '{table_name}' 不存在. 可用的表: {', '.join(table_names)}"

        # 通过白名单校验后再拼接表名，并用反引号处理特殊表名。
        quoted_table_name = quote_identifier(table_name)
        result = session.exec(text(f"SELECT * FROM {quoted_table_name} LIMIT 100"))
        columns = list(result.keys())
        rows = result.all()

    if not rows:
        return f"表 '{table_name}' 没有数据."

    return result_to_dict(columns, rows)


@tool
def execute_sql_query(query: str) -> dict[str, Any] | str:
    """执行自定义只读 SQL 查询，仅允许 SELECT。"""
    monitor.report_tool(tool_name="执行自定义 SQL 查询工具", args={"query": query})

    # 先做只读限制，再交给数据库执行，避免执行 UPDATE/DELETE/DROP 等危险语句。
    sql = ensure_select_query(query)
    try:
        with Session(get_engine()) as session:
            result = session.exec(text(sql))
            columns = list(result.keys())
            rows = result.all()
    except SQLAlchemyError as e:
        try:
            with Session(get_engine()) as session:
                table_names = list_table_names(session)
        except SQLAlchemyError:
            table_names = []

        table_hint = f" 当前可用表: {', '.join(table_names)}。" if table_names else ""
        return (
            f"SQL 查询执行失败: {e}。"
            f"{table_hint}"
            "请先调用 list_sql_tables 确认真实表名，再调用 get_table_data 预览字段，"
            "不要凭空假设表名或字段名。"
        )

    if not rows:
        return f"查询未返回任何行: {sql}"

    return result_to_dict(columns, rows)
