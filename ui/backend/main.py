"""
FastAPI 主应用
财务报告分析系统 - FastAPI 后端服务
"""
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from ui.backend.api import pdf, database
from ui.backend.core.config import UPLOAD_DIR, EXCEL_DIR, API_HOST, API_PORT

# 创建FastAPI应用
app = FastAPI(
    title="财务报告分析系统",
    description="PDF财务报告上传、解析与数据库查询API服务",
    version="1.0.0"
)

# CORS配置（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(pdf.router, prefix="/api")
app.include_router(database.router, prefix="/api")

# 确保目录存在
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
EXCEL_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/")
async def root():
    """API根路径"""
    return {
        "name": "财务报告分析系统",
        "version": "1.0.0",
        "docs": "/docs",
        "frontend": "/static/index.html"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


# 文件下载路由
@app.get("/api/files/{filename}")
async def download_file(filename: str):
    """
    下载生成的Excel文件
    """
    # 安全检查：防止目录遍历
    filename = filename.replace("..", "").replace("/", "").replace("\\", "")

    # 搜索文件
    file_path = None
    for search_dir in [UPLOAD_DIR, EXCEL_DIR, Path("./data/temp")]:
        potential_path = search_dir / filename
        if potential_path.exists():
            file_path = potential_path
            break

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在或已过期")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.delete("/api/files/{filename}")
async def delete_file(filename: str):
    """
    删除临时文件
    """
    filename = filename.replace("..", "").replace("/", "").replace("\\", "")

    file_path = None
    for search_dir in [UPLOAD_DIR, EXCEL_DIR, Path("./data/temp")]:
        potential_path = search_dir / filename
        if potential_path.exists():
            file_path = potential_path
            break

    if file_path and file_path.exists():
        try:
            file_path.unlink()
            return {"message": "文件已删除"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=404, detail="文件不存在")


# 挂载静态文件目录（前端）
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "ui.backend.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True
    )
