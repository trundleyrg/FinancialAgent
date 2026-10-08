# Visualization Module Usage

`src/tools/visualization.py` 把 `{period: {metric: value}}` 形式的连续 N 期数据
渲染成 PNG 趋势图和/或 pandas DataFrame。

## 三个公开 API

### `build_trend_table(series, *, series_labels=None, value_formatter=None) -> pd.DataFrame`

把数据展平成宽表，**不依赖 matplotlib**，可以在任何上下文（单元测试、
DB 写表、前端 JSON 序列化）单独使用。

```python
df = build_trend_table({
    "2021": {"营收": 38.5e8, "净利": 4.4e8},
    "2022": {"营收": 40.4e8, "净利": 7.8e8},
})
# index=period, columns=营收/净利（按首次出现顺序）
```

### `plot_multi_series_trend(series, *, output_path, layout="auto", ..., metric_explanations=None) -> Path`

渲染 PNG 到 `output_path`。`layout` 自动规则：

| 指标数 | 行为 |
|---|---|
| 1 | `single`（1×1） |
| 2 | `twinx`（左右双 Y 轴，左实线 + 右虚线） |
| 3+ | `subplot`（上下堆叠，共享 X 轴） |

显式 `layout="subplot"` 可强制覆盖。

`metric_explanations`（可选，`dict[str, str]`）— 在图片下方居中渲染多行「指标名：解释文本」，常用于把计算公式/定义挂在图上。dict 的 key 应与 `series` 中的 metric 名（或 `series_labels` 映射后的显示名）保持一致，文本由调用方提供。None / 空 dict 不渲染。

```python
plot_multi_series_trend(
    series,
    output_path="dividend_trend.png",
    metric_explanations={
        "分红率(%)": "现金分红 / 归母净利润 × 100",
        "营业收入(亿元)": "主营业务收入合计",
    },
)
```

### `render_trend_chart_and_table(series, *, output_path, ..., metric_explanations=None) -> tuple[Path, DataFrame]`

combine：写图 + 返回表。图与表共享同一份 `series` 数据，保证口径一致。

## 中文字体兼容

`font.sans-serif` 按下列顺序 fallback：

```
PingFang SC → Hiragino Sans GB → Heiti SC → WenQuanYi Zen Hei
→ Noto Sans CJK SC → Source Han Sans CN → Microsoft YaHei → SimHei → DejaVu Sans
```

系统找不到 CJK 字体时降级到 DejaVu Sans。

## 周期股复用

未来 commodity price 入 DB 后，直接复用 `plot_multi_series_trend`：

```python
series = {
    "2021": {"螺纹钢": 5200, "铜": 68000, "铝": 18500},
    "2022": {"螺纹钢": 4100, "铜": 65000, "铝": 17800},
}
plot_multi_series_trend(series, x_label="年份", output_path="...")
# 3 指标 → 自动 subplot
```

## 集成到 Skill

dividend skill 已经把 wrapper（`render_dividend_trend_chart`）接进去：

- PNG 路径：`data/{stock_code}/memory/charts/dividend_trend_{year}.png`
- CSV 路径：同名 `.csv`
- 表格 dict（供 SQL `json_extract`）：写进 `skill_analysis_results.input_context.table_dict`
- 指标解释（计算公式）：由 `skill.py` 通过 `metric_explanations` 透传，渲染在图片下方居中位置。dividend skill 目前会传分红率公式说明。
