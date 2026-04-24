import backtrader as bt
import pandas as pd
import akshare as ak
import math
from datetime import datetime, timedelta # 导入时间处理模块
import os, pdb

active_cap_raise_range = [
    (20201223, 20210125),
    (20210218, 20210303),
    (20210419, 20210615),
    (20210709, 20210816),
    (20210824, 20210915),
    (20211210, 20220124),
    (20220225, 20220311),
    (20220316, 20220324),
    (20220427, 20220505),
    (20220511, 20220523),
    (20220606, 20220722),
    (20221013, 20221216),
    (20230105, 20230511),
    (20230616, 20230620),
    (20230731, 20230810),
    (20230828, 20230919),
    (20231025, 20231219),
    (20231228, 20240116),
    (20240124, 20240129),
    (20240206, 20240322),
    (20240417, 20240514),
    (20240711, 20240722),
    (20240731, 20240809),
    (20240830, 20241010),
    (20241018, 20241113),
    (20250114, 20250124),
    (20250206, 20250227),
    (20250408, 20250415),
    (20250506, 20250514),
    (20250625, 20250903),
    (20251029, 20251120),
    (20260105, 20260130),
    (20260408, 21000101)
]

def in_active_cap_raise(date_str, cheat_on_close=False):
    if cheat_on_close:
        return _in_active_cap_raise_cheat(date_str)
    d = int(date_str)
    for i in active_cap_raise_range:
        if d >= i[0]:
            if d <= i[1]:
                return True
            else:
                continue
        # 当区间起始时间超过指定日期，后续永远无法匹配直接返回False
        else:
            return False

def _in_active_cap_raise_cheat(date_str):
    """开启cheat_on_close之后,交易会以尾盘收盘价成交，活跃市值第一天的尾盘无法感知活跃市值已经进入多头，第二天才感知"""
    d = int(date_str)
    for i in active_cap_raise_range:
        if d > i[0]:
            if d <= i[1]:
                return True
            else:
                continue
        # 当区间起始时间超过指定日期，后续永远无法匹配直接返回False
        else:
            return False