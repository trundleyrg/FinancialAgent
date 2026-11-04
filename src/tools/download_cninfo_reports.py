"""
下载巨潮资讯网上市公司年度报告
"""
import os
import sys
import requests
import time
import re
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('download_cninfo.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class CNInfoReportDownloader:
    """巨潮资讯网报告下载器（年报/半年报/一季报/三季报）"""

    # 巨潮资讯网公告分类：报告类型 → category 参数
    REPORT_CATEGORY = {
        'FY': 'category_ndbg_szsh',   # 年度报告
        'Q1': 'category_yjdbg_szsh',  # 第一季度报告
        'H1': 'category_bndbg_szsh',  # 半年度报告
        'Q3': 'category_sjdbg_szsh',  # 第三季度报告
    }

    # 报告类型 → 标题中必须出现的关键词
    REPORT_TITLE_KEYWORD = {
        'FY': ('年度报告',),
        'Q1': ('第一季度报告',),
        'H1': ('半年度报告',),
        'Q3': ('第三季度报告',),
    }

    # 报告类型 → 标题中**不能**出现的关键词（防止类型互串）。
    # "半年度报告" 里含 "年度报告"，所以查年报时必须排除半年度类标题；
    # "第一季度报告" 里含 "季度"，同理。
    _PERIOD_TITLE_CONFLICTS = {
        'FY': ('半年度', '半年报', '季度', '季报'),
        'Q1': ('半年度', '半年报', '第三季度', '三季度'),
        'H1': ('第一季度', '一季报', '第三季度', '三季度'),
        'Q3': ('第一季度', '一季报', '半年度', '半年报'),
    }

    # 报告类型 → 搜索窗口的年份偏移。
    # 年报在次年 4 月底前发布；季报/半年报在**报告当年**发布
    # （Q1→4月、H1→8月、Q3→10月）。
    REPORT_SEARCH_YEAR_OFFSET = {
        'FY': (1, 2),
        'Q1': (0,),
        'H1': (0,),
        'Q3': (0,),
    }

    # 标题里必须排除的非正式版本
    _TITLE_EXCLUDE_KEYWORDS = (
        '摘要', '英文', '已取消', '修订公告', '补充公告',
        '补充说明', '决议公告', '主要财务指标',
    )

    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'Host': 'www.cninfo.com.cn',
            'Origin': 'http://www.cninfo.com.cn',
            'Pragma': 'no-cache',
            'Accept-Encoding': 'gzip,deflate',
            'Connection': 'keep-alive',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Accept': 'application/json,text/plain,*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        
    def get_stock_info(self, stock_code: str) -> dict:
        """获取股票信息，包括orgId和板块（按代码查询）"""
        url = "http://www.cninfo.com.cn/new/data/szse_stock.json"
        try:
            resp = self.session.get(url, headers=self.headers, timeout=10)
            resp.raise_for_status()
            stock_list = resp.json().get("stockList", [])

            for stock in stock_list:
                if stock['code'] == stock_code:
                    return self._build_stock_info(stock, stock_code)

            # 如果szse没找到，尝试sse
            url = "http://www.cninfo.com.cn/new/data/sse_stock.json"
            resp = self.session.get(url, headers=self.headers, timeout=10)
            resp.raise_for_status()
            stock_list = resp.json().get("stockList", [])

            for stock in stock_list:
                if stock['code'] == stock_code:
                    return self._build_stock_info(stock, stock_code)

            logger.error(f"未找到股票代码 {stock_code} 的信息")
            print(f"未找到股票代码 {stock_code} 的信息")
            return None
        except Exception as e:
            logger.error(f"获取股票代码 {stock_code} 信息失败: {e}")
            print(f"获取股票信息失败: {e}")
            return None

    def search_stock_by_name(self, stock_name: str) -> dict:
        """根据公司名称搜索股票信息（按名称模糊查询）"""
        # 尝试深市
        url_sz = "http://www.cninfo.com.cn/new/data/szse_stock.json"
        # 尝试沪市
        url_sh = "http://www.cninfo.com.cn/new/data/sse_stock.json"

        try:
            # 并行请求两市数据
            resp_sz = self.session.get(url_sz, headers=self.headers, timeout=10)
            resp_sz.raise_for_status()
            stock_list_sz = resp_sz.json().get("stockList", [])

            resp_sh = self.session.get(url_sh, headers=self.headers, timeout=10)
            resp_sh.raise_for_status()
            stock_list_sh = resp_sh.json().get("stockList", [])

            all_stocks = stock_list_sz + stock_list_sh

            # 模糊匹配公司名称
            matches = []
            name_lower = stock_name.lower()
            for stock in all_stocks:
                zwjc = stock.get('zwjc', '').lower()
                if name_lower in zwjc or zwjc.startswith(name_lower):
                    matches.append(stock)

            if not matches:
                logger.error(f"未找到名称包含 '{stock_name}' 的股票")
                print(f"未找到名称包含 '{stock_name}' 的股票")
                return None

            if len(matches) > 1:
                logger.warning(f"找到多个匹配结果，请使用更精确的名称:")
                print(f"找到多个匹配结果，请使用更精确的名称:")
                for i, m in enumerate(matches):
                    print(f"  {i+1}. {m['zwjc']} ({m['code']})")
                # 返回第一个匹配
                stock = matches[0]
                logger.info(f"自动选择第一个匹配: {stock['zwjc']} ({stock['code']})")
                print(f"自动选择第一个匹配: {stock['zwjc']} ({stock['code']})")
            else:
                stock = matches[0]

            return self._build_stock_info(stock, stock['code'])

        except Exception as e:
            logger.error(f"搜索股票名称 '{stock_name}' 失败: {e}")
            print(f"搜索股票名称 '{stock_name}' 失败: {e}")
            return None

    def _build_stock_info(self, stock: dict, stock_code: str) -> dict:
        """构建股票信息字典"""
        org_id = stock['orgId']
        # 判断板块：上海主板、深圳主板、创业板等
        if stock_code.startswith('6'):
            plate, column = 'sh', 'sse'
        elif stock_code.startswith('0'):
            plate, column = 'sz', 'szse'
        elif stock_code.startswith('3'):
            plate, column = 'sz', 'szse'  # 创业板
        elif stock_code.startswith('68'):
            plate, column = 'sh', 'sse'  # 科创板
        else:
            plate, column = 'sz', 'szse'

        return {
            'orgId': org_id,
            'plate': plate,
            'column': column,
            'code': stock_code,
            'name': stock.get('zwjc', '')
        }

    def get_stock_info_by_code_or_name(self, code_or_name: str) -> dict:
        """
        根据代码或名称获取股票信息

        Args:
            code_or_name: 股票代码或公司名称
                - 如果是纯数字且长度为6，视为代码查询
                - 否则视为名称模糊查询

        Returns:
            股票信息字典，包含 orgId, plate, column, code, name
        """
        code_or_name = code_or_name.strip()

        # 判断是代码还是名称
        if code_or_name.isdigit() and len(code_or_name) == 6:
            logger.info(f"按股票代码查询: {code_or_name}")
            return self.get_stock_info(code_or_name)
        else:
            logger.info(f"按公司名称查询: {code_or_name}")
            return self.search_stock_by_name(code_or_name)
    
    def query_reports_by_period(self, stock_code: str, org_id: str, column: str,
                                plate: str, years: list, periods: list) -> list:
        """按报告类型查询公告列表。

        Args:
            years: 报告所属年份列表，如 [2024, 2025]
            periods: 报告类型列表，如 ['FY'] 或 ['Q1', 'H1', 'Q3']
        Returns:
            [{'title','year','period','adjunctUrl','announcementId','secName','announcementTime'}]
        """
        reports = []
        for period in periods:
            category = self.REPORT_CATEGORY.get(period)
            if not category:
                logger.warning(f"未知报告类型 {period}，跳过")
                continue
            for year in years:
                reports.extend(self._query_period_reports(
                    stock_code, org_id, column, plate, int(year), period, category,
                ))
        return reports

    def _query_period_reports(self, stock_code: str, org_id: str, column: str,
                              plate: str, year: int, period: str,
                              category: str) -> list:
        """查询某一年度、某一类型的报告。"""
        reports = []
        found_valid = False
        url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"

        for search_year in [year + off for off in self.REPORT_SEARCH_YEAR_OFFSET[period]]:
            if found_valid:
                break  # 同一年度同一类型只取一份

            se_date = f"{search_year}-01-01~{search_year}-12-31"

            data = {
                'pageNum': '1',
                'pageSize': '30',
                'tabName': 'fulltext',
                'stock': f'{stock_code},{org_id}',
                'seDate': se_date,
                'column': column,
                'category': category,
                'isHLtitle': 'true',
                'sortName': 'time',
                'sortType': 'desc',
                'plate': plate,
                'searchkey': '',
                'secid': '',
            }

            try:
                resp = self.session.post(url, data=data, headers=self.headers, timeout=15)
                resp.raise_for_status()
                result = resp.json()
                announcements = result.get('announcements', []) or []
            except Exception as e:
                logger.error(f"查询 {year} 年 {period} 报告失败: {e}")
                print(f"查询 {year} 年 {period} 报告失败: {e}")
                continue

            if not announcements:
                logger.info(f"  {search_year}年未找到任何 {period} 公告")

            for ann in announcements:
                title = ann.get('announcementTitle', '')
                if not self._is_valid_report(title, year, period):
                    continue
                reports.append({
                    'title': title,
                    'year': year,
                    'period': period,
                    'adjunctUrl': ann.get('adjunctUrl', ''),
                    'announcementId': ann.get('announcementId', ''),
                    'secName': ann.get('secName', ''),
                    'announcementTime': ann.get('announcementTime', ''),
                })
                logger.info(f"  找到 {year} {period} 报告: {title} (来源: {search_year}年)")
                print(f"  找到 {year} {period} 报告: {title} (来源: {search_year}年)")
                found_valid = True
                break  # 同一年度同一类型只取一份

            time.sleep(0.5)  # 避免请求过快

        return reports

    def query_annual_reports(self, stock_code: str, org_id: str, column: str, plate: str, years: list) -> list:
        """查询年度报告列表（`query_reports_by_period` 的年报特例）。"""
        return self.query_reports_by_period(
            stock_code, org_id, column, plate, years, ['FY'],
        )
    
    def _is_valid_report(self, title: str, year: int, period: str) -> bool:
        """判断标题是否是目标年度、指定类型的正式报告。

        排除摘要/英文/已取消/更正/修订等非正式版本；标题里的年份必须与
        目标年度一致（"羚锐制药2025年第一季度报告"）。
        """
        if any(k in title for k in self._TITLE_EXCLUDE_KEYWORDS):
            return False

        keywords = self.REPORT_TITLE_KEYWORD.get(period)
        if not keywords:
            return False
        if not any(k in title for k in keywords):
            return False

        conflicts = self._PERIOD_TITLE_CONFLICTS.get(period, ())
        if any(k in title for k in conflicts):
            return False

        title_years = set(re.findall(r'(?:19|20)\d{2}', title))
        if title_years and str(year) not in title_years:
            return False
        return True

    @staticmethod
    def build_report_filename(company_name: str, stock_code: str,
                              year: int, period: str) -> str:
        """报告 PDF 文件名。

        年报保持 `{简称}_{代码}_{年}.pdf`（兼容既有 data/ 下的历史文件），
        季报/半年报加周期后缀：`{简称}_{代码}_{年}{Q1|H1|Q3}.pdf`。
        """
        clean_name = re.sub(r'[<>:"/\\|?*]', '', company_name)
        suffix = '' if period == 'FY' else period
        return f"{clean_name}_{stock_code}_{year}{suffix}.pdf"

    def download_pdf(self, adjunct_url: str, save_path: str, filename: str) -> bool:
        """下载PDF文件"""
        pdf_url = f"https://static.cninfo.com.cn/{adjunct_url}"
        
        # 下载PDF需要额外的headers
        download_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': 'http://www.cninfo.com.cn/',
            'Accept': 'application/pdf,*/*',
        }
        
        try:
            logger.info(f"  下载中: {filename}")
            resp = self.session.get(pdf_url, headers=download_headers, timeout=60)
            resp.raise_for_status()

            full_path = os.path.join(save_path, filename)
            with open(full_path, 'wb') as f:
                f.write(resp.content)

            logger.info(f"  下载成功: {filename}")
            print(f"  下载成功: {filename}")
            return True

        except Exception as e:
            logger.error(f"  下载失败: {e}")
            print(f"  下载失败: {e}")
            return False
    
    def query_dividend_announcements(
        self, stock_code: str, years: list[int],
    ) -> list[dict]:
        """查询权益分派公告(巨潮搜 "权益分派" 关键词)。

        Returns:
            [{'year': int, 'title': str, 'adjunctUrl': str,
              'announcementTime': int(ms epoch)}]
        """
        stock_info = self.get_stock_info_by_code_or_name(stock_code)
        if not stock_info:
            return []
        org_id = stock_info['orgId']
        plate = stock_info['plate']
        column = stock_info['column']

        url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
        se_date = f"{min(years)}-01-01~{max(years)+1}-12-31"
        data = {
            'pageNum': '1', 'pageSize': '50', 'tabName': 'fulltext',
            'stock': f'{stock_code},{org_id}', 'seDate': se_date,
            'column': column, 'category': '',
            'searchkey': '权益分派',
            'isHLtitle': 'true', 'sortName': 'time', 'sortType': 'desc',
            'plate': plate, 'secid': '',
        }
        try:
            resp = self.session.post(url, data=data, headers=self.headers, timeout=15)
            resp.raise_for_status()
            announcements = resp.json().get('announcements', [])
        except Exception as exc:
            logger.error("查询权益分派公告失败: %s", exc)
            return []

        # 按**分配年度**提取(标题里的年份),而不是发布时间。
        #
        # 旧逻辑用「发布年 - 1」,对年度分配正确(实施公告在次年 5-7 月),
        # 但对**半年度分配**就错了:「2024年半年度权益分派实施公告」发布于
        # 2024-08,会被归到 2023,与「2024年年度」(发布于 2025-06)撞车;
        # 又因 dedup 键是 (stock_code, report_year, event_type),
        # API 按时间倒序返回 → 半年度的先入库,年度的被跳过,
        # 于是 2023/2024/2025 三年的分红率全错(实测东阿阿胶)。
        #
        # 标题里能直接读出分配年度,优先用它;读不出时才回退到发布年 - 1。
        out = []
        for ann in announcements:
            title = ann.get('announcementTitle', '')
            adj = ann.get('adjunctUrl', '')
            ts_ms = ann.get('announcementTime', 0)
            if not adj or not ts_ms:
                continue
            from datetime import datetime
            ts = datetime.utcfromtimestamp(ts_ms / 1000.0)
            title_year, kind = _parse_dividend_announcement_title(title)
            for y in years:
                if title_year is not None:
                    if title_year != y:
                        continue
                elif ts.year - 1 != y:
                    # 标题读不出年份 → 回退到发布时间推断
                    continue
                out.append({
                    'year': y, 'title': title, 'adjunctUrl': adj,
                    'announcementTime': ts_ms, 'time_str': ts.isoformat(),
                    'dividend_kind': kind,
                })
                break
        return out

    def download_reports(self, code_or_name: str, years: list, save_dir: str = None,
                         periods: list = None):
        """下载指定股票的报告 PDF（年报/半年报/一季报/三季报）。

        Args:
            code_or_name: 股票代码或公司名称
            years: 要下载的年份列表
            save_dir: 保存目录（默认为 data/{股票代码}）
            periods: 报告类型列表，默认 ['FY']
        """
        periods = periods or ['FY']

        # 获取股票信息
        stock_info = self.get_stock_info_by_code_or_name(code_or_name)
        if not stock_info:
            return False

        logger.info(f"\n股票信息: {stock_info['code']} {stock_info['name']}")
        logger.info(f"orgId: {stock_info['orgId']}, 板块: {stock_info['plate']}")
        print(f"\n股票信息: {stock_info['code']} {stock_info['name']}")
        print(f"orgId: {stock_info['orgId']}, 板块: {stock_info['plate']}")
        
        # 固定保存路径: 项目根目录/data/{code}/
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        save_dir = os.path.join(project_root, 'data', stock_info['code'])

        os.makedirs(save_dir, exist_ok=True)
        logger.info(f"保存目录: {save_dir}")
        print(f"保存目录: {save_dir}")

        # 查询报告
        stock_code = stock_info['code']
        logger.info(f"\n查询 {stock_code} {years} 报告 ({'/'.join(periods)})...")
        print(f"\n查询 {stock_code} {years} 报告 ({'/'.join(periods)})...")
        reports = self.query_reports_by_period(
            stock_code,
            stock_info['orgId'],
            stock_info['column'],
            stock_info['plate'],
            years,
            periods,
        )

        if not reports:
            logger.warning("未找到任何报告")
            print("未找到任何报告")
            return False

        logger.info(f"\n共找到 {len(reports)} 份报告，开始下载...")
        print(f"\n共找到 {len(reports)} 份报告，开始下载...")

        # 下载PDF
        success_count = 0
        for report in reports:
            filename = self.build_report_filename(
                stock_info['name'], stock_code, report['year'], report['period'],
            )

            if self.download_pdf(report['adjunctUrl'], save_dir, filename):
                success_count += 1

            time.sleep(1)  # 避免下载过快

        logger.info(f"\n下载完成: 成功 {success_count}/{len(reports)}")
        print(f"\n下载完成: 成功 {success_count}/{len(reports)}")
        return True


def query_dividend_announcements(
    self, stock_code: str, years: list[int],
) -> list[dict]:
    """查询权益分派公告(巨潮搜 "权益分派" 关键词)。

    Returns:
        [{'year': int, 'title': str, 'adjunctUrl': str,
          'announcementTime': int(ms epoch)}]
    """
    stock_info = self.get_stock_info_by_code_or_name(stock_code)
    if not stock_info:
        return []
    org_id = stock_info['orgId']
    plate = stock_info['plate']
    column = stock_info['column']

    url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
    se_date = f"{min(years)}-01-01~{max(years)+1}-12-31"
    data = {
        'pageNum': '1', 'pageSize': '50', 'tabName': 'fulltext',
        'stock': f'{stock_code},{org_id}', 'seDate': se_date,
        'column': column, 'category': '',
        'searchkey': '权益分派',
        'isHLtitle': 'true', 'sortName': 'time', 'sortType': 'desc',
        'plate': plate, 'secid': '',
    }
    try:
        resp = self.session.post(url, data=data, headers=self.headers, timeout=15)
        resp.raise_for_status()
        announcements = resp.json().get('announcements', [])
    except Exception as exc:
        logger.error("查询权益分派公告失败: %s", exc)
        return []

    # 按 year 提取(用 announceTime 推断: 通常权益分派实施公告在次年 5-7 月发布,
    # 所以 2023 年 5 月发布的对应 2022 年度权益分派 → 归到 year-1)
    out = []
    for ann in announcements:
        title = ann.get('announcementTitle', '')
        adj = ann.get('adjunctUrl', '')
        ts_ms = ann.get('announcementTime', 0)
        if not adj or not ts_ms:
            continue
        from datetime import datetime
        ts = datetime.utcfromtimestamp(ts_ms / 1000.0)
        # 按**分配年度**归年(标题里的年份),读不出才回退到发布年 - 1。
        # 详见 CNInfoReportDownloader.query_dividend_announcements 的说明。
        title_year, kind = _parse_dividend_announcement_title(title)
        for y in years:
            if title_year is not None:
                if title_year != y:
                    continue
            elif ts.year - 1 != y:
                continue
            out.append({
                'year': y, 'title': title, 'adjunctUrl': adj,
                'announcementTime': ts_ms, 'time_str': ts.isoformat(),
                'dividend_kind': kind,
            })
            break
    return out


def _extract_dividend_total(text: str) -> float | None:
    """从公告文本提取「现金分红总额」(元)。

    为什么不自己算:公告里的「每10股派 X 元」是按**参与分配股数**
    (总股本剔除回购专户后)折算的,而 share_structure 里存的是**含回购股的
    总股本**。两者口径不同,用「每10股 × 年末总股本」反推会系统性偏大
    (东阿阿胶 2020-2022 三年偏大 1.56%)。

    公告直接披露的「现金分红总额」才是权威分子(与年报「利润分配预案」
    和官方现金分红比例同口径)。

    覆盖的句式(实测东阿阿胶 13 份公告):
      1. 「现金分红总额为 425,113,999.05 元」
      2. 「（现金红利派发总额÷参与利润分配的总股数）×10=817,850,566.48元÷…」
      3. 「合计派发现金总额为 588,619,383.30 元」
    """
    if not text:
        return None
    flat = text.replace(" ", "").replace("\n", "").replace(" ", "")

    patterns = (
        # 句式 1:最明确,优先
        r"现金分红总额为([0-9,]+\.?[0-9]*)元",
        # 句式 3:早期公告
        r"合计派发现金总额为([0-9,]+\.?[0-9]*)元",
        # 句式 4:每股派现型公告(600285 表述)
        r"共计派发现金红利([0-9,]+\.?[0-9]*)元",
        # 句式 2:折算公式
        r"×10=([0-9,]+\.?[0-9]*)元",
    )
    for pat in patterns:
        m = re.search(pat, flat)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except (TypeError, ValueError):
                continue
    return None


def _parse_dividend_announcement_title(title: str) -> tuple[int | None, str]:
    """从公告标题解析「分配年度」与「分配性质」。

    Returns:
        (year, kind) —— year 是**分配年度**(公告标题里的年份),
        kind 是 'annual'(年度分配) / 'interim'(半年度分配)。
        解析不出年份时返回 (None, 'annual')。

    为什么不能按发布时间归年:「2024年半年度权益分派实施公告」发布于 2024-08,
    若按「发布年 - 1」归年会落到 2023,与「2024年年度权益分派实施公告」
    (发布于 2025-06)撞在同一年,后入库的半年度数值会覆盖年度数值 ——
    实测东阿阿胶 2023/2024/2025 三年的分红率因此算错。
    """
    if not title:
        return None, "annual"
    flat = title.replace(" ", "").replace("　", "")
    m = re.search(r"(20\d{2})年(半年度|年度)?", flat)
    if not m:
        return None, "annual"
    year = int(m.group(1))
    kind = "interim" if m.group(2) == "半年度" else "annual"
    return year, kind


def _extract_dividend_from_pdf(pdf_path: str) -> dict:
    """从权益分派实施公告 PDF 提取分红数据。

    解析策略:
    1. 优先 "本次实际派发现金红利人民币 0.XXXXX 元/股" 或 "每股现金红利人民币 0.XXXXX 元"
    2. 回退 "除权(息)参考价格=(前收盘价格-0.XXXXX)" 反推
    3. 提取 "股权登记日总股本为 X,XXX,XXX 股" → total_shares
    4. 提取 "每 10 股派 X.XX 元" → 优先用这个(财会标准披露)
    5. 提取 "现金分红总额为 X 元" → cash_dividend_total(**权威分子**)

    Returns:
        {'cash_per_share': float, 'cash_per_10_shares': float,
         'total_shares': int | None, 'event_date': str | None}
    """
    import re
    import pdfplumber  # type: ignore
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        # 读前 6 页并逐页检查是否已拿到「现金分红总额」。
        # 原实现只看前 3 页且遇到"现金红利+股权登记/总股本"就 break,
        # 万一总额句在更后面就漏掉 —— 分红率会退回到
        # 「每10股派息 × 年末总股本」的反推口径(偏大)。
        # 实测东阿阿胶/羚锐制药的公告总额都在前 3 页内,这里是稳健性冗余。
        for page in pdf.pages[:6]:
            t = page.extract_text() or ""
            text += t + "\n"
            # 已拿到「总额」就可以停(它是最权威的分子)
            if _extract_dividend_total(text) is not None:
                break

    out: dict = {
        'cash_per_share': None, 'cash_per_10_shares': None,
        'total_shares': None, 'event_date': None,
        'cash_dividend_total': None,   # 公告披露的现金分红总额(元)——权威分子
        'dividend_kind': 'annual',     # 'annual' 年度分配 / 'interim' 半年度分配
    }
    # 1. "每股实际派发现金红利人民币 0.XXXXX 元"
    m = re.search(
        r"每股(?:实际)?派发现金红利(?:人民币)?\s*([0-9]+\.?[0-9]*)\s*元", text
    )
    if not m:
        m = re.search(
            r"实际派发现金红利\s*人民币\s*([0-9]+\.?[0-9]*)\s*元", text
        )
    if not m:
        # "A股每股现金红利 0.80 元" (600285 2023 用此表述)
        m = re.search(
            r"[A-Z]?股每股现金红利\s*([0-9]+\.[0-9]+)\s*元", text
        )
    if not m:
        # 兜底:"每 X 股派 Y 元"
        m = re.search(
            r"每\s*([0-9]+)\s*股派[发]?\s*现金红利?\s*([0-9]+\.[0-9]+)\s*元", text
        )
        if m:
            shares, per = int(m.group(1)), float(m.group(2))
            out['cash_per_share'] = round(per / shares, 4)
            out['cash_per_10_shares'] = round(out['cash_per_share'] * 10, 4)
    if m and out['cash_per_share'] is None:
        out['cash_per_share'] = float(m.group(1))
        out['cash_per_10_shares'] = round(out['cash_per_share'] * 10, 4)

    # 2. "每 10 股派 X.XX 元"
    if out['cash_per_10_shares'] is None:
        m = re.search(
            r"每\s*10\s*股派?\s*(?:现)?金?红?利?\s*([0-9]+\.[0-9]+)\s*元", text
        )
        if m:
            out['cash_per_10_shares'] = float(m.group(1))
            out['cash_per_share'] = round(out['cash_per_10_shares'] / 10, 4)

    # 3. "(前收盘价格-0.XXXX)÷..." → 派息额
    if out['cash_per_share'] is None:
        m = re.search(
            r"前收盘价格\s*-\s*([0-9]+\.[0-9]+)\s*[)）]", text
        )
        if m:
            out['cash_per_share'] = float(m.group(1))
            out['cash_per_10_shares'] = round(out['cash_per_share'] * 10, 4)

    # 4. "总股本为 X,XXX,XXX 股" → total_shares
    m = re.search(
        r"总股本为\s*([0-9,]+)\s*股", text
    )
    if m:
        out['total_shares'] = int(m.group(1).replace(',', ''))

    # 5. 股权登记日
    m = re.search(
        r"股权登记日[为是:：]?\s*(\d{4})[年\-](\d{1,2})[月\-](\d{1,2})", text
    )
    if m:
        out['event_date'] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # 6. "现金分红总额为 X 元" → 权威分子(避免用「每10股 × 年末总股本」反推)
    out['cash_dividend_total'] = _extract_dividend_total(text)
    return out


def persist_dividend_to_db(
    stock_code: str,
    events: list[dict],
    source: str = "cninfo",
    company_name: str | None = None,
) -> int:
    """把分红事件列表持久化到 capital_change_events 表。

    Args:
        stock_code: 股票代码
        events: [{'report_year': int, 'cash_per_10_shares': float,
                  'cash_per_share': float, 'total_shares': int|None,
                  'event_date': str|None, 'announcement_title': str|None}]
        source: 数据来源标识
        company_name: 公司全称。缺省时从已入库的财报表按 stock_code 反查;
            查不到才退化为 ''。**不要**把 stock_code 塞进 company_name ——
            那是两个不同语义的字段,混用会让按公司名的查询查不到分红事件。
    Returns:
        新插入的记录数(同 (stock_code, report_year, event_type) 已存在则跳过)
    """
    from src.db.db_connector import get_db
    db = get_db()

    # company_name 缺省时按 stock_code 从财报表反查(财报表由 PDF 解析写入,
    # 是公司全称最可靠的来源)。查不到再退化为空串。
    if not company_name:
        try:
            row = db._duckdb_conn.execute(
                "SELECT company_name FROM consolidated_balance_sheet "
                "WHERE stock_code=? AND company_name IS NOT NULL "
                "AND company_name<>'' "
                "ORDER BY report_year DESC LIMIT 1",
                [stock_code],
            ).fetchone()
        except Exception:
            row = None
        company_name = (row[0] if row and row[0] else "") or ""

    # 取 share_structure 表里已有的总股本(每年)
    share_by_year: dict[int, int] = {}
    rows = db._duckdb_conn.execute(
        "SELECT report_year, total_shares FROM share_structure "
        "WHERE stock_code=? AND total_shares IS NOT NULL AND total_shares > 0",
        [stock_code],
    ).fetchall()
    for ry, ts in rows:
        if ts:
            share_by_year[ry] = int(ts)

    inserted = 0
    updated = 0
    for ev in events:
        cps = ev.get('cash_per_share')
        cps10 = ev.get('cash_per_10_shares')
        if cps is None and cps10 is not None:
            cps = round(cps10 / 10.0, 4)
        total_amt = ev.get('cash_dividend_total')
        if cps is None and cps10 is None and total_amt is None:
            continue
        ry = ev['report_year']
        kind = ev.get('dividend_kind') or 'annual'
        # 优先用 events 自带的 total_shares,否则从 share_structure 取
        total_shares = ev.get('total_shares') or share_by_year.get(ry)
        scheme = ev.get('announcement_title', '').split(' ')[0]

        # UPSERT(更新或初始化):已存在则刷新字段,不存在则插入。
        # dedup 键含 dividend_kind —— 同一年内年度分配与半年度分配是**两笔**
        # 独立的分红,不能互相覆盖(旧实现只有 (stock_code, report_year,
        # event_type),后入库的会顶掉先入库的)。
        #
        # 用 UPDATE 而非「已存在就 skip」是为了支持**重跑刷新**:
        # 公告解析规则改进后(比如新增了「现金分红总额」提取),重跑一次
        # 就该把新字段补进已有行,而不是因为 dedup 命中被跳过。
        existing = db._duckdb_conn.execute(
            "SELECT id FROM capital_change_events "
            "WHERE stock_code=? AND report_year=? AND event_type='cash_dividend' "
            "AND COALESCE(dividend_kind,'annual')=?",
            [stock_code, ry, kind],
        ).fetchone()
        if existing:
            row_id = existing[0]
            db._duckdb_conn.execute(
                "UPDATE capital_change_events SET "
                " company_name=?, event_date=?, cash_per_10_shares=?, total_shares=?, "
                " cash_dividend_total=COALESCE(?, cash_dividend_total), "
                " source=?, scheme_description=?, updated_at=CURRENT_TIMESTAMP "
                "WHERE id=?",
                [company_name, ev.get('event_date') or '1900-01-01',
                 cps10 or 0.0, total_shares, total_amt, source, scheme, row_id],
            )
            updated += 1
            continue

        # 插入
        db._duckdb_conn.execute(
            "INSERT INTO capital_change_events "
            "(company_name, stock_code, report_year, report_period, "
            " event_type, event_date, cash_per_10_shares, total_shares, "
            " cash_dividend_total, dividend_kind, source, scheme_description) "
            "VALUES (?, ?, ?, 'FY', 'cash_dividend', ?, ?, ?, ?, ?, ?, ?)",
            [company_name, stock_code, ry, ev.get('event_date') or '1900-01-01',
             cps10 or 0.0, total_shares, total_amt, kind, source, scheme],
        )
        inserted += 1
    if updated:
        logger.info("分红事件更新 %d 条(已存在,字段刷新)", updated)
    return inserted


def query_dividend_announcements_and_persist(
    stock_code: str, years: list[int],
) -> list[dict]:
    """一站式:query 巨潮权益分派公告 → 下载 PDF → 解析 → 入库。"""
    from pathlib import Path
    import os
    dl = CNInfoReportDownloader()
    anns = dl.query_dividend_announcements(stock_code, years)
    print(f"找到 {len(anns)} 条权益分派公告")
    pdf_dir = Path("data") / stock_code / "dividend_announcements"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    events = []
    for ann in anns:
        # 用 time_str 推断年份(实施公告发布在次年 5-7 月)
        from datetime import datetime
        ts = datetime.fromisoformat(ann['time_str'])
        # 下载
        url = f"https://static.cninfo.com.cn/{ann['adjunctUrl']}"
        local = pdf_dir / Path(ann['adjunctUrl']).name
        try:
            r = dl.session.get(url, headers={
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'http://www.cninfo.com.cn/',
            }, timeout=60)
            r.raise_for_status()
            local.write_bytes(r.content)
        except Exception as exc:
            print(f"下载 {ann['title']} 失败: {exc}")
            continue
        # 解析
        info = _extract_dividend_from_pdf(str(local))
        info['report_year'] = ann['year']
        info['announcement_title'] = ann['title']
        # 分配性质(年度/半年度)—— 决定 dedup 时能否与同年另一笔共存
        info['dividend_kind'] = ann.get('dividend_kind') or 'annual'
        events.append(info)
        print(
            f"  {ann['year']}[{info['dividend_kind']}] {ann['title'][:36]}... → "
            f"每股 {info['cash_per_share']}元 (10股 {info['cash_per_10_shares']}元)"
            f" 总额 {info['cash_dividend_total']}"
            f" 总股本 {info['total_shares']}"
        )
    # 入库
    n = persist_dividend_to_db(stock_code, events, source="cninfo")
    print(f"入库: {n} 条新事件")
    return events


def main():
    """主函数 - 下载年度报告"""
    import argparse

    parser = argparse.ArgumentParser(description='巨潮资讯网年度报告下载器')
    parser.add_argument('code_or_name', nargs='?', default='000423',
                        help='股票代码（如000423）或公司名称（如东阿阿胶）')
    parser.add_argument('--years', '-y', type=str, default='2015-2025',
                        help='年份范围，格式：2015-2025 或 2015,2016,2020')

    args = parser.parse_args()

    # 解析年份
    if '-' in args.years:
        start, end = args.years.split('-')
        years = list(range(int(start), int(end) + 1))
    elif ',' in args.years:
        years = [int(y.strip()) for y in args.years.split(',')]
    else:
        years = [int(args.years)]

    downloader = CNInfoReportDownloader()

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    print("=" * 60)
    print("巨潮资讯网年度报告下载器")
    print("=" * 60)
    print(f"查询条件: {args.code_or_name}")
    print(f"年份范围: {years}")

    print("=" * 60)

    downloader.download_reports(args.code_or_name, years, project_root)


if __name__ == "__main__":
    main()

    # .\script\download_report.bat "东阿阿胶" -y 2015-2026
