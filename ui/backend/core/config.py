"""
FastAPI 配置
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data"

# 上传文件临时目录
UPLOAD_DIR = DATA_DIR / "temp" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Excel导出目录
EXCEL_DIR = DATA_DIR / "temp" / "excel"
EXCEL_DIR.mkdir(parents=True, exist_ok=True)

# 数据库配置
DATABASE_TYPE = os.getenv("DATABASE", "duckdb")
DUCKDB_PATH = os.getenv("DUCKDB_DB_PATH", str(BASE_DIR / "data" / "db" / "financial_data.duckdb"))
POSTGRES_URL = os.getenv("POSTGRES_DB_URL", "postgresql://postgres:postgres@localhost:5432/financial_statements")

# FastAPI配置
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

# 文件大小限制 (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# 支持的文件类型
ALLOWED_EXTENSIONS = {".pdf"}
