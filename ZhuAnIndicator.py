import backtrader as bt
import math
import pdb

class TdxSMA(bt.Indicator):
    lines = ('sma',)
    params = (('period', 4), ('m', 1),)

    def __init__(self):
        self.addminperiod(1)

    def next(self):
        n = self.params.period
        m = self.params.m

        val = self.data[0] if not math.isnan(self.data[0]) else 0

        if len(self) == 1:
            self.lines.sma[0] = val
        else:
            prev_sma = self.lines.sma[-1]
            if math.isnan(prev_sma): prev_sma = 0
            self.lines.sma[0] = (m * val + (n - m) * prev_sma) / n


class ZhuAnIndicator(bt.Indicator):
    lines = ('zhuan',) # 只需要主线，高度我们在策略里实时算，防止初始化阻塞
    
    def __init__(self):
        # 波动区间计算
        hhv4 = bt.indicators.Highest(self.data.high, period=4)
        llv4 = bt.indicators.Lowest(self.data.low, period=4)
        diff = hhv4 - llv4
        
        # VAR1A 至 VAR6A
        # 加 0.0001 彻底防止除零，使用标准乘除
        var1a = (hhv4 - self.data.close) / (diff + 0.0001) * 100 - 90
        var2a = TdxSMA(var1a, period=4, m=1) + 100
        
        var3a = (self.data.close - llv4) / (diff + 0.0001) * 100
        var4a = TdxSMA(var3a, period=6, m=1)
        var5a = TdxSMA(var4a, period=6, m=1) + 100
        
        var6a = var5a - var2a
        
        # 砖型图核心线
        self.lines.zhuan = bt.If(var6a > 4, var6a - 4, 0)