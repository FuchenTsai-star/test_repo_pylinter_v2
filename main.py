import math
import os
from typing import Any


def sum_and_trunc(x: float, y: float) -> int:
    """將兩數相加並無條件捨去為整數（向零取整）。"""
    return math.trunc(x + y)


def sum_and_floor(x: float, y: float) -> int:
    """將兩數相加並無條件捨去為整數（向下取整）。"""
    return math.floor(x + y)


def get_working_directory(*_args: Any) -> str:
    """取得目前的工作目錄（若因介面需求須保留不定參數）。"""
    return os.getcwd()
