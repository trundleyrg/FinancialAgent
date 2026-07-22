"""
DuckDB 数据库初始化脚本

功能：
1. 检查 DUCKDB_DB_PATH 配置的 DuckDB 文件是否存在、是否可连接
2. 按 src/db/models.py 中的 Peewee 模型创建所有表
3. 打印数据库文件路径、大小、表清单
4. 支持 --reset 选项：先 drop 后重建

使用方法：
    # 1. 默认初始化（使用 .env 中 DUCKDB_DB_PATH，无则用默认路径 ./data/db/financial_data.duckdb）
    python script/init_duckdb.py

    # 2. 指定路径初始化
    python script/init_duckdb.py --path ./data/db/financial_data.duckdb

    # 3. 删除并重建（清空全部表与数据）
    python script/init_duckdb.py --reset

    # 4. 仅检查连接（不修改任何文件）
    python script/init_duckdb.py --check

    # 5. 列出已存在的表
    python script/init_duckdb.py --list

与 src/db/db_connector.py 共用底层建表逻辑；与 script/init_postgresql_db.py 风格保持对称。
"""
import argparse
import os
import sys
from pathlib import Path

# 让脚本可以直接 python script/init_duckdb.py 运行（无需 PYTHONPATH）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

from src.utils.logger import db_logger  # noqa: E402
from src.db.models import (  # noqa: E402
    FinancialReport, FinancialMetric, ShareStructure,
    ConsolidatedBalanceSheet, ParentCompanyBalanceSheet,
    ConsolidatedIncomeStatement, ParentCompanyIncomeStatement,
    ConsolidatedCashFlowStatement, ParentCompanyCashFlowStatement,
)
from src.db.db_connector import get_db, DatabaseConnector  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

# 与 ui/backend/core/config.py 保持一致的默认路径
DEFAULT_DUCKDB_PATH = PROJECT_ROOT / "data" / "db" / "financial_data.duckdb"

# 用于按顺序展示（外键依赖靠前）
ALL_MODELS = [
    FinancialReport,
    FinancialMetric,
    ShareStructure,
    ConsolidatedBalanceSheet,
    ParentCompanyBalanceSheet,
    ConsolidatedIncomeStatement,
    ParentCompanyIncomeStatement,
    ConsolidatedCashFlowStatement,
    ParentCompanyCashFlowStatement,
]


def get_db_path(args_path: str = None) -> Path:
    """从 CLI 参数 / 环境变量 / 默认值 解析 DuckDB 文件路径。"""
    if args_path:
        return Path(args_path).expanduser().resolve()
    env_path = os.getenv("DUCKDB_DB_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return DEFAULT_DUCKDB_PATH


def format_size(num_bytes: int) -> str:
    """人类可读的文件大小。"""
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} TB"


def check_connection(db_path: Path) -> bool:
    """尝试连接 DuckDB，验证文件可读。"""
    import duckdb

    if not db_path.exists():
        db_logger.error(f"数据库文件不存在: {db_path}")
        return False
    try:
        conn = duckdb.connect(str(db_path), read_only=True)
        result = conn.execute("SELECT 1").fetchone()
        conn.close()
        if result and result[0] == 1:
            db_logger.info(f"连接成功: {db_path}")
            return True
        db_logger.error("连接测试失败：SELECT 1 返回异常")
        return False
    except Exception as e:
        db_logger.error(f"连接失败: {type(e).__name__}: {e}")
        return False


def list_tables(db_path: Path) -> int:
    """列出数据库中已有的表及其行数。返回表数量。"""
    import duckdb

    if not db_path.exists():
        db_logger.warning(f"数据库文件不存在: {db_path}")
        return 0

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        db_logger.info("数据库中无任何表")
        return 0

    db_logger.info(f"数据库 {db_path} 中已存在 {len(rows)} 张表：")
    for (table_name,) in rows:
        db_logger.info(f"  - {table_name}")
    return len(rows)


def init_database(db_path: Path, reset: bool = False) -> bool:
    """初始化数据库：必要时 reset，再按 models.py 建表。"""
    # 确保父目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 如果文件存在但已损坏，主动删除以便重建
    if db_path.exists() and not _is_valid_duckdb_file(db_path):
        db_logger.warning(f"现有 DuckDB 文件损坏，将被删除重建: {db_path}")
        _remove_db_file(db_path)

    if reset:
        if db_path.exists():
            db_logger.warning(f"[--reset] 删除现有 DuckDB 文件: {db_path}")
            _remove_db_file(db_path)
        else:
            db_logger.info(f"[--reset] 数据库文件不存在，无需删除: {db_path}")

    # 通过 DatabaseConnector 完成建表（与项目其它入口一致）
    db_logger.info("正在创建/校验数据表 ...")
    db = None
    try:
        # 临时设置 DUCKDB_DB_PATH 以便 get_db() 使用目标路径
        os.environ["DUCKDB_DB_PATH"] = str(db_path)
        db = DatabaseConnector(database_type="duckdb")
        if reset:
            db.drop_tables()
        db.create_tables()
    except Exception as e:
        db_logger.error(f"建表失败: {type(e).__name__}: {e}")
        return False
    finally:
        # 关键：必须先关闭 DatabaseConnector 的连接，否则下方 list_tables
        # 用 read_only 打开同一文件会触发 DuckDB 的多连接冲突
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    if not db_path.exists():
        db_logger.error("建表过程未生成数据库文件")
        return False

    db_logger.info(f"数据库初始化完成: {db_path} ({format_size(db_path.stat().st_size)})")
    list_tables(db_path)
    return True


def _is_valid_duckdb_file(db_path: Path) -> bool:
    """快速检测 .duckdb 文件是否可被 duckdb 正常打开。"""
    import duckdb

    try:
        conn = duckdb.connect(str(db_path))
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return True
    except Exception:
        return False


def _remove_db_file(db_path: Path) -> None:
    """删除 DuckDB 文件及其 WAL/SHM 临时文件。"""
    for suffix in ("", ".wal", ".wal.tmp"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()


def main():
    parser = argparse.ArgumentParser(description="DuckDB 数据库初始化脚本")
    parser.add_argument(
        "--path",
        help="DuckDB 文件路径（默认读 .env 的 DUCKDB_DB_PATH，否则 ./data/db/financial_data.duckdb）",
    )
    parser.add_argument("--reset", action="store_true", help="删除现有数据库文件后重建")
    parser.add_argument("--check", action="store_true", help="仅测试连接与文件有效性，不修改任何内容")
    parser.add_argument("--list", action="store_true", help="列出当前数据库中已存在的表")
    parser.add_argument(
        "--models",
        action="store_true",
        help="打印 src/db/models.py 中定义的所有模型类清单（用于交叉校验）",
    )
    args = parser.parse_args()

    db_path = get_db_path(args.path)

    db_logger.info("=" * 60)
    db_logger.info("DuckDB 数据库初始化")
    db_logger.info("=" * 60)
    db_logger.info(f"目标路径: {db_path}")
    db_logger.info(f"路径存在: {db_path.exists()}")
    db_logger.info("=" * 60)

    if args.check:
        ok = check_connection(db_path)
        if ok:
            list_tables(db_path)
        sys.exit(0 if ok else 1)

    if args.list:
        n = list_tables(db_path)
        sys.exit(0 if (n > 0 or db_path.exists()) else 1)

    if args.models:
        db_logger.info("models.py 中定义的 ORM 模型：")
        for m in ALL_MODELS:
            db_logger.info(f"  - {m.__name__:40s} -> {m._meta.table_name}")
        sys.exit(0)

    ok = init_database(db_path, reset=args.reset)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()