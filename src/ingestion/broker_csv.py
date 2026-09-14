"""券商成交导出（东方财富 / 同花顺）到 ``generic_csv_v1`` 的确定性转换适配器。

公开接口（集成接线契约，签名不可偏离）::

    detect_broker_format(raw: bytes) -> str | None
    convert_to_generic_csv(raw: bytes, broker: str) -> str

设计边界（产品诚实原则）：列名映射基于 2026 年前的常见导出版本，
券商导出版本可能变化；识别失败时用户应改用 generic_csv_v1 格式
（参见 ``data/reference/broker_column_aliases.md``）手工整理后导入。
仅支持 CSV 文本：现有导入管道 ``preview_generic_csv`` 只接受 UTF-8
CSV 文本，不支持 Excel；Excel 工作簿请先另存为 CSV 再导入。

口径要点：

- 编码探测顺序：UTF-8 BOM → UTF-8 → GB18030；全部失败抛 ``ValueError``。
- 时间：A股成交记录为北京时间（UTC+08:00，无夏令时）。导出带时间列时
  合成 ``YYYY-MM-DD HH:MM[:SS]+08:00``（精度 second/minute），用文件内
  显式偏移量满足 generic_csv_v1 对 naive timed 事实的 fail-closed 时区
  要求；无时间列（或时间单元格为空）时输出 ``YYYY-MM-DD``（精度 date）。
- 方向：仅支持 买入/卖出（含 证券买入/证券卖出 等变体），映射为
  generic 枚举 ``BUY``/``SELL``；其余方向（融资买入、卖出开仓等）无法
  表达为该枚举，抛 ``ValueError``。
- 费用：generic_csv_v1 只有一个 ``fee`` 字段。若导出含“手续费”（总额
  列）则直接取该列；否则将 佣金+印花税+过户费+经手费+证管费+其他费
  求和，总额列与分项列不重复累计。文件完全没有费用列时不输出 ``fee``
  列（generic 记为 unknown，仅告警）；费用单元格为空按 0 计。
- 价格/数量/费用支持千分位逗号与“元”后缀；数量为整数时输出整数形式。
- 行序保持原文件顺序，不排序、不去重（重复检测由既有管道负责）。

本模块只做格式转换：能解析但违反 generic 数值约束的值（如非正价格、
负费用）原样交给 ``preview_generic_csv`` 按行标记 invalid，由预览呈现。
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping

__all__ = ["BROKER_EASTMONEY", "BROKER_THS", "convert_to_generic_csv", "detect_broker_format"]

BROKER_EASTMONEY = "eastmoney"
BROKER_THS = "ths"

_TIMEZONE_OFFSET = "+08:00"
_HEADER_SCAN_LIMIT = 10

# Full-width ASCII block (U+FF01..U+FF5E) folds onto ASCII; U+3000 folds to space.
_FULLWIDTH_MAP: dict[str, str] = {
    chr(0xFF01 + offset): chr(0x21 + offset) for offset in range(0x5E)
}
_FULLWIDTH_MAP["\u3000"] = " "

# Broker headers carry trailing unit suffixes like (元)/(股)/(人民币); strip them.
_UNIT_SUFFIX_PATTERN = re.compile(r"[([（\[]+[^)）\]]*[)\]）\]]+$")

# Field spec: canonical key -> (中文列名 label for error messages, aliases).
# ``fee_parts`` is special: every matching column is collected and summed.
_EASTMONEY_SPEC: Mapping[str, tuple[str, tuple[str, ...]]] = {
    "date": ("成交日期", ("成交日期",)),
    "time": ("成交时间", ("成交时间",)),
    "symbol": ("证券代码", ("证券代码", "代码")),
    "side": ("买卖方向", ("买卖方向", "交易方向", "方向", "操作")),
    "price": ("成交价格", ("成交价格", "成交价")),
    "quantity": ("成交数量", ("成交数量", "成交股数", "成交份额", "数量")),
    "fee_total": ("手续费", ("手续费", "费用", "总费用")),
    "fee_parts": (
        "费用分项",
        ("佣金", "印花税", "过户费", "经手费", "证管费", "其他费", "附加费"),
    ),
    "execution_id": ("成交编号", ("成交编号", "编号", "成交序号")),
}
_THS_SPEC: Mapping[str, tuple[str, tuple[str, ...]]] = {
    "date": ("日期", ("日期", "成交日期")),
    "time": ("时间", ("时间", "成交时间")),
    "symbol": ("代码", ("代码", "证券代码")),
    "side": ("操作", ("操作", "操作方向", "买卖方向", "方向", "交易方向")),
    "price": ("成交价", ("成交价", "成交价格", "价格")),
    "quantity": ("数量", ("数量", "成交数量", "成交股数", "成交份额")),
    "fee_total": ("手续费", ("手续费", "费用", "总费用")),
    "fee_parts": (
        "费用分项",
        ("佣金", "印花税", "过户费", "经手费", "证管费", "其他费", "附加费"),
    ),
    "execution_id": ("成交编号", ("成交编号", "编号", "成交序号")),
}
_BROKER_SPECS: Mapping[str, Mapping[str, tuple[str, tuple[str, ...]]]] = {
    BROKER_EASTMONEY: _EASTMONEY_SPEC,
    BROKER_THS: _THS_SPEC,
}
_REQUIRED_FIELDS = ("date", "symbol", "side", "price", "quantity")

# Direction variants observed in real exports; anything else fails closed.
_SIDE_MAP: Mapping[str, str] = {
    "买入": "BUY",
    "买": "BUY",
    "证券买入": "BUY",
    "买入证券": "BUY",
    "buy": "BUY",
    "b": "BUY",
    "卖出": "SELL",
    "卖": "SELL",
    "证券卖出": "SELL",
    "卖出证券": "SELL",
    "sell": "SELL",
    "s": "SELL",
}

_DATE_FORMATS = ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d")

_OUTPUT_HEADER = ("event_time", "time_precision", "symbol", "side", "quantity", "price")


def _decode_raw(raw: bytes) -> str:
    """UTF-8 BOM → UTF-8 → GB18030，全部失败抛中文 ``ValueError``。"""

    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("gb18030")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "无法识别文件编码：请将导出文件另存为 UTF-8 或 GBK 编码的 CSV 后重试"
        ) from exc


def _normalize_header(value: str) -> str:
    text = value.lstrip("\ufeff").translate(_FULLWIDTH_MAP)
    text = re.sub(r"\s+", "", text)
    return _UNIT_SUFFIX_PATTERN.sub("", text).casefold()


def _normalize_side(value: str) -> str:
    return re.sub(r"\s+", "", value.translate(_FULLWIDTH_MAP)).casefold()


def _read_rows(text: str) -> list[list[str]]:
    return [
        row
        for row in csv.reader(io.StringIO(text, newline=""))
        if any(cell.strip() for cell in row)
    ]


def _match_field(cells: set[str], aliases: tuple[str, ...]) -> bool:
    return any(alias in cells for alias in aliases)


def _score_row(cells: set[str], spec: Mapping[str, tuple[str, tuple[str, ...]]]) -> int:
    return sum(1 for _, (_, aliases) in spec.items() if _match_field(cells, aliases))


def _match_score(cells: set[str], spec: Mapping[str, tuple[str, tuple[str, ...]]]) -> int | None:
    """Required 核心列全部命中时返回命中字段数，否则 ``None``（用于 detect）。"""

    if not all(_match_field(cells, spec[field][1]) for field in _REQUIRED_FIELDS):
        return None
    return _score_row(cells, spec)


def _locate_header(
    rows: list[list[str]], broker: str
) -> tuple[int, dict[str, int], list[int]]:
    """返回 ``(表头行号, 单值字段→列号, 费用分项列号列表)``。

    在前若干行中选命中字段最多的一行作为表头；没有任何券商列命中时
    报“无法识别表头行”。必需列不全的情况留给调用方报缺列错误。
    """

    spec = _BROKER_SPECS[broker]
    best: tuple[int, dict[str, int], list[int]] | None = None
    best_score = 0
    for index, row in enumerate(rows[:_HEADER_SCAN_LIMIT]):
        cells = {_normalize_header(cell) for cell in row}
        score = _score_row(cells, spec)
        if best is not None and score <= best_score:
            continue
        columns: dict[str, int] = {}
        fee_part_indexes: list[int] = []
        for position, cell in enumerate(row):
            normalized = _normalize_header(cell)
            if not normalized:
                continue
            matched = False
            for field, (_, aliases) in spec.items():
                if field == "fee_parts":
                    continue
                if field not in columns and normalized in aliases:
                    columns[field] = position
                    matched = True
                    break
            if not matched and normalized in spec["fee_parts"][1]:
                fee_part_indexes.append(position)
        best = (index, columns, fee_part_indexes)
        best_score = score
    if best is None or best_score == 0:
        label = "东方财富" if broker == BROKER_EASTMONEY else "同花顺"
        raise ValueError(
            f"无法在文件前 {_HEADER_SCAN_LIMIT} 行内识别{label}导出的表头行；"
            "若导出版本较新，请改用 generic_csv_v1 格式整理后导入"
        )
    return best


def _cell(row: list[str], columns: Mapping[str, int], field: str) -> str:
    index = columns.get(field)
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _clean_number(raw: str) -> str:
    text = raw.translate(_FULLWIDTH_MAP)
    for char in (" ", ",", "元", "￥", "¥"):
        text = text.replace(char, "")
    return text.strip()


def _to_decimal(text: str, row_number: int, label: str, raw: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            f"第 {row_number} 行数据“{label}”列的值“{raw}”不是有效数字，无法转换"
        ) from exc
    if not value.is_finite():
        raise ValueError(
            f"第 {row_number} 行数据“{label}”列的值“{raw}”不是有限数字，无法转换"
        )
    return value


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _parse_date(raw: str, row_number: int) -> str:
    text = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(
        f"第 {row_number} 行数据的成交日期“{raw}”格式无法识别"
        "（支持 20241231、2024-12-31、2024/12/31、2024.12.31）"
    )


def _parse_clock(raw: str, row_number: int) -> tuple[str, str]:
    """返回 ``(HH:MM[:SS], precision)``；输入为空表示无时间（date 精度）。"""

    text = raw.strip()
    if not text:
        return "", "date"
    if ":" in text:
        parts = text.split(":")
        if len(parts) == 3:
            hour, minute, second, precision = parts[0], parts[1], parts[2], "second"
        elif len(parts) == 2:
            hour, minute, second, precision = parts[0], parts[1], "0", "minute"
        else:
            raise ValueError(f"第 {row_number} 行数据的成交时间“{raw}”格式无法识别")
        if not all(part.isdigit() for part in parts):
            raise ValueError(f"第 {row_number} 行数据的成交时间“{raw}”格式无法识别")
    else:
        digits = re.sub(r"\s+", "", text.translate(_FULLWIDTH_MAP))
        if not digits.isdigit():
            raise ValueError(f"第 {row_number} 行数据的成交时间“{raw}”格式无法识别")
        if len(digits) in (5, 6):
            digits = digits.zfill(6)
            hour, minute, second, precision = digits[:2], digits[2:4], digits[4:6], "second"
        elif len(digits) in (3, 4):
            digits = digits.zfill(4)
            hour, minute, second, precision = digits[:2], digits[2:4], "0", "minute"
        else:
            raise ValueError(f"第 {row_number} 行数据的成交时间“{raw}”格式无法识别")
    hour_i, minute_i, second_i = int(hour), int(minute), int(second)
    if not (0 <= hour_i <= 23 and 0 <= minute_i <= 59 and 0 <= second_i <= 59):
        raise ValueError(f"第 {row_number} 行数据的成交时间“{raw}”超出有效范围")
    clock = f"{hour_i:02d}:{minute_i:02d}"
    if precision == "second":
        clock = f"{clock}:{second_i:02d}"
    return clock, precision


def _missing_columns_error(broker: str, missing: list[str]) -> ValueError:
    label = "东方财富" if broker == BROKER_EASTMONEY else "同花顺"
    names = "、".join(_BROKER_SPECS[broker][field][0] for field in missing)
    return ValueError(
        f"{label}导出缺少必需列：{names}；"
        "若导出版本较新导致列名变化，请改用 generic_csv_v1 格式整理后导入"
    )


def detect_broker_format(raw: bytes) -> str | None:
    """返回 ``'eastmoney' | 'ths' | None``；基于表头行特征判断。

    输入为文件原始字节。仅支持 CSV 文本（现有管道不支持 Excel，
    Excel 字节无法解出可识别表头，返回 ``None``）。
    """

    try:
        text = _decode_raw(raw)
    except ValueError:
        return None
    best: tuple[int, str] | None = None
    for row in _read_rows(text)[:_HEADER_SCAN_LIMIT]:
        cells = {_normalize_header(cell) for cell in row}
        for broker, spec in _BROKER_SPECS.items():
            score = _match_score(cells, spec)
            if score is None:
                continue
            if best is None or score > best[0]:
                best = (score, broker)
    return best[1] if best is not None else None


def convert_to_generic_csv(raw: bytes, broker: str) -> str:
    """把券商导出文本转换为 ``generic_csv_v1`` 格式的 CSV 文本（含表头）。

    确定性、纯函数：同一输入字节永远产生同一输出文本。行序保持原序，
    不排序、不去重。必需列缺失、方向无法识别、数值无法解析时抛带中文
    说明的 ``ValueError``。
    """

    if broker not in _BROKER_SPECS:
        raise ValueError(f"不支持的券商类型：{broker!r}，仅支持 'eastmoney' 或 'ths'")
    rows = _read_rows(_decode_raw(raw))
    if not rows:
        raise ValueError("文件为空，没有可识别的表头行或数据行")
    header_index, columns, fee_part_indexes = _locate_header(rows, broker)
    spec = _BROKER_SPECS[broker]
    missing = [field for field in _REQUIRED_FIELDS if field not in columns]
    if missing:
        raise _missing_columns_error(broker, missing)

    fee_total_index = columns.get("fee_total")
    has_fee_columns = fee_total_index is not None or bool(fee_part_indexes)
    execution_id_index = columns.get("execution_id")

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    header = list(_OUTPUT_HEADER)
    if has_fee_columns:
        header.append("fee")
    if execution_id_index is not None:
        header.append("source_execution_id")
    writer.writerow(header)

    for offset, row in enumerate(rows[header_index + 1 :], start=1):
        date_raw = _cell(row, columns, "date")
        if not date_raw:
            raise ValueError(f"第 {offset} 行数据缺少{spec['date'][0]}，无法转换")
        date_text = _parse_date(date_raw, offset)
        clock, precision = _parse_clock(_cell(row, columns, "time"), offset)
        if precision == "date":
            event_time = date_text
        else:
            event_time = f"{date_text} {clock}{_TIMEZONE_OFFSET}"

        symbol = _cell(row, columns, "symbol")
        if not symbol:
            raise ValueError(f"第 {offset} 行数据缺少{spec['symbol'][0]}，无法转换")
        side_raw = _cell(row, columns, "side")
        side = _SIDE_MAP.get(_normalize_side(side_raw))
        if side is None:
            raise ValueError(
                f"第 {offset} 行数据的方向“{side_raw}”无法识别："
                "generic_csv_v1 仅支持 买入/卖出（BUY/SELL）"
            )

        price_raw = _cell(row, columns, "price")
        price_text = _clean_number(price_raw)
        if not price_text:
            raise ValueError(f"第 {offset} 行数据缺少{spec['price'][0]}，无法转换")
        _to_decimal(price_text, offset, spec["price"][0], price_raw)

        quantity_raw = _cell(row, columns, "quantity")
        quantity_text = _clean_number(quantity_raw)
        if not quantity_text:
            raise ValueError(f"第 {offset} 行数据缺少{spec['quantity'][0]}，无法转换")
        quantity_value = _to_decimal(quantity_text, offset, spec["quantity"][0], quantity_raw)
        if quantity_value == quantity_value.to_integral_value():
            quantity_out = str(int(quantity_value))
        else:
            quantity_out = quantity_text

        record = [event_time, precision, symbol, side, quantity_out, price_text]
        if has_fee_columns:
            fee_value = Decimal(0)
            if fee_total_index is not None:
                fee_sources: list[tuple[int, str]] = [
                    (fee_total_index, spec["fee_total"][0])
                ]
            else:
                fee_sources = [
                    (index, spec["fee_parts"][0]) for index in fee_part_indexes
                ]
            for index, label in fee_sources:
                cell = row[index] if index < len(row) else ""
                cleaned = _clean_number(cell)
                if not cleaned:
                    continue
                fee_value += _to_decimal(cleaned, offset, label, cell)
            record.append(_decimal_text(fee_value))
        if execution_id_index is not None:
            record.append(_cell(row, columns, "execution_id"))
        writer.writerow(record)
    return output.getvalue()
