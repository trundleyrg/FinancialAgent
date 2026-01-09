"""
日志管理
"""
import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler

class LoggerManager:
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # 基础格式：时间 - 模块名 - 级别 - 消息
        self.formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    def get_logger(
        self, 
        name: str, 
        log_file: str, 
        max_bytes: int = 10 * 1024 * 1024,  # 默认 10MB
        backup_count: int = 5              # 默认保留 5 个旧文件
    ) -> logging.Logger:
        """
        获取一个支持日志轮转的特定 logger。
        :param name: Logger 名称
        :param log_file: 文件名
        :param max_bytes: 单个文件最大字节数
        :param backup_count: 保留的历史日志文件数量
        """
        logger = logging.getLogger(name)
        
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            
            # 1. 轮转文件处理器
            rotating_handler = RotatingFileHandler(
                self.log_dir / log_file, 
                maxBytes=max_bytes, 
                backupCount=backup_count,
                encoding='utf-8'
            )
            rotating_handler.setFormatter(self.formatter)
            logger.addHandler(rotating_handler)
            
            # 2. 控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(self.formatter)
            logger.addHandler(console_handler)
            
        return logger

# 实例化全局管理对象
manager = LoggerManager()

# --- 预定义各个模块的 Logger ---

# PDF 解析日志
pdf_logger = manager.get_logger(
    "PDFParser", "pdf_parser.log", max_bytes=20*1024*1024
)

# Agent 节点日志：记录状态流转，10MB 轮转
node_logger = manager.get_logger(
    "AgentNode", "agent_node.log"
)

# 数据库逻辑日志
db_logger = manager.get_logger(
    "Database", "db_operations.log"
)

# 系统全局日志
sys_logger = manager.get_logger(
    "System", "system.log"
)