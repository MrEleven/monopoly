import backtrader as bt
import pandas as pd
import akshare as ak
import math
from datetime import datetime, timedelta # 导入时间处理模块
import os, pdb

# 自定义通达信风格的 KDJ 指标
class TdxKDJ(bt.Indicator):
    lines = ('k', 'd', 'j')
    params = (('period', 9), ('m1', 3), ('m2', 3))

    def __init__(self):
        # 1. 计算 RSV
        # Highest 和 Lowest 会自动处理 minperiod，确保 9 天后才开始计算
        hh = bt.indicators.Highest(self.data.high, period=self.p.period)
        ll = bt.indicators.Lowest(self.data.low, period=self.p.period)
        self.rsv = 100 * (self.data.close - ll) / (hh - ll)

    def next(self):
        # 初始值处理：当 RSV 刚计算出来时（即第 9 天）
        # len(self) 代表当前是第几根 K 线
        if len(self) <= self.p.period:
            self.lines.k[0] = 50.0
            self.lines.d[0] = 50.0
        else:
            # 严格对齐通达信公式：Y = (1*X + 2*Y') / 3
            # 注意：Backtrader 的索引 [-1] 指向的是上一根 K 线
            self.lines.k[0] = (1 * self.rsv[0] + 2 * self.lines.k[-1]) / 3
            self.lines.d[0] = (1 * self.lines.k[0] + 2 * self.lines.d[-1]) / 3
        
        # 计算 J 值
        self.lines.j[0] = 3 * self.lines.k[0] - 2 * self.lines.d[0]