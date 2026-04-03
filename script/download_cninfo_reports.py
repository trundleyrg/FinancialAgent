"""
下载巨潮资讯网上市公司年度报告
"""
import os
import requests
import time
import re

class CNInfoReportDownloader:
    """巨潮资讯网年度报告下载器"""
    
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
        """获取股票信息，包括orgId和板块"""
        url = "http://www.cninfo.com.cn/new/data/szse_stock.json"
        try:
            resp = self.session.get(url, headers=self.headers, timeout=10)
            resp.raise_for_status()
            stock_list = resp.json().get("stockList", [])
            
            for stock in stock_list:
                if stock['code'] == stock_code:
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
            
            print(f"未找到股票代码 {stock_code} 的信息")
            return None
        except Exception as e:
            print(f"获取股票信息失败: {e}")
            return None
    
    def query_annual_reports(self, stock_code: str, org_id: str, column: str, plate: str, years: list) -> list:
        """查询年度报告列表"""
        reports = []
        url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"

        for year in years:
            found_valid = False

            # 首先在当年搜索，如果找到已取消的报告，则在后一年继续搜索
            for search_year in [int(year) + 1, int(year) + 2]:  # 先搜次年，再搜第三年
                if found_valid:
                    break

                se_date = f"{search_year}-01-01~{search_year}-12-31"  # 扩大搜索范围到全年

                data = {
                    'pageNum': '1',
                    'pageSize': '30',
                    'tabName': 'fulltext',
                    'stock': f'{stock_code},{org_id}',
                    'seDate': se_date,
                    'column': column,
                    'category': 'category_ndbg_szsh',  # 年度报告
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

                    announcements = result.get('announcements', [])
                    if not announcements:
                        print(f"  {search_year}年未找到任何公告")
                    for ann in announcements:
                        title = ann.get('announcementTitle', '')

                        # 检查是否已取消
                        if "已取消" in title:
                            print(f"  {year} 年度报告已取消，继续寻找...")
                            continue

                        # 检查是否是有效的年度报告
                        if self._is_valid_annual_report(title, year):
                            reports.append({
                                'title': title,
                                'year': year,
                                'adjunctUrl': ann.get('adjunctUrl', ''),
                                'announcementId': ann.get('announcementId', ''),
                                'secName': ann.get('secName', ''),
                                'announcementTime': ann.get('announcementTime', ''),
                            })
                            print(f"  找到 {year} 年度报告: {title} (来源: {search_year}年)")
                            found_valid = True
                            break

                    time.sleep(0.5)  # 避免请求过快

                except Exception as e:
                    print(f"查询 {year} 年度报告失败: {e}")

            if not found_valid:
                print(f"  未找到 {year} 年度有效报告")

        return reports
    
    def _is_valid_annual_report(self, title: str, year: str) -> bool:
        """判断是否是有效的年度报告"""
        title_lower = title.lower()
        year_in_title = str(year) in title or f"{int(year)+1}" in title
        
        # 排除无效的报告
        exclude_keywords = ['摘要', '英文', '已取消', '季度', '半年度', '半年报', 
                          '补充公告', '补充说明', '决议公告', '修订公告', '季报',
                          '摘要版', '主要财务指标']
        
        for keyword in exclude_keywords:
            if keyword in title:
                return False
        
        # 必须包含"年度报告"且年份匹配
        if '年度报告' in title or '年报' in title:
            return True
        
        return False
    
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
            print(f"  下载中: {filename}")
            resp = self.session.get(pdf_url, headers=download_headers, timeout=60)
            resp.raise_for_status()
            
            full_path = os.path.join(save_path, filename)
            with open(full_path, 'wb') as f:
                f.write(resp.content)
            
            print(f"  下载成功: {filename}")
            return True
            
        except Exception as e:
            print(f"  下载失败: {e}")
            return False
    
    def download_reports(self, stock_code: str, years: list, save_dir: str = None):
        """下载指定股票的年度报告"""
        # 获取股票信息
        stock_info = self.get_stock_info(stock_code)
        if not stock_info:
            return False
        
        print(f"\n股票信息: {stock_info['code']} {stock_info['name']}")
        print(f"orgId: {stock_info['orgId']}, 板块: {stock_info['plate']}")
        
        # 设置保存目录
        if save_dir is None:
            save_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', stock_code)
        
        os.makedirs(save_dir, exist_ok=True)
        print(f"保存目录: {save_dir}")
        
        # 查询年度报告
        print(f"\n查询 {stock_code} {years} 年度报告...")
        reports = self.query_annual_reports(
            stock_code, 
            stock_info['orgId'],
            stock_info['column'],
            stock_info['plate'],
            years
        )
        
        if not reports:
            print("未找到任何年度报告")
            return False
        
        print(f"\n共找到 {len(reports)} 份年度报告，开始下载...")
        
        # 下载PDF
        success_count = 0
        for report in reports:
            # 清理公司简称中的非法字符
            clean_name = re.sub(r'[<>:"/\\|?*]', '', stock_info['name'])
            filename = f"{clean_name}_{stock_code}_{report['year']}.pdf"
            
            if self.download_pdf(report['adjunctUrl'], save_dir, filename):
                success_count += 1
            
            time.sleep(1)  # 避免下载过快
        
        print(f"\n下载完成: 成功 {success_count}/{len(reports)}")
        return True


def main():
    """主函数 - 下载年度报告"""
    downloader = CNInfoReportDownloader()
    
    # 东阿阿胶股票代码: 000423
    stock_code = "000423"

    # 下载过去十年的年度报告
    years = list(range(2015, 2026))
    
    # 保存目录
    project_root = os.path.dirname(os.path.dirname(__file__))
    save_dir = os.path.join(project_root, 'data', stock_code)
    
    print("=" * 60)
    print("巨潮资讯网年度报告下载器")
    print("=" * 60)
    print(f"股票代码: {stock_code}")
    print(f"年份范围: {years}")
    print(f"保存目录: {save_dir}")
    print("=" * 60)
    
    downloader.download_reports(stock_code, years, save_dir)


if __name__ == "__main__":
    main()
