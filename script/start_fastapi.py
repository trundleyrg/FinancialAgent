"""
启动 FastAPI 后端服务的脚本

用法:
    python script/start_fastapi.py                 # 使用默认配置
    python script/start_fastapi.py --host 0.0.0.0  # 指定主机
    python script/start_fastapi.py --port 8080     # 指定端口
"""

import argparse
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import uvicorn
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(description="启动财务报告分析系统 FastAPI 后端服务")
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("API_HOST", "127.0.0.1"),
        help="服务监听地址 (默认: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("API_PORT", "8000")),
        help="服务监听端口 (默认: 8000)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=True,
        help="启用代码热重载 (默认: True)"
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="禁用代码热重载"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="日志级别 (默认: info)"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 确定是否启用 reload
    reload = args.reload and not args.no_reload

    # 获取后端模块路径
    backend_module = "ui.backend.main:app"

    print("=" * 60)
    print("  财务报告分析系统 - FastAPI 后端服务")
    print("=" * 60)
    print(f"  API 地址: http://{args.host}:{args.port}")
    print(f"  API 文档: http://{args.host}:{args.port}/docs")
    print(f"  前端页面: http://{args.host}:{args.port}/static/index.html")
    print(f"  热重载:   {'启用' if reload else '禁用'}")
    print("=" * 60)
    print()

    # 启动服务
    uvicorn.run(
        backend_module,
        host=args.host,
        port=args.port,
        reload=reload,
        log_level=args.log_level,
        reload_dirs=[str(project_root / "ui" / "backend")],
    )


if __name__ == "__main__":
    main()
