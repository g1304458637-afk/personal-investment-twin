"""券商导出（东方财富 / 同花顺）CSV 识别与转换测试。

固件内嵌两种券商的代表性导出文本（GBK/UTF-8/UTF-8-BOM 编码成 bytes），
并直接调用 ``preview_generic_csv`` 做集成断言：转换结果必须能被既有
generic_csv_v1 管道原样吃下。
"""

from __future__ import annotations

from datetime import date

import pytest

from src.ingestion.broker_csv import (
    BROKER_EASTMONEY,
    BROKER_THS,
    convert_to_generic_csv,
    detect_broker_format,
)
from src.ingestion.generic_csv import GenericCsvImportConfig, preview_generic_csv

CONFIG = GenericCsvImportConfig(subject_id="SUBJECT-1", account_id="ACC-1")

# --- 东方财富：GBK，日期 20241231，时间 093105，费用为分项列 -----------------
EASTMONEY_GBK_TEXT = (
    "成交日期,成交时间,证券代码,证券名称,买卖方向,成交价格,成交数量,成交金额,成交编号,佣金,印花税,过户费\n"
    "20241231,093105,600519,贵州茅台,买入,1500.00,100,150000.00,1001,15.00,150.00,10.00\n"
    "20241231,093105,600519,贵州茅台,卖出,1510.50,100,151050.00,1002,15.11,151.05,10.00\n"
    "20241231,145501,000858,五粮液,买入,128.50,1200,154200.00,1003,12.00,0.00,1.50\n"
)

# --- 东方财富变体：UTF-8 BOM，横线日期，全角空格表头，(元)后缀，千分位，
# 费用为总额列（手续费）+分项列并存，总额列优先 --------------------------------
EASTMONEY_BOM_TEXT = (
    "成交日期,成交时间,证券代码,证券名称,买　卖　方向,成交价格(元),成交数量(股),成交金额(元),手续费,佣金,印花税\n"
    '2024-12-31,09:31:05,600519,贵州茅台,买入,"1,500.00",100,"150,017.50",17.61,15.00,151.05\n'
)

# --- 同花顺：GBK，斜线日期，证券买入/卖出，第三行仅到分钟 -------------------
THS_GBK_TEXT = (
    "日期,时间,代码,名称,操作,成交价,数量,成交额,佣金,印花税,过户费\n"
    "2024-12-31,09:31:05,600519,贵州茅台,证券买入,1500.00,100,150000,15.00,150.00,10.00\n"
    "2024-12-31,09:31:05,600519,贵州茅台,证券卖出,1510.50,100,151050,15.11,151.05,10.00\n"
    "2024/12/31,14:55,000858,五粮液,买,128.50,1200,154200,12.00,0.00,1.50\n"
)

# --- 同花顺变体：UTF-8，8 位数字日期与紧凑时间混排 --------------------------
THS_UTF8_TEXT = (
    "日期,时间,代码,名称,操作,成交价,数量,佣金,印花税,过户费\n"
    "20241231,093105,600519,贵州茅台,证券买入,1500.00,100,15.00,150.00,10.00\n"
)

GENERIC_TEXT = (
    "event_time,symbol,side,quantity,price,fee,time_precision\n"
    "2025-01-02 09:30:00+08:00,600519,BUY,100,10.0,1,second\n"
)

EASTMONEY_NO_TIME_TEXT = (
    "成交日期,证券代码,证券名称,买卖方向,成交价格,成交数量,佣金,印花税,过户费\n"
    "20241231,600519,贵州茅台,买入,1500.00,100,15.00,150.00,10.00\n"
)

EASTMONEY_MISSING_PRICE_TEXT = (
    "成交日期,成交时间,证券代码,证券名称,买卖方向,成交数量,成交金额\n"
    "20241231,093105,600519,贵州茅台,买入,100,150000.00\n"
)

THS_UNSUPPORTED_SIDE_TEXT = (
    "日期,时间,代码,名称,操作,成交价,数量\n"
    "2024-12-31,09:31:05,600519,贵州茅台,融资买入,1500.00,100\n"
)


def _gbk(text: str) -> bytes:
    return text.encode("gbk")


def _new(preview):
    return tuple(
        row.candidate for row in preview.rows if row.candidate is not None
    )


# --- detect_broker_format ----------------------------------------------------


def test_detect_eastmoney_gbk():
    assert detect_broker_format(_gbk(EASTMONEY_GBK_TEXT)) == BROKER_EASTMONEY


def test_detect_eastmoney_utf8_bom_variant_headers():
    raw = b"\xef\xbb\xbf" + EASTMONEY_BOM_TEXT.encode("utf-8")
    assert detect_broker_format(raw) == BROKER_EASTMONEY


def test_detect_ths_gbk_and_utf8():
    assert detect_broker_format(_gbk(THS_GBK_TEXT)) == BROKER_THS
    assert detect_broker_format(THS_UTF8_TEXT.encode("utf-8")) == BROKER_THS


def test_detect_returns_none_for_generic_or_unknown_content():
    assert detect_broker_format(GENERIC_TEXT.encode("utf-8")) is None
    assert detect_broker_format("随便什么文本".encode("utf-8")) is None
    assert detect_broker_format(b"") is None


def test_detect_returns_none_for_undecodable_bytes():
    # \x81\x7f 在 GB18030 中是不合法的双字节序列，也不是合法 UTF-8。
    assert detect_broker_format(b"name,amount\r\n\x81\x7f,1\r\n") is None


# --- 编码回退 ----------------------------------------------------------------


def test_encoding_fallback_gbk_and_utf8_produce_identical_output():
    ths_text = THS_GBK_TEXT
    from_gbk = convert_to_generic_csv(ths_text.encode("gbk"), BROKER_THS)
    from_utf8 = convert_to_generic_csv(ths_text.encode("utf-8"), BROKER_THS)
    assert from_gbk == from_utf8
    assert from_gbk.startswith("event_time,time_precision,symbol,side,quantity,price,fee")


def test_undecodable_bytes_raise_chinese_value_error():
    with pytest.raises(ValueError, match="编码"):
        convert_to_generic_csv(b"name,amount\r\n\x81\x7f,1\r\n", BROKER_THS)


# --- convert_to_generic_csv --------------------------------------------------


def test_convert_eastmoney_fee_parts_summed_and_order_preserved():
    converted = convert_to_generic_csv(_gbk(EASTMONEY_GBK_TEXT), BROKER_EASTMONEY)
    lines = converted.strip().splitlines()
    assert lines[0] == (
        "event_time,time_precision,symbol,side,quantity,price,fee,source_execution_id"
    )
    # 行序保持原序，不去重（前两行是同一标的同价不同方向的独立成交）。
    assert lines[1] == "2024-12-31 09:31:05+08:00,second,600519,BUY,100,1500.00,175,1001"
    assert lines[2] == "2024-12-31 09:31:05+08:00,second,600519,SELL,100,1510.50,176.16,1002"
    assert lines[3] == "2024-12-31 14:55:01+08:00,second,000858,BUY,1200,128.50,13.5,1003"


def test_convert_eastmoney_fee_total_column_wins_over_parts():
    converted = convert_to_generic_csv(
        b"\xef\xbb\xbf" + EASTMONEY_BOM_TEXT.encode("utf-8"), BROKER_EASTMONEY
    )
    lines = converted.strip().splitlines()
    # 手续费(总额)17.61 优先，不与佣金/印花税分项重复累计；千分位被清洗。
    assert lines[1] == "2024-12-31 09:31:05+08:00,second,600519,BUY,100,1500.00,17.61"
    assert "source_execution_id" not in lines[0]


def test_convert_ths_minute_precision_row():
    converted = convert_to_generic_csv(_gbk(THS_GBK_TEXT), BROKER_THS)
    lines = converted.strip().splitlines()
    assert lines[0] == "event_time,time_precision,symbol,side,quantity,price,fee"
    assert lines[3] == "2024-12-31 14:55+08:00,minute,000858,BUY,1200,128.50,13.5"


def test_convert_ths_compact_date_and_time():
    converted = convert_to_generic_csv(THS_UTF8_TEXT.encode("utf-8"), BROKER_THS)
    assert converted.strip().splitlines()[1] == (
        "2024-12-31 09:31:05+08:00,second,600519,BUY,100,1500.00,175"
    )


def test_convert_without_time_column_uses_date_precision():
    converted = convert_to_generic_csv(_gbk(EASTMONEY_NO_TIME_TEXT), BROKER_EASTMONEY)
    lines = converted.strip().splitlines()
    assert lines[0].split(",")[:3] == ["event_time", "time_precision", "symbol"]
    assert "fee" in lines[0].split(",")
    assert lines[1].split(",")[:2] == ["2024-12-31", "date"]


def test_convert_is_deterministic():
    raw = _gbk(THS_GBK_TEXT)
    assert convert_to_generic_csv(raw, BROKER_THS) == convert_to_generic_csv(raw, BROKER_THS)


def test_convert_rejects_unknown_broker():
    with pytest.raises(ValueError, match="券商类型"):
        convert_to_generic_csv(_gbk(THS_GBK_TEXT), "huatai")


def test_convert_missing_required_column_lists_names():
    with pytest.raises(ValueError) as excinfo:
        convert_to_generic_csv(_gbk(EASTMONEY_MISSING_PRICE_TEXT), BROKER_EASTMONEY)
    message = str(excinfo.value)
    assert "缺少必需列" in message
    assert "成交价格" in message


def test_convert_unsupported_side_fails_with_chinese_message():
    with pytest.raises(ValueError) as excinfo:
        convert_to_generic_csv(_gbk(THS_UNSUPPORTED_SIDE_TEXT), BROKER_THS)
    message = str(excinfo.value)
    assert "融资买入" in message
    assert "方向" in message


def test_convert_empty_required_cell_fails_with_row_number():
    raw = _gbk(
        "日期,时间,代码,操作,成交价,数量\n"
        "2024-12-31,09:31:05,,买入,1500.00,100\n"
    )
    with pytest.raises(ValueError, match="第 1 行"):
        convert_to_generic_csv(raw, BROKER_THS)


def test_convert_invalid_date_fails_with_chinese_message():
    raw = _gbk(
        "日期,时间,代码,操作,成交价,数量\n"
        "2024/13/31,09:31:05,600519,买入,1500.00,100\n"
    )
    with pytest.raises(ValueError, match="成交日期"):
        convert_to_generic_csv(raw, BROKER_THS)


def test_convert_unlocatable_header_raises_for_forced_broker():
    with pytest.raises(ValueError, match="表头"):
        convert_to_generic_csv(_gbk(GENERIC_TEXT), BROKER_THS)


# --- 集成断言：转换结果能被 preview_generic_csv 直接吃下 ----------------------


def test_converted_eastmoney_feeds_generic_preview():
    converted = convert_to_generic_csv(_gbk(EASTMONEY_GBK_TEXT), BROKER_EASTMONEY)
    preview = preview_generic_csv(converted, config=CONFIG)

    assert preview.summary.total_rows == 3
    assert preview.summary.new_executions == 3
    assert preview.summary.invalid_rows == 0
    assert preview.summary.fee_issue_count == 0
    assert preview.date_range == ("2024-12-31", "2024-12-31")

    items = _new(preview)
    assert [item.side for item in items] == ["BUY", "SELL", "BUY"]
    assert [item.instrument.local_symbol for item in items] == ["600519", "600519", "000858"]
    assert [item.source_execution_id for item in items] == ["1001", "1002", "1003"]

    first = items[0]
    assert first.event_time.precision == "second"
    assert first.event_time.calendar_date == date(2024, 12, 31)
    assert first.event_time.instant_utc.isoformat() == "2024-12-31T01:31:05+00:00"
    assert (first.executed_quantity, first.executed_price) == (100.0, 1500.0)
    assert first.fee.status == "known_nonzero"
    assert first.fee.amount == pytest.approx(175.0)

    assert preview.column_mapping is not None
    fields = dict(preview.column_mapping.fields)
    assert fields["fee"] == "fee"
    assert fields["source_execution_id"] == "source_execution_id"


def test_converted_ths_minute_row_feeds_generic_preview_without_timezone_config():
    converted = convert_to_generic_csv(_gbk(THS_GBK_TEXT), BROKER_THS)
    preview = preview_generic_csv(converted, config=CONFIG)

    assert preview.summary.invalid_rows == 0
    minute_row = _new(preview)[2]
    assert minute_row.event_time.precision == "minute"
    assert minute_row.event_time.instant_utc.isoformat() == "2024-12-31T06:55:00+00:00"


def test_converted_date_only_row_feeds_generic_preview():
    converted = convert_to_generic_csv(_gbk(EASTMONEY_NO_TIME_TEXT), BROKER_EASTMONEY)
    preview = preview_generic_csv(converted, config=CONFIG)

    assert preview.summary.invalid_rows == 0
    item = _new(preview)[0]
    assert item.event_time.precision == "date"
    assert item.event_time.instant_utc is None
    assert item.event_time.calendar_date == date(2024, 12, 31)


def test_converted_bytes_round_trip_through_wiring_path():
    """模拟集成接线：detect 命中 → convert → 既有管道接受 bytes。"""

    raw = b"\xef\xbb\xbf" + EASTMONEY_BOM_TEXT.encode("utf-8")
    broker = detect_broker_format(raw)
    assert broker == BROKER_EASTMONEY
    converted = convert_to_generic_csv(raw, broker).encode("utf-8")
    preview = preview_generic_csv(converted, config=CONFIG)
    assert preview.summary.new_executions == 1
    item = _new(preview)[0]
    assert item.fee.amount == pytest.approx(17.61)
    assert (item.executed_quantity, item.executed_price) == (100.0, 1500.0)


def test_product_runtime_accepts_eastmoney_export(tmp_path):
    """Integration: an eastmoney-format export goes through ProductRuntime
    preview without manual reformatting, and the detect->convert hook fires
    before the generic parser (integrator wiring in product._trade_preview)."""
    from toujing_core_runtime.product import ProductRuntime

    csv_text = (
        "成交日期,成交时间,证券代码,证券名称,买卖方向,成交价格,成交数量,成交金额,手续费,成交编号\n"
        "20260901,093105,600000,浦发银行,买入,12.34,1000,\"12,340.00\",5.64,100001\n"
        "20260902,14:55,600000,浦发银行,卖出,12.85,1000,\"12,850.00\",7.21,100002\n"
    )
    path = tmp_path / "export.csv"
    path.write_bytes(csv_text.encode("gb18030"))
    runtime = ProductRuntime(tmp_path / "db")
    params = {"file_path": str(path), "subject_id": "local-user", "account_id": "ACC-1",
              "display_name": "Broker", "use_source_row_order_as_sequence": True,
              "initial_cash": 100000, "imported_at": "2026-09-04T12:00:00Z"}
    preview = runtime.preview_trade(params)
    assert preview["summary"]["new_executions"] == 2
    assert all(row["status"] == "new_execution" for row in preview["rows"])

    params["expected_file_sha256"] = preview["batch"]["file_sha256"]
    params["expected_preview_fingerprint"] = preview["preview_fingerprint"]
    assert runtime.commit_trade(params)["inserted_executions"] == 2
    runtime.close()
