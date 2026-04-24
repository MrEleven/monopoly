import backtrader as bt
import pandas as pd
import akshare as ak
import math
from datetime import datetime, timedelta # 导入时间处理模块
import os, pdb
from TdxKDJ import TdxKDJ

BC_CONFIG_KDJ = {"bc_kdj": True, "bc_raise_trend": False, "bc_undumping":False, "bc_overyellow": False}
BC_CONFIG_KDJ_RAISE_TREND = {"bc_kdj": True, "bc_raise_trend": True, "bc_undumping":False, "bc_overyellow": False}
BC_CONFIG_KDJ_NODUMP = {"bc_kdj": True, "bc_raise_trend": False, "bc_undumping":True, "bc_overyellow": False}
BC_CONFIG_KDJ_RAISE_TREND_NODUMP = {"bc_kdj": True, "bc_raise_trend": True, "bc_undumping":True, "bc_overyellow": False}
BC_CONFIG_KDJ_RAISE_TREND_NODUMP_OVER_YELLOW = {"bc_kdj": True, "bc_raise_trend": True, "bc_undumping":True, "bc_overyellow": True}

SHAOFU_BC_CONFIG_LIST = [BC_CONFIG_KDJ, BC_CONFIG_KDJ_RAISE_TREND, 
    BC_CONFIG_KDJ_NODUMP, BC_CONFIG_KDJ_RAISE_TREND_NODUMP, 
    BC_CONFIG_KDJ_RAISE_TREND_NODUMP_OVER_YELLOW]

class ShaoFuStrategy(bt.Strategy):
    strategy_name = "少妇战法B1买点"
    params = (
        ('j_low', 13),
        ('vol_period', 30),
        ('stop_loss_pct', 0.01), # 止损 1%
        ('percents', 0.99),     # 梭哈比例 99%
        ('log_open', False), # 股价在黄线之上才买

        ('bc_raise_trend', False), # 上升趋势才买
        ('bc_kdj', True), # KDJ的J小于阈值才买
        ('bc_undumping', True), # 非放量出货才买
        ('bc_overyellow', False), # 股价在黄线之上才买
    )

    def __init__(self):
        # 获取当前数据源的名称
        self.stock_name = self.data._name
        
        # 1. KDJ (9, 3, 3)
        # 使用自定义的 TdxKDJ
        self.kdj = TdxKDJ(self.data)
        self.j_line = self.kdj.j
        
        # 2. 白线：EMA(EMA(C,10),10)
        ema_inner = bt.indicators.EMA(self.data.close, period=10)
        self.white_line = bt.indicators.EMA(ema_inner, period=10)
        
        # 3. 黄线：(MA14+MA28+MA57+MA114)/4
        ma14 = bt.indicators.SMA(self.data.close, period=14)
        ma28 = bt.indicators.SMA(self.data.close, period=28)
        ma57 = bt.indicators.SMA(self.data.close, period=57)
        ma114 = bt.indicators.SMA(self.data.close, period=114)
        self.yellow_line = (ma14 + ma28 + ma57 + ma114) / 4

        # 4. 辅助指标：过去30天最大量（不含当天）
        self.max_vol_30 = bt.indicators.Highest(self.data.volume(-1), period=self.params.vol_period)

        # 变量记录
        self.order = None
        self.stop_price = None # 动态止损价
        self.buy_value = 0     # 记录买入时的总市值

        self.log("少妇战法 初始化买入条件：")
        if self.params.bc_kdj:
            self.log(" - KDJ的J < " + str(ShaoFuStrategy.params.j_low))
        if self.params.bc_raise_trend:
            self.log(" - 上升趋势")
        if self.params.bc_undumping:
            self.log(" - 非放量出货 时间区间:" + str(ShaoFuStrategy.params.vol_period) + "天")
        if self.params.bc_overyellow:
            self.log(" - 股价在黄线之上")

    def next(self):
        if self.order: # 检查是否有挂单
            self.cancel(self.order)
            self.order = None

        # --- 未持仓：寻找买点 ---
        if not self.position:
            buy_condition = True
            # 校验kdj
            cond_kdj = (self.j_line[0] < self.params.j_low) if self.params.bc_kdj else True
            # 校验上升趋势
            cond_trend = self.white_line[0] > self.yellow_line[0] if self.params.bc_raise_trend else True
            # 校验非放量出货
            cond_nodump = True
            if self.params.bc_undumping:
                # 获取过去30天（含当天）的成交量列表
                # get(ago=0, size=N) 可以获取数据切片
                vols = self.data.volume.get(ago=0, size=self.params.vol_period)
                if len(vols) >= self.params.vol_period:
                    max_v = max(vols)
                    # 找到最大成交量的位置索引（距离今天的偏移）
                    # vols 是从旧到新排列，所以 index 是从 0 开始
                    # 我们需要把它映射回 Backtrader 的相对索引
                    # 比如 vols[29] 是今天，vols[0] 是 29 天前
                    idx_in_list = vols.index(max_v)
                    # 计算相对于当前的偏移量：
                    # 如果 idx_in_list 是 29 (最后一位)，偏移量就是 0 (代表今天)
                    # 如果 idx_in_list 是 0 (第一位)，偏移量就是 -29 (29天前)
                    offset = idx_in_list - (self.params.vol_period - 1)
                    
                    # 判断那天的收盘是否大于开盘 (阳线则 cond3 为 True)
                    cond_nodump = self.data.close[offset] >= self.data.open[offset]
            # 收盘价在黄线之上
            cond_over_yellow = (self.data.close[0] > self.yellow_line[0]) if self.params.bc_overyellow else True

            if cond_kdj and cond_trend and cond_nodump and cond_over_yellow:
                # 1. 计算挂单价格（今日收盘价上浮 2%）
                limit_price = self.data.close[0] * 1.02
                
                # 2. 【核心逻辑】：手动计算梭哈股数
                # 可用资金 = 当前总现金 * 98%
                available_cash = self.broker.get_cash() * self.params.percents
                
                # 股数 = 可用资金 / 挂单价 -> 向下取整到 100 的倍数
                size = (available_cash / limit_price) // 100 * 100
                
                if size > 0:
                    # 3. 指定 size 发出限价单
                    self.order = self.buy(exectype=bt.Order.Limit, price=limit_price, size=size)
                    self.log(f'【{self.stock_name}】买入信号: J值 {self.j_line[0]:.2f}，挂单价 {limit_price:.2f}，计算梭哈股数 {size} | 当前余额: {self.broker.get_cash():.2f}')

        # --- 已持仓：寻找卖点 ---
        else:
            if self.stop_price and self.data.close[0] < self.stop_price:
                self.order = self.close(exectype=bt.Order.Market)
                self.log(f'【{self.stock_name}】触发止损: 当前价 {self.data.close[0]:.2f} < 止损价 {self.stop_price:.2f} | 当前余额: {self.broker.get_cash():.2f}')
                return

            cond_vol = (self.data.close[0] < self.data.open[0]) and (self.data.volume[0] > self.max_vol_30[0])
            cond_break_white = (self.data.close[-1] > self.white_line[-1]) and (self.data.close[0] < self.white_line[0])
            cond_break_yellow = (self.data.close[-1] > self.yellow_line[-1]) and (self.data.close[0] < self.yellow_line[0])
            cond_death_cross = (self.white_line[-1] > self.yellow_line[-1]) and (self.white_line[0] < self.yellow_line[0])

            if cond_vol or cond_break_white or cond_break_yellow or cond_death_cross:
                self.order = self.close(exectype=bt.Order.Market)
                reason = "放量阴线"
                if cond_vol:
                    reason = "放量阴线"
                elif cond_break_white:
                    reason = "跌破白线"
                elif cond_break_yellow:
                    reason = "跌破黄线"
                else:
                    reason = "下跌趋势形成"
                self.log(f'【{self.stock_name}】卖出信号: 原因 {reason}，准备次日全仓清仓 | 当前余额: {self.broker.get_cash():.2f}')

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                self.buy_value = order.executed.value + order.executed.comm
                self.stop_price = self.data.low[0] * (1 - self.params.stop_loss_pct)
                self.log(f'>>> 实盘买入【{self.stock_name}】: 价格 {order.executed.price:.2f}, 股数 {order.executed.size}, 总成本 {self.buy_value:.2f}')
                self.log(f'设定止损价: {self.stop_price:.2f} | 剩余现金: {self.broker.get_cash():.2f}')
                self.log(" ")
            else:
                sell_received = (order.executed.price * abs(order.executed.size)) - order.executed.comm
                profit = sell_received - self.buy_value
                profit_pct = (profit / self.buy_value) * 100 if self.buy_value != 0 else 0
                self.log(f'<<< 实盘卖出【{self.stock_name}】: 价格 {order.executed.price:.2f}, 盈亏额 {profit:.2f}, 收益率 {profit_pct:.2f}%')
                self.log(f'回拢后现金: {self.broker.get_cash():.2f}')
                self.log("====================================================================================")
                self.stop_price = None
                self.buy_value = 0
            self.order = None 
        elif order.status in [order.Margin, order.Rejected]:
            self.log(f'【{self.stock_name}】订单失败: 资金不足或被拒绝 | 当前余额: {self.broker.get_cash():.2f}')
            self.log("====================================================================================")
            self.order = None
        elif order.status in [order.Expired, order.Canceled]:
            self.log(f'【{self.stock_name}】订单失败：订单取消 | 当前余额: {self.broker.get_cash():.2f}')
            self.log("====================================================================================")
            self.order = None

    def log(self, txt):
        if not self.params.log_open:
            return
        dt = self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()}, {txt}')

    def print_buy_condition(config={}):
        """打印买点条件"""
        print("买入条件：")
        if config.get("bc_kdj", ShaoFuStrategy.params.bc_kdj):
            print(" - KDJ的J < " + str(ShaoFuStrategy.params.j_low))
        if config.get("bc_raise_trend", ShaoFuStrategy.params.bc_raise_trend):
            print(" - 上升趋势")
        if config.get("bc_undumping", ShaoFuStrategy.params.bc_undumping):
            print(" - 非放量出货 时间区间:" + str(ShaoFuStrategy.params.vol_period) + "天")
        if config.get("bc_overyellow", ShaoFuStrategy.params.bc_overyellow):
            print(" - 股价在黄线之上")