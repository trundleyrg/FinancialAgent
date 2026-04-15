import akshare as ak

# 只返回的字段列表（对应 xq.md 中"是否返回"=1 的项）
RETURN_FIELDS = {
    "org_name_cn",           # 公司中文全称
    "org_short_name_cn",      # 公司中文简称
    "main_operation_business", # 主营业务
    "operating_scope",        # 经营范围
    "org_cn_introduction",    # 公司简介
    "org_website",            # 官网
    "listed_date",            # 上市日期
    "provincial_name",        # 所在省份
    "classi_name",            # 分类名称
    "affiliate_industry",    # 所属行业
}

symbol = "SZ000423"
stock_individual_basic_info_xq_df = ak.stock_individual_basic_info_xq(symbol=symbol)

# 只保留"是否返回"=1 的字段，转为字典
result_dict = {
    row["item"]: row["value"]
    for _, row in stock_individual_basic_info_xq_df.iterrows()
    if row["item"] in RETURN_FIELDS
}

print(result_dict)
