"""
PostgreSQL 数据库初始化脚本

功能：
1. 在 PostgreSQL 服务器上创建目标数据库（默认 'financial'，如已存在则跳过）
2. 通过 DatabaseConnector 在目标数据库中按 src/db/models.py 中的 Peewee 模型创建所有表
3. 打印数据库连接信息与建表清单

使用方法：
    # 默认（读 .env 中 POSTGRES_DB_URL / DATABASE=postgresql）
    python script/init_postgresql_db.py

    # 指定连接参数
    python script/init_postgresql_db.py --host localhost --port 5432 --user postgres --password postgres --dbname financial

    # 仅测试连接
    python script/init_postgresql_db.py --check-only

    # 重置（drop 全部表后重建，会清空数据）
    python script/init_postgresql_db.py --reset

与 src/db/db_connector.py 共用底层建表逻辑，与 script/init_duckdb.py 风格保持对称。
"""
import argparse
import os
import sys
from pathlib import Path

# 让脚本可直接 python script/init_postgresql_db.py 运行
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
from src.db.db_connector import DatabaseConnector  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")


def get_pg_config():
    """从 POSTGRES_DB_URL 解析或回退到独立环境变量。"""
    url = os.getenv("POSTGRES_DB_URL")
    if url:
        # postgresql://user:password@host:port/dbname
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return {
                "host": parsed.hostname or "localhost",
                "port": parsed.port or 5432,
                "user": parsed.username or "postgres",
                "password": parsed.password or "",
                "dbname": (parsed.path or "/").lstrip("/") or "financial",
            }
        except Exception as e:
            db_logger.warning(f"解析 POSTGRES_DB_URL 失败，回退到独立环境变量: {e}")

    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
        "dbname": os.getenv("DB_NAME", "financial"),
    }


def check_pg_connection(host: str, port: int, user: str, password: str, dbname: str | None) -> bool:
    """测试到 PostgreSQL 服务器的连通性（不要求目标库已存在）。"""
    try:
        import psycopg2
    except ImportError:
        db_logger.error("缺少依赖 psycopg2，请先运行 `pip install psycopg2-binary`")
        return False

    try:
        # 若指定了 dbname，则尝试连接到目标库；否则连到默认 postgres 库
        target_db = dbname or "postgres"
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=target_db,
            connect_timeout=10,
        )
        server_version = conn.server_version
        db_logger.info(f"连接成功：PostgreSQL 服务器版本 {server_version} @ {host}:{port}")
        conn.close()
        return True
    except Exception as e:
        db_logger.error(f"连接失败: {type(e).__name__}: {e}")
        return False


def create_database_if_not_exists(
    host: str, port: int, user: str, password: str, dbname: str
) -> bool:
    """创建目标数据库（若不存在）。通过连接到默认 postgres 库实现。"""
    try:
        import psycopg2
        from psycopg2 import sql
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    except ImportError:
        db_logger.error("缺少依赖 psycopg2，请先运行 `pip install psycopg2-binary`")
        return False

    db_logger.info(f"[步骤 1] 创建数据库 '{dbname}'（如不存在）...")
    try:
        conn = psycopg2.connect(
            host=host, port=port, user=user, password=password, dbname="postgres"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        cur.execute(
            sql.SQL("SELECT 1 FROM pg_database WHERE datname = {}").format(sql.Literal(dbname))
        )
        if cur.fetchone():
            db_logger.info(f"数据库 '{dbname}' 已存在，跳过创建")
        else:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
            db_logger.info(f"数据库 '{dbname}' 创建成功")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        db_logger.error(f"创建数据库失败: {type(e).__name__}: {e}")
        return False


def init_tables(host: str, port: int, user: str, password: str, dbname: str, reset: bool = False) -> bool:
    """通过 DatabaseConnector 创建/重建 Peewee 表。"""
    db_logger.info(f"[步骤 2] {'重建' if reset else '创建/校验'}数据表 ...")
    database_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    os.environ["DATABASE"] = "postgresql"
    os.environ["POSTGRES_DB_URL"] = database_url

    db = None
    try:
        db = DatabaseConnector(database_type="postgresql", database_url=database_url)
        if reset:
            db.drop_tables()
        db.create_tables()
    except Exception as e:
        db_logger.error(f"建表失败: {type(e).__name__}: {e}")
        return False
    finally:
        # PostgreSQL 连接由 Peewee 管理，DatabaseConnector.close() 仅处理 DuckDB 分支
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    # 列出现有表
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=host, port=port, user=user, password=password, dbname=dbname
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
        tables = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        if tables:
            db_logger.info(f"目标数据库 '{dbname}' 中已存在 {len(tables)} 张表：")
            for t in tables:
                db_logger.info(f"  - {t}")
        else:
            db_logger.warning(f"目标数据库 '{dbname}' 中未找到任何表")
    except Exception as e:
        db_logger.warning(f"列出表失败: {e}")
    return True


def main():
    cfg = get_pg_config()
    parser = argparse.ArgumentParser(description="PostgreSQL 数据库初始化脚本")
    parser.add_argument("--host", default=cfg["host"], help="PostgreSQL 主机地址")
    parser.add_argument("--port", type=int, default=cfg["port"], help="PostgreSQL 端口")
    parser.add_argument("--user", default=cfg["user"], help="用户名")
    parser.add_argument("--password", default=cfg["password"], help="密码")
    parser.add_argument("--dbname", default=cfg["dbname"], help="要初始化的数据库名")
    parser.add_argument("--check-only", action="store_true", help="仅测试连接，不创建任何对象")
    parser.add_argument("--reset", action="store_true", help="drop 全部表后重建（清空数据）")
    args = parser.parse_args()

    db_logger.info("=" * 60)
    db_logger.info("PostgreSQL 数据库初始化")
    db_logger.info("=" * 60)
    db_logger.info(f"主机: {args.host}:{args.port}")
    db_logger.info(f"用户: {args.user}")
    db_logger.info(f"数据库: {args.dbname}")
    db_logger.info("=" * 60)

    if args.check_only:
        ok = check_pg_connection(args.host, args.port, args.user, args.password, None)
        sys.exit(0 if ok else 1)

    # 步骤 1：创建数据库
    if not create_database_if_not_exists(
        args.host, args.port, args.user, args.password, args.dbname
    ):
        db_logger.error("数据库创建失败，终止执行")
        sys.exit(1)

    # 步骤 2：建表
    if not init_tables(
        args.host, args.port, args.user, args.password, args.dbname, reset=args.reset
    ):
        db_logger.error("建表失败，终止执行")
        sys.exit(1)

    db_logger.info("=" * 60)
    db_logger.info("数据库初始化完成！")
    db_logger.info("=" * 60)


if __name__ == "__main__":
    main()