"""`main.py run 600285 ...` 端到端集成测试(防回归)。

## ⚠️ DuckDB 并发约束(重要)

DuckDB 是**单写者锁**的文件数据库:同一时刻只能有一个进程写同一个
`.duckdb` 文件。本测试因此**绝不**直接打开项目真实的
`data/db/financial_data.duckdb`。

早先一版测试用 `duckdb.connect(db_path, read_only=True)` 持有真实
DB 的读锁,再 fork 子进程跑 `main.py run` 写同一个文件 —— 锁冲突
**损坏了 DB 文件**,丢失 stock_daily_price(6207 行)、
capital_change_events、consolidated_cash_flow_statement 等数据。

正确做法:测试全程在 `tmp_path` 下的**独立 DB 副本**里跑,
通过 `DUCKDB_DB_PATH` 环境变量指向它,项目真实 DB 零接触。

## 测试策略

- 用 `shutil.copy2` 把真实 DB 复制到 tmp_path(只读源文件,安全)
- `DUCKDB_DB_PATH` 指向副本,子进程写副本
- PDF 用软链接/复制到 tmp_path 的 `data/600285/`(避免污染真实目录)
- `NO_LLM=1` 走 code-only 模式,避免 LLM 网络依赖
- 验证:pipeline exit 0 + DB 行数 + markdown 文件结构
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
REAL_DB = PROJECT_ROOT / "data" / "db" / "financial_data.duckdb"
REAL_PDF_DIR = PROJECT_ROOT / "data" / "600285"
STOCK_CODE = "600285"
YEARS = [2020, 2021, 2022, 2023, 2024]


@pytest.fixture
def isolated_workspace(tmp_path: Path) -> Path:
    """构造一个完全隔离的工作目录,内含 DB 副本 + PDF 副本。

    - `data/db/financial_data.duckdb`  ← 从真实 DB 复制(**只读源文件**)
    - `data/600285/*.pdf`             ← 从真实 PDF 目录复制
    - 项目源码通过 `main.py` 路径引用,但 cwd 隔离在 tmp_path

    测试结束后 tmp_path 自动清理,真实 DB / 真实 data/ 目录零污染。
    """
    ws = tmp_path / "workspace"
    (ws / "data" / "db").mkdir(parents=True)
    (ws / "data" / STOCK_CODE).mkdir(parents=True)

    # DB 副本(源文件只被读取一次,copy2 是纯读操作)
    assert REAL_DB.exists(), (
        f"真实 DB 不存在:{REAL_DB}\n"
        "先跑 `python main.py run 600285 2020 2021 2022 2023 2024` 建库。"
    )
    shutil.copy2(REAL_DB, ws / "data" / "db" / "financial_data.duckdb")

    # PDF 副本
    pdfs = sorted(REAL_PDF_DIR.glob("*.pdf"))
    assert pdfs, f"真实 PDF 目录为空:{REAL_PDF_DIR}\n先跑 `python main.py download 600285`。"
    for pdf in pdfs:
        shutil.copy2(pdf, ws / "data" / STOCK_CODE / pdf.name)

    return ws


def _run_pipeline(ws: Path, stock_code: str, years: list[int]) -> dict:
    """在隔离 workspace 里跑 `python main.py run`,返回结果摘要。

    关键:必须把 PROJECT_ROOT 放到 PYTHONPATH 最前面,让子进程 import
    到项目源码(main.py / src.*),但**读写**的是 ws 下的 DB 和 PDF。
    """
    env = os.environ.copy()
    env["NO_LLM"] = "1"                                   # code-only,无 LLM 网络
    env["PYTHONPATH"] = str(PROJECT_ROOT)                 # import 项目源码
    env["DUCKDB_DB_PATH"] = str(ws / "data" / "db" / "financial_data.duckdb")

    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "main.py"), "run", stock_code,
         *[str(y) for y in years]],
        cwd=str(ws),          # ← 相对路径 data/{stock}/ 落在 ws 里
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def test_pipeline_runs_all_four_steps(isolated_workspace):
    """4 个 step 全走完:download / parse / dividend。"""
    res = _run_pipeline(isolated_workspace, STOCK_CODE, YEARS)
    assert res["exit_code"] == 0, (
        f"pipeline 跑挂(exit={res['exit_code']}):\n"
        f"STDOUT tail:\n{res['stdout'][-1500:]}\n"
        f"STDERR tail:\n{res['stderr'][-1500:]}"
    )
    out = res["stdout"]
    assert "Step 1 / Download annual reports" in out
    assert "Step 2+3 / Parse PDF" in out
    assert "Step 4 / Dividend analysis" in out
    assert "skill 完成" in out, "dividend skill 应跑完"


def test_pipeline_reports_all_seven_tables_present_in_db(isolated_workspace):
    """解析后 6 张财报表都应有 2020-2024 共 5 年数据。

    这是防止 chapter_extractor 回归的关键断言 ——
    早先一次「start_page 只看前 10 行」的改动让所有报表定位失败,
    但 pipeline 仍 exit 0(因为 parse 错误被吞进 log),
    只有查 DB 才能发现。
    """
    import duckdb

    res = _run_pipeline(isolated_workspace, STOCK_CODE, YEARS)
    assert res["exit_code"] == 0

    db_path = isolated_workspace / "data" / "db" / "financial_data.duckdb"
    # 关闭上一步可能残留的连接后再读
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        for tbl in [
            "consolidated_balance_sheet",
            "consolidated_income_statement",
            "consolidated_cash_flow_statement",
            "parent_company_balance_sheet",
            "parent_company_income_statement",
            "parent_company_cash_flow_statement",
        ]:
            years = sorted(
                r[0] for r in conn.execute(
                    f"SELECT report_year FROM {tbl} WHERE stock_code=?", [STOCK_CODE]
                ).fetchall()
            )
            assert years == YEARS, (
                f"{tbl} 应覆盖 {YEARS},实际 {years}\n"
                f"提示:若只剩零星年份,多半是 chapter_extractor 的章节定位回归。"
            )
    finally:
        conn.close()


def test_pipeline_writes_markdown_report(isolated_workspace):
    """报告文件写到隔离目录的 data/{stock}/memory/ 下,结构完整。"""
    res = _run_pipeline(isolated_workspace, STOCK_CODE, YEARS)
    assert res["exit_code"] == 0

    md_files = list(
        (isolated_workspace / "data" / STOCK_CODE / "memory").glob("分析报告_分红_*.md")
    )
    assert len(md_files) == 1, f"应生成 1 份报告,实际 {md_files}"
    content = md_files[0].read_text(encoding="utf-8")

    # 关键 section(编号随负债结构是否出现而偏移,故只断言标题文字)
    for title in [
        "关键指标趋势",
        "关键指标",
        "盈利能力",
        "偿债能力",
        "估值",
        "风险因素",
        "目标股息率",
    ]:
        assert title in content, f"报告应含「{title}」section"

    # 评级段已删
    assert "**投资评级" not in content, "报告不应含评级段"

    # 关键指标 6 项
    for indicator in [
        "股息率(%)", "分红率(%)", "连续分红年限(年)",
        "自由现金流对分红覆盖率(倍)", "有息负债(亿元)", "有息负债占比(%)",
    ]:
        assert indicator in content, f"关键指标表应含「{indicator}」"

    # 目标股息率表头
    assert "对应市值(亿元)" in content and "对应价格(元/股)" in content


def test_pipeline_generates_charts(isolated_workspace):
    """趋势图 + 负债结构图 PNG 都要生成。"""
    res = _run_pipeline(isolated_workspace, STOCK_CODE, YEARS)
    assert res["exit_code"] == 0

    charts = isolated_workspace / "data" / STOCK_CODE / "memory" / "charts"
    assert (charts / "dividend_trend_2024.png").exists(), "缺分红趋势图"
    assert (charts / "debt_structure_2024.png").exists(), "缺负债结构图"
    # PNG 非空
    for png in charts.glob("*.png"):
        assert png.stat().st_size > 1000, f"{png.name} 应非空"


def test_pipeline_is_idempotent(isolated_workspace):
    """重复跑两次,DB 行数不应变化(UPSERT 而非重复 INSERT)。"""
    import duckdb

    db_path = isolated_workspace / "data" / "db" / "financial_data.duckdb"

    def snapshot() -> dict[str, int]:
        conn = duckdb.connect(str(db_path), read_only=True)
        try:
            return {
                t: conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE stock_code=?", [STOCK_CODE]
                ).fetchone()[0]
                for t in ["consolidated_balance_sheet", "consolidated_income_statement",
                          "consolidated_cash_flow_statement", "share_structure"]
            }
        finally:
            conn.close()

    assert _run_pipeline(isolated_workspace, STOCK_CODE, YEARS)["exit_code"] == 0
    first = snapshot()
    assert _run_pipeline(isolated_workspace, STOCK_CODE, YEARS)["exit_code"] == 0
    second = snapshot()

    assert first == second, f"重复跑后行数变了(应幂等):\n  before={first}\n  after={second}"


def test_pipeline_persists_skill_result(isolated_workspace):
    """skill_analysis_results 表应有 600285/dividend/2024 记录。"""
    import duckdb

    res = _run_pipeline(isolated_workspace, STOCK_CODE, YEARS)
    assert res["exit_code"] == 0

    conn = duckdb.connect(
        str(isolated_workspace / "data" / "db" / "financial_data.duckdb"), read_only=True
    )
    try:
        row = conn.execute(
            """
            SELECT stock_code, report_year, skill_name, investment_rating
            FROM skill_analysis_results
            WHERE stock_code=? AND skill_name='dividend'
            ORDER BY created_at DESC LIMIT 1
            """,
            [STOCK_CODE],
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "skill_analysis_results 应有 dividend 记录"
    assert row[1] == 2024
    assert row[3] in ("BUY", "HOLD", "SELL"), f"评级应为 BUY/HOLD/SELL,实际 {row[3]}"


def test_real_db_untouched_by_tests(isolated_workspace):
    """回归防线:跑完测试后,真实 DB 的 mtime / 大小不应变化。

    这条测试直接锁住「测试绝不碰真实 DB」这条铁律 ——
    早先的 bug 就是测试持有真实 DB 读锁 + 子进程写,锁冲突损坏文件。
    如果将来有人图省事去掉隔离 fixture,这条会立刻失败。
    """
    real_before = REAL_DB.stat()
    size_before, mtime_before = real_before.st_size, real_before.st_mtime

    assert _run_pipeline(isolated_workspace, STOCK_CODE, YEARS)["exit_code"] == 0

    real_after = REAL_DB.stat()
    assert real_after.st_size == size_before, (
        f"真实 DB 大小变了:{size_before} → {real_after.st_size}\n"
        "测试污染了真实 DB!检查 isolated_workspace fixture 是否生效。"
    )
    assert real_after.st_mtime == mtime_before, "真实 DB 被写入过(mtime 变了)"