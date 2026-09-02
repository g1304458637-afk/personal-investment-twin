# Market Data Contract

## Purpose

为 Selection Evidence 和后续 Decision Attribution 提供统一的市场参考数据。

上层分析不得依赖具体数据供应商。

数据可以来自：

- Local frozen data
- BigQuant
- 同花顺 Financial API
- 其他后续 Provider

但进入分析层前必须转换成统一格式。

---

## 1. Price Series

标准字段：

- `date`
- `instrument`
- `close`
- `price_type`
- `data_source`
- `data_version`
- `is_synthetic`

要求：

- `date`：交易日期
- `instrument`：股票或指数唯一标识
- `close`：用于收益计算的价格
- `price_type`：价格口径
- `data_source`：数据来源
- `data_version`：本地冻结版本或供应商版本
- `is_synthetic`：是否为合成测试数据

### price_type

第一版允许：

- `adjusted_close`
- `total_return`
- `synthetic`

真实股票数据优先使用复权或总回报口径。

禁止在未处理分红、拆股等公司行为时，把裸价格变化描述成严格的投资总回报。

---

## 2. Industry Membership

标准字段：

- `symbol`
- `industry_id`
- `industry_name`
- `valid_from`
- `valid_to`
- `classification`
- `data_source`
- `data_version`
- `is_synthetic`

行业归属必须支持 point-in-time 语义。

也就是说：

分析某个 Episode 时，必须使用该 Episode 开始时有效的行业归属。

禁止：

使用当前行业分类直接倒填历史 Episode。

---

## 3. Benchmark Mapping

标准字段：

- `benchmark_id`
- `benchmark_name`
- `benchmark_type`

`benchmark_type` 第一版允许：

- `market`
- `industry`

比赛 MVP：

- Market Benchmark：CSI300
- Industry Benchmark：Episode 开始时对应的行业指数

---

## 4. Provider Boundary

Provider 只负责：

- 读取数据
- 字段映射
- 类型转换
- 基础完整性检查
- 返回统一 Market Data Contract

Provider 不负责：

- PnL
- TWR
- Alpha
- Selection Skill
- Behavioral Analytics
- Investor DNA
- LLM explanation

这些属于上层分析模块。

---

## 5. Offline Demo

比赛 Demo 默认优先使用本地冻结数据。

目录建议：

data/reference/

本地数据必须记录：

- 来源
- 版本
- 是否 synthetic

Synthetic fixture 不得描述为真实历史市场数据。

---

## 6. Failure Rules

遇到以下情况不得猜测：

- Episode 时间段行情缺失
- Benchmark 行情缺失
- 历史行业归属无法确认
- 价格口径未知
- 数据来源无法追溯

上层必须能够返回：

`insufficient_evidence`

并说明原因。
