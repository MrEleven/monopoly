import backtrader as bt
import pandas as pd
import akshare as ak
import math
from datetime import datetime, timedelta # 导入时间处理模块
import os, pdb
from ZhuAnIndicator import ZhuAnIndicator
from ActiveCapIndicator import in_active_cap_raise
import itertools
from SingleNeedleIndicator import SingleNeedleIndicator
from MonopolyHelper import get_limit_price

class SingleNeedleStrategy(bt.Strategy):
    # 此策略需要开启CheatOnClose模式
    strategy_name = "单针下30"
    cheat_on_close = True
    params = (
        ('percents', 0.98),
        ('log_open', False), # 挂单价格：收盘价上浮 2%
        ('start_date', None),
        ('n1', 3),
        ('n2', 21),
        ('short_amount', 30), #  短期资金
        ('long_amount', 85), # 长期资金
        ('chasing_ratio', 0.08), # 追高比例
        ('vol_period', 30),
        ('trend_activation_ratio', 0.2), # 最高估价跟最低估价的差距，用来表示上涨趋势倾斜幅度
        ('leave_buy_price_ratio', 0.01),

        ('bc_nochase', False), #  不追高
        ('bc_raise_trend', False), # 上升趋势才买
        ('bc_trend_alive', False), # 上升趋势教研
        ('bc_raise_active_cap', False),   # 活跃市值多头趋势

        ('sc_quick_leave_buy_price', False), # 快速脱离成本区
    )

    def __init__(self):
        self.stock_name = self.data._name
        self.sn_ind = SingleNeedleIndicator(self.data, n1=self.params.n1, n2=self.params.n2)
        self.hi_n2 = bt.indicators.Highest(self.data.high, period=self.p.n2)
        self.lo_n2 = bt.indicators.Lowest(self.data.low, period=self.p.n2)

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

        
        # --- 2. 状态记录 ---
        self.order = None
        self.hold_days = 0
        self.trade_pnl_list = []  # 记录每一笔交易的百分比收益率
        self.trade_duration_list = [] # 记录每一笔交易的持仓天数
        self.pnl_bucket = {}
        self.trade_date_set = set() # 记录每一笔成交的日期

    def next(self):
        # --- 新增：日期拦截逻辑 ---
        current_date = self.data.datetime.date(0).strftime('%Y%m%d')
        if self.params.start_date:
            # 将当前回测到的日期转为 YYYYMMDD 格式的整数或字符串进行对比
            if current_date < self.params.start_date:
                return

        # 获取当前涨跌停状态
        limit_up_price, limit_down_price = get_limit_price(self.data.close[-1], self.stock_name)

        # --- 2. 持仓管理（卖出逻辑） ---
        if self.position:
            # 如果有卖单没成交，只有是跌停没卖出的情况，继续挂的跌停价卖出
            if self.order and self.order.issell():
                self.cancel(self.order)
                tomorrow_limit_up_price, tomorrow_limit_down_price = get_limit_price(self.data.close[0], self.stock_name)
                sell_limit_price = tomorrow_limit_down_price + 0.01
                self.order = self.sell(exectype=bt.Order.Limit, 
                                       price=sell_limit_price, 
                                       size=self.position.size)
                self.log(f"【限价卖出挂单】原因：卖单没成交，挂单价: {sell_limit_price:.2f} (跌停价+0.01)")
                return

            sell_signal = False
            reason = ""
            self.hold_days += 1

            # if self.hold_days >= 2:  # 第一天买入，第二天收盘卖
            #     sell_signal = True
            #     reason = "次日尾盘卖出"

            # 止损
            if self.data.close[0] < self.stop_price:
                sell_signal = True
                reason = f"触发止损,跌破最低价 {self.stop_price:.2f}"

            # S1出货
            cond_vol = (self.data.close[0] < self.data.open[0]) and (self.data.volume[0] > self.max_vol_30[0])
            # 破黄线
            cond_break_white = (self.data.close[-1] > self.white_line[-1]) and (self.data.close[0] < self.white_line[0])
            # 破白线
            cond_break_yellow = (self.data.close[-1] > self.yellow_line[-1]) and (self.data.close[0] < self.yellow_line[0])
            # 趋势线死叉
            cond_death_cross = (self.white_line[-1] > self.yellow_line[-1]) and (self.white_line[0] < self.yellow_line[0])

            if cond_vol or cond_break_white or cond_break_yellow or cond_death_cross:
                sell_signal = True
                reason = "放量阴线"
                if cond_vol:
                    reason = "放量阴线"
                elif cond_break_white:
                    reason = "跌破白线"
                elif cond_break_yellow:
                    reason = "跌破黄线"
                else:
                    reason = "下跌趋势形成"

            # 不快速脱离成本区就走
            if (not sell_signal) and self.params.sc_quick_leave_buy_price:
                if self.data.close[0] < self.buy_price * (1 + self.params.leave_buy_price_ratio):
                    sell_signal = True
                    reason = "没有快速脱离成本区"

            if sell_signal:
                # 如果是跌停价，则挂第二天的跌停价+1分卖出
                if self.data.close[0] <= limit_down_price:
                    tomorrow_limit_up_price, tomorrow_limit_down_price = get_limit_price(self.data.close[0], self.stock_name)
                    sell_limit_price = tomorrow_limit_down_price + 0.01
                    self.order = self.sell(exectype=bt.Order.Limit, 
                                           price=sell_limit_price, 
                                           size=self.position.size)
                    self.log(f"【限价卖出挂单】原因：{reason}，挂单价: {sell_limit_price:.2f} (跌停价+0.01)")
                    return
                # 今日尾盘即刻卖出
                self.order = self.close(exectype=bt.Order.Market)
                self.log(f"【尾盘卖出】原因：{reason}，参考成交价: {self.data.close[0]:.2f}")
                return

        # --- 3. 选股买入逻辑 ---
        else:
            # 避免重复挂单
            if self.order:
                return

            # 校验上升趋势
            cond_trend = self.white_line[0] > self.yellow_line[0] if self.params.bc_raise_trend else True
            if not cond_trend:
                return

            # # 收盘价在黄线之上
            # cond_over_yellow = (self.data.close[0] > self.yellow_line[0]) if self.params.bc_overyellow else True
            # if not cond_over_yellow:
            #     return

            # 活跃市值多头区间
            curr_date_str = self.data.datetime.date(0).strftime('%Y%m%d')
            cond_active_cap_raise = in_active_cap_raise(curr_date_str) if self.params.bc_raise_active_cap else True
            if not cond_active_cap_raise:
                return

            if self.params.bc_nochase:
                if self.data.close[0] > (self.data.close[-1] * (1 + self.params.chasing_ratio)):
                    return

            # # 校验非放量出货
            # cond_nodump = True
            # if self.params.bc_undumping:
            #     # 获取过去30天（含当天）的成交量列表
            #     # get(ago=0, size=N) 可以获取数据切片
            #     vols = self.data.volume.get(ago=0, size=self.params.vol_period)
            #     if len(vols) >= self.params.vol_period:
            #         max_v = max(vols)
            #         # 找到最大成交量的位置索引（距离今天的偏移）
            #         # vols 是从旧到新排列，所以 index 是从 0 开始
            #         # 我们需要把它映射回 Backtrader 的相对索引
            #         # 比如 vols[29] 是今天，vols[0] 是 29 天前
            #         idx_in_list = vols.index(max_v)
            #         # 计算相对于当前的偏移量：
            #         # 如果 idx_in_list 是 29 (最后一位)，偏移量就是 0 (代表今天)
            #         # 如果 idx_in_list 是 0 (第一位)，偏移量就是 -29 (29天前)
            #         offset = idx_in_list - (self.params.vol_period - 1)
                    
            #         # 判断那天的收盘是否大于开盘 (阳线则 cond3 为 True)
            #         cond_nodump = self.data.close[offset] >= self.data.open[offset]
            # if not cond_nodump:
            #     return

            # if self.params.bc_no_upper_shadow or self.params.bc_no_lower_shadow:
            #     # K线总长度
            #     body = abs(self.data.high[0] - self.data.low[0])
            #     # 十字星K线不做
            #     if body == 0:
            #         return
            #     if self.params.bc_no_upper_shadow:
            #         upper_shadow = self.data.high[0] - max(self.data.open[0], self.data.close[0])
            #         if upper_shadow > (body * self.params.upper_shadow_ratio):
            #             return
            #     if self.params.bc_no_lower_shadow:
            #         lower_shadow = min(self.data.open[0], self.data.close[0]) - self.data.low[0]
            #         if lower_shadow > (body * self.params.lower_shadow_ratio):
            #             return

            # 计算 21 天内的最高价和最低价的价差百分比
            # 只有波幅（箱体高度）大于一定程度（比如 12%），说明这只股票是“活的”
            if self.params.bc_trend_alive:
                volatility_21 = (self.hi_n2[0] - self.lo_n2[0]) / self.lo_n2[0]
                is_trend_alive = volatility_21 > self.params.trend_activation_ratio
                if not is_trend_alive:
                    return

            # --- 基础买入逻辑判定 ---
            # 1. 今天必须是双100
            is_today_double_100 = (self.sn_ind.short_line[0] >= 99.9) and (self.sn_ind.long_line[0] >= 99.9)
            
            if not is_today_double_100:
                return

            # 2. 寻找“开始K线” (距离最近的一次双100，不含今天)
            # 我们向后追溯，限制在最近 15 个交易日内（洗盘时间不宜过长）
            start_idx = None
            for i in range(1, 16):
                if len(self.sn_ind.short_line) > i:
                    if self.sn_ind.short_line[-i] >= 99.9 and self.sn_ind.long_line[-i] >= 99.9:
                        start_idx = i
                        break
            
            if start_idx is None:
                return

            # 3. 检查开始K线与今日K线之间的区间表现 (区间为 index: -start_idx + 1 到 -1)
            # 短期必须到达过30以下
            # 长期不能跌破过85
            short_slice = self.sn_ind.short_line.get(ago=-1, size=start_idx)
            long_slice = self.sn_ind.long_line.get(ago=-1, size=start_idx)
            
            if not short_slice or not long_slice:
                return

            # 长期资金始终处于短期资金之上
            for i in range(len(short_slice)):
                if short_slice[i] > long_slice[i]:
                    return

            has_dipped_30 = min(short_slice) < 30
            stayed_above_85 = min(long_slice) >= 85

            # 4. 执行买入
            if has_dipped_30 and stayed_above_85:
                # 记录信号日最低价作为后续止损基准
                self.stop_price = self.data.close[0] * (0.97)

                cash = self.broker.get_cash() * self.params.percents
                size = (cash / self.data.close[0]) // 100 * 100
                if size > 0:
                    # 涨停价不买
                    if self.data.close[0] >= limit_up_price:
                        return
                    # 核心：使用今日收盘价下单
                    self.order = self.buy(exectype=bt.Order.Market, size=size)
                    self.log(f"【尾盘买入】以今日收盘价成交: {self.data.close[0]:.2f}")
                    self.hold_days = 1

                    # 记录涨幅
                    self.buy_price_change = (self.data.close[0] - self.data.close[-1]) * 100 // self.data.close[-1]
                    self.trade_date_set.add(current_date)

    def notify_order(self, order):
        # 处理订单状态流转
        if order.status in [order.Completed]:
            if order.isbuy():
                self.buy_value = order.executed.value + order.executed.comm
                self.buy_price = order.executed.price
                self.log(f'>>> 实盘买入【{self.stock_name}】: 价格 {order.executed.price:.2f}, 股数 {order.executed.size}, 总成本 {self.buy_value:.2f}')
                self.log(f'设定止损价: {self.stop_price:.2f} | 剩余现金: {self.broker.get_cash():.2f}')
                self.log(" ")
            else:
                sell_received = (order.executed.price * abs(order.executed.size)) - order.executed.comm
                profit = sell_received - self.buy_value
                profit_pct = (profit / self.buy_value) * 100 if self.buy_value != 0 else 0
                self.log(f'<<< 实盘卖出【{self.stock_name}】: 价格 {order.executed.price:.2f}, 盈亏额 {profit:.2f}')
                # self.log(f'回拢后现金: {self.broker.get_cash():.2f}')
                # 卖出成功后清空计数
                self.red_count = 0
                self.stop_price = None
            self.order = None # 订单完成，重置

        elif order.status in [order.Canceled]:
            self.log("--- 订单已撤销 ---")
            self.log("====================================================================================")
            self.order = None

        elif order.status in [order.Margin, order.Rejected, order.Expired]:
            self.log(f"--- 订单失败 (状态: {order.getstatusname()}) ---")
            self.log("====================================================================================")
            self.order = None

    def notify_trade(self, trade):
        # pdb.set_trace()
        if trade.isclosed:
            # 这里的 trade.pnlcomm 是扣除买卖双边佣金后的净利润
            # 精确收益率 = 净利润 / 买入总成本
            if self.buy_value != 0:
                pnl_pct = (trade.pnlcomm / self.buy_value) * 100
                self.trade_pnl_list.append(pnl_pct)
                self.trade_duration_list.append(trade.barlen)
            
                # log 记录（可选）
                self.log(f"【交易结束】回拢后现金: {self.broker.get_cash():.2f}，持仓天数: {trade.barlen}, 净收益率: {pnl_pct:.2f}%")
                self.log("====================================================================================")

                if self.buy_price_change not in self.pnl_bucket:
                    self.pnl_bucket[self.buy_price_change] = []
                self.pnl_bucket[self.buy_price_change].append(pnl_pct)
                self.buy_price_change = None


    def log(self, txt):
        if not self.params.log_open:
            return
        dt = self.data.datetime.date(0)
        print(f"{dt}, {txt}")

    def stop(self):
        # 回测结束时计算该股票的平均每笔收益
        # pdb.set_trace()
        self.avg_trade_pnl = sum(self.trade_pnl_list) / len(self.trade_pnl_list) if self.trade_pnl_list else 0
        self.avg_trade_duration = sum(self.trade_duration_list) / len(self.trade_duration_list) if self.trade_duration_list else 0

    def print_buy_condition(config={}):
        """打印买点条件"""
        print("买入条件：")
        # if config.get("bc_kdj", ShaoFuStrategy.params.bc_kdj):
        #     print(" - KDJ的J < " + str(ShaoFuStrategy.params.j_low))
        if config.get("bc_raise_trend", SingleNeedleStrategy.params.bc_raise_trend):
            print(" - 上升趋势")
        if config.get("bc_trend_alive", SingleNeedleStrategy.params.bc_trend_alive):
            trend_activation_ratio = config.get('trend_activation_ratio', SingleNeedleStrategy.params.trend_activation_ratio)
            print(f" - 上升趋势倾斜校验 幅度落差超过{trend_activation_ratio*100:2f}%")
        # if config.get("bc_no_upper_shadow", SingleNeedleStrategy.params.bc_no_upper_shadow):
        #     print(" - 不能有长上影线")
        # if config.get("bc_no_lower_shadow", SingleNeedleStrategy.params.bc_no_lower_shadow):
        #     print(" - 不能有长下影线")
        # if config.get("bc_raise_active_cap", SingleNeedleStrategy.params.bc_raise_active_cap):
        #     print(" - 活跃市值多头趋势")
        # if config.get("bc_undumping", SingleNeedleStrategy.params.bc_undumping):
        #     vol_period = config.get('vol_period', SingleNeedleStrategy.params.vol_period)
        #     print(" - 非放量出货 时间区间:" + str(vol_period) + "天")
        if config.get("bc_nochase", SingleNeedleStrategy.params.bc_nochase):
            chasing_ratio = config.get('chasing_ratio', SingleNeedleStrategy.params.chasing_ratio)
            print(f" - 不追高 追高涨幅:{chasing_ratio*100:.2f}%")

        # print("卖出条件：")
        # if config.get("sc_dumping", SingleNeedleStrategy.params.sc_dumping):
        #     print(" - 放量出货")
        # if config.get("sc_4_red", SingleNeedleStrategy.params.sc_4_red):
        #     print(" - 累计四块红砖")
        if config.get("sc_quick_leave_buy_price", SingleNeedleStrategy.params.sc_quick_leave_buy_price):
            leave_buy_price_ratio = config.get('leave_buy_price_ratio', SingleNeedleStrategy.params.leave_buy_price_ratio)
            print(f" - 必须快速脱离成本区 最低涨幅:{leave_buy_price_ratio*100:.2f}%")


            



    