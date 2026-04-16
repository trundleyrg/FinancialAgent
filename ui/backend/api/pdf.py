"""
PDF处理API路由
"""
import os
import shutil
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, BackgroundTasks, Depends
from fastapi.responses import FileResponse

from ui.backend.core.config import UPLOAD_DIR, ALLOWED_EXTENSIONS, MAX_FILE_SIZE
from ui.backend.models.schemas import ProcessResult, TableInfo, CompanyInfo
from ui.backend.services.pdf_service import PDFService
from ui.backend.services.db_service import DatabaseService

router = APIRouter(prefix="/pdf", tags=["PDF处理"])


def get_pdf_service(
    db_type: Annotated[str, Query(description="数据库类型")] = "duckdb"
) -> PDFService:
    """PDF服务依赖注入"""
    return PDFService(db_type=db_type)


@router.post("/upload", response_model=ProcessResult)
async def upload_and_process_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF文件"),
    service: Annotated[PDFService, Depends(get_pdf_service)]
):
    """
    上传PDF文件并处理

    1. 保存上传的PDF文件
    2. 提取财务报表
    3. 保存到数据库
    4. 生成Excel下载链接

    优化：上传成功后自动清除数据库查询缓存
    """
    # 检查文件类型
    if not file.filename or not any(file.filename.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="只支持PDF文件")

    # 安全检查：验证文件名
    safe_filename = file.filename.replace("..", "").replace("/", "").replace("\\", "")
    if not safe_filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只支持PDF文件")

    # 创建临时文件
    file_id = os.urandom(8).hex()
    file_path = UPLOAD_DIR / f"{file_id}_{safe_filename}"

    try:
        # 保存上传的文件（使用流式写入控制内存）
        with open(file_path, "wb") as buffer:
            # 使用1MB缓冲区进行大文件优化
            shutil.copyfileobj(file.file, buffer, length=1024 * 1024)

        # 处理PDF
        success, message, company_info, tables, saved_ids, download_urls = service.process_pdf(str(file_path))

        if not success:
            raise HTTPException(status_code=400, detail=message)

        # PDF处理成功后清除数据库缓存（后台任务）
        background_tasks.add_task(DatabaseService.invalidate_cache)

        return ProcessResult(
            success=True,
            message=message,
            company_info=CompanyInfo(**company_info) if company_info else None,
            tables=[TableInfo(**t) for t in tables],
            saved_ids=saved_ids,
            download_urls=download_urls
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

    finally:
        # 清理上传的文件
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                pass


@router.post("/process", response_model=ProcessResult)
async def process_pdf_file(
    background_tasks: BackgroundTasks,
    file_path: Annotated[str, Query(description="PDF文件路径")],
    service: Annotated[PDFService, Depends(get_pdf_service)]
):
    """
    处理已存在的PDF文件（服务器上的文件）

    优化：处理成功后自动清除数据库查询缓存
    """
    pdf_path = Path(file_path)

    if not pdf_path.exists() or not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    if pdf_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="只支持PDF文件")

    try:
        success, message, company_info, tables, saved_ids, download_urls = service.process_pdf(str(pdf_path))

        if not success:
            raise HTTPException(status_code=400, detail=message)

        # 处理成功后清除缓存
        background_tasks.add_task(DatabaseService.invalidate_cache)

        return ProcessResult(
            success=True,
            message=message,
            company_info=CompanyInfo(**company_info) if company_info else None,
            tables=[TableInfo(**t) for t in tables],
            saved_ids=saved_ids,
            download_urls=download_urls
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@router.post("/cleanup")
async def cleanup_temp_files():
    """
    清理过期的临时文件

    删除超过24小时的临时目录
    """
    PDFService.cleanup_temp_dirs(max_age_hours=24)
    return {"message": "临时文件清理完成"}
