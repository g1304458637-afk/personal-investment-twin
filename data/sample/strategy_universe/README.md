# 合成策略股票池（strategy_universe）

本目录数据 100% 合成，由 `scripts/build_strategy_universe_fixtures.py` 确定性生成，与任何真实证券无关，
只能用于策略历史模拟（`src/strategy`）的教学演示与测试，不得用于宣称真实业绩。

- `universe.csv`：点时成员资格。`list_date` 前与 `delist_date` 起（含当日）不可选。
- `prices.csv`：未复权日度价格（工作日枚举，非真实交易所日历）。缺行 = 当日不可交易（停牌或缺失）。
  合成十一号在 2024-05-15 按 1:2 拆股，因此此前价格约为之后的两倍——这是引擎必须处理的未复权现实。
- `corporate_actions.csv`：公司行动（V1 仅支持 split）。

重新生成：`.venv/bin/python scripts/build_strategy_universe_fixtures.py`（输出应与提交内容逐字节一致）。
