import backtrader as bt
import math
import pdb

class SingleNeedleIndicator(bt.Indicator):
    lines = ('short_line', 'long_line')
    params = (('n1', 3), ('n2', 21),)

    def __init__(self):
        # 预先定义好最高最低价格的 Lines
        self.hi_n1 = bt.indicators.Highest(self.data.close, period=self.p.n1)
        self.lo_n1 = bt.indicators.Lowest(self.data.low, period=self.p.n1)
        
        self.hi_n2 = bt.indicators.Highest(self.data.close, period=self.p.n2)
        self.lo_n2 = bt.indicators.Lowest(self.data.low, period=self.p.n2)

    def next(self):
        # --- 计算短期线 ---
        diff_n1 = self.hi_n1[0] - self.lo_n1[0]
        if diff_n1 > 0:
            self.lines.short_line[0] = 100 * (self.data.close[0] - self.lo_n1[0]) / diff_n1
        else:
            self.lines.short_line[0] = 0.0

        # --- 计算长期线 ---
        diff_n2 = self.hi_n2[0] - self.lo_n2[0]
        if diff_n2 > 0:
            self.lines.long_line[0] = 100 * (self.data.close[0] - self.lo_n2[0]) / diff_n2
        else:
            self.lines.long_line[0] = 0.0