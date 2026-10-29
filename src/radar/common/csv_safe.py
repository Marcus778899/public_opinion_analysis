"""CSV 公式注入防護：以公式字元開頭的字串前置 `'`，Excel 才不會執行。"""

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: str) -> str:
    return "'" + value if value.startswith(FORMULA_PREFIXES) else value
