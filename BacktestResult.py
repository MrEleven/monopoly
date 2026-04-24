import backtrader as bt
import pandas as pd
import akshare as ak
import math
from datetime import datetime, timedelta # 导入时间处理模块
import os, pdb

class BacktestResult(object):
    """单只股票回测结果"""  
    total_trade = 0
    win_trade = 0
    lose_trade = 0
    win_rate = 0
    # 平均持仓天数
    avg_duration = 0
    # 当笔交易平均收益率
    precise_avg_pnl = 0
    # 所有交易的收益明细
    all_pnls = []

    def __init__(self):
        self.symbol = ""
        self.total_trade = 0
        self.win_rate = 0
        self.lose_trade = 0
        self.win_rate = 0

    def build(total_trade, win_trade, lose_trade, avg_duration, precise_avg_pnl, all_pnls=[]):
        result = BacktestResult()
        result.total_trade = total_trade
        result.win_trade = win_trade
        result.lose_trade = lose_trade
        result.win_rate = (win_trade / total_trade) * 100 if total_trade > 0 else 0
        result.avg_duration = avg_duration
        result.precise_avg_pnl = precise_avg_pnl
        result.all_pnls = all_pnls
        return result

    def show(self):
        print(f"单笔交易胜率: {self.win_rate:.2f}%")
        print(f"总交易次数: {self.total_trade}")
        print(f"盈利次数: {self.win_trade}")
        print(f"亏损次数: {self.lose_trade}")
        print(f"单笔交易收益率: {self.precise_avg_pnl:.2f}%")
        # pdb.set_trace()
