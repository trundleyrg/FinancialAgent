"""
PostgreSQL 数据库初始化脚本

功能：
1. 创建数据库 'financial'
2. 在数据库中创建表（基于 src/db/models.py 中的 ORM 模型）
3. 表名使用模型类中定义的 __tablename__
4. 列名使用模型类中定义的属性
使用方法：
    python script/init_db.py

    或带参数运行：
    python script/init_db.py --host localhost --port 5432 --user postgres --password postgres
"""
import argparse
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine
import sys
import os
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.logger import db_logger
from src.db.models import Base

load_dotenv()


def get_db_config():
    """从环境变量获取数据库配置，如果不存在则使用默认值"""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
        "dbname": os.getenv("DB_NAME", "financial")
    }


def create_database_if_not_exists(
    host: str = "localhost",
    port: int = 5432,
    user: str = "postgres",
    password: str = "",
    dbname: str = "financial"
) -> bool:
    """
    创建数据库（如果不存在）
    """
    db_logger.info(f"正在连接 PostgreSQL 服务器: {host}:{port}")
    db_logger.info(f"用户: {user}")

    try:
        # 连接到默认的 postgres 数据库
        conn = psycopg2.connect(
                host=host,
                user=user,
                password=password,
                dbname="postgres"  
            )

        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # 检查数据库是否已存在
        cursor.execute(
            sql.SQL("SELECT 1 FROM pg_database WHERE datname = {}").format(
                sql.Literal(dbname)
            )
        )
        exists = cursor.fetchone()

        if exists:
            db_logger.info(f"数据库 '{dbname}' 已存在，跳过创建。")
        else:
            # 创建数据库
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(dbname)
                )
            )
            db_logger.info(f"数据库 '{dbname}' 创建成功！")

        cursor.close()
        conn.close()
        return True

    except psycopg2.OperationalError as e:
        db_logger.error(f"连接 PostgreSQL 失败！")
        db_logger.error(f"错误详情: {e}")
        return False
    except psycopg2.Error as e:
        db_logger.error(f"创建数据库时出错: {e}")
        return False


def create_tables(
    host: str = "localhost",
    port: int = 5432,
    user: str = "postgres",
    password: str = "postgres",
    dbname: str = "financial"
) -> bool:
    """
    在数据库中创建所有表（基于 SQLAlchemy 模型）

    :param host: PostgreSQL 主机地址
    :param port: PostgreSQL 端口
    :param user: 数据库用户名
    :param password: 数据库密码
    :param dbname: 数据库名称
    :return: 是否创建成功
    """
    db_logger.info(f"正在连接数据库 '{dbname}' 创建表...")

    try:
        # 构建数据库连接 URL
        database_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

        # 创建 SQLAlchemy 引擎
        engine = create_engine(database_url, echo=False)

        # 创建所有表
        Base.metadata.create_all(engine)

        db_logger.info("数据库表创建成功！")
        db_logger.info("已创建的表：")
        for table_name in Base.metadata.tables.keys():
            db_logger.info(f"  - {table_name}")

        engine.dispose()
        return True
    except Exception as e:
        db_logger.error(f"创建表时出错: {type(e).__name__}: {e}")
        return False


def main():
    """主函数"""
    # 从 .env 文件加载默认配置
    default_config = get_db_config()

    parser = argparse.ArgumentParser(description="PostgreSQL 数据库初始化脚本")
    parser.add_argument("--host", default=default_config["host"], help="PostgreSQL 主机地址")
    parser.add_argument("--port", type=int, default=default_config["port"], help="PostgreSQL 端口")
    parser.add_argument("--user", default=default_config["user"], help="数据库用户名")
    parser.add_argument("--password", default=default_config["password"], help="数据库密码")
    parser.add_argument("--dbname", default=default_config["dbname"], help="要创建的数据库名称")
    parser.add_argument("--check-only", action="store_true", help="仅测试连接，不创建数据库和表")

    args = parser.parse_args()

    db_logger.info("=" * 50)
    db_logger.info("PostgreSQL 数据库初始化")
    db_logger.info("=" * 50)
    db_logger.info(f"主机: {args.host}:{args.port}")
    db_logger.info(f"用户: {args.user}")
    db_logger.info(f"数据库: {args.dbname}")
    db_logger.info("=" * 50)

    if args.check_only:
        db_logger.info("[检查模式] 测试 PostgreSQL 连接...")
        try:
            conn = psycopg2.connect(
                host=args.host,
                port=args.port,
                dbname="postgres",
                user=args.user,
                password=args.password,
                connect_timeout=10
            )
            db_logger.info("连接成功！PostgreSQL 服务运行正常。")
            conn.close()
        except Exception as e:
            db_logger.error(f"连接失败: {e}")
            sys.exit(1)
        return

    # 步骤 1: 创建数据库
    db_logger.info("[步骤 1] 创建数据库...")
    if not create_database_if_not_exists(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        dbname=args.dbname
    ):
        db_logger.error("数据库创建失败，终止执行。")
        sys.exit(1)

    # 步骤 2: 创建表
    db_logger.info("[步骤 2] 创建数据库表...")
    if not create_tables(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        dbname=args.dbname
    ):
        db_logger.error("表创建失败，终止执行。")
        sys.exit(1)

    db_logger.info("=" * 50)
    db_logger.info("数据库初始化完成！")
    db_logger.info("=" * 50)


if __name__ == "__main__":
    main()
