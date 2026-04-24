import backtrader as bt
import pandas as pd
import akshare as ak
import math
from datetime import datetime, timedelta # 导入时间处理模块
import os, pdb
from ZhuAnIndicator import ZhuAnIndicator
from ActiveCapIndicator import in_active_cap_raise
import itertools


BC_CONFIG_BASE = {"bc_raise_trend": False, "bc_overyellow": False, 'bc_raise_active_cap': False, 'bc_no_upper_shadow': False, "bc_no_lower_shadow": False}
BC_CONFIG_ACTIVE_RAISE = {"bc_raise_trend": False, "bc_overyellow": False, 'bc_raise_active_cap': True, 'bc_no_upper_shadow': False, "bc_no_lower_shadow": False}
BC_CONFIG_RAISE_TREND = {"bc_raise_trend": True, "bc_overyellow": False, 'bc_raise_active_cap': False, 'bc_no_upper_shadow': False, "bc_no_lower_shadow": False}
BC_CONFIG_RAISE_TREND_ACTIVE_RAISE_NO_SHADOW = {"bc_raise_trend": True, "bc_overyellow": False, 'bc_raise_active_cap': True, 'bc_no_upper_shadow': True, "bc_no_lower_shadow": True}
# BC_CONFIG_RAISE_TREND_OVER_YELLOW = {"bc_raise_trend": True, "bc_overyellow": True}

ZHUAN_BC_CONFIG_LIST = [BC_CONFIG_BASE, BC_CONFIG_ACTIVE_RAISE, BC_CONFIG_RAISE_TREND, BC_CONFIG_RAISE_TREND_ACTIVE_RAISE_NO_SHADOW]

# 定义所有布尔型参数的名称
condition_keys = [
    # 'bc_raise_trend', 
    # 'bc_overyellow', 
    'bc_no_upper_shadow', 
    'bc_no_lower_shadow', 
    # 'bc_raise_active_cap', 
    # 'bc_undumping',
    # 'sc_4_red',
    # 'sc_dumping',
]

# 生成所有 True/False 的组合 (2^6 = 64种)
combinations = list(itertools.product([True, False], repeat=len(condition_keys)))

# 将组合转化为字典列表
ZHUAN_BC_CONFIG_LIST = []
for combo in combinations:
    # dict(zip(...)) 是将 key 和对应的 True/False 值关联起来
    config = dict(zip(condition_keys, combo))
    ZHUAN_BC_CONFIG_LIST.append(config)

print(f"成功生成了 {len(ZHUAN_BC_CONFIG_LIST)} 组策略配置。")

class ZhuAnStrategy(bt.Strategy):
    # 此策略需要开启CheatOnClose模式
    strategy_name = "砖型图"
    cheat_on_close = True
    params = (
        ('percents', 0.98),
        ('log_open', False), # 挂单价格：收盘价上浮 2%
        ('start_date', None),
        ('upper_shadow_ratio', 0.6), # 上影线/实体比例
        ('lower_shadow_ratio', 0.9), # 上影线/实体比例
        ('vol_period', 30),

            # 对单笔交易收益率有提升帮助的是:活跃市值，长上影，长下影
            # 对单笔交易收益率起反向作用的是：上涨趋势，黄线之上，非放量出货
        ('bc_raise_trend', False), # 上升趋势才买
        ('bc_overyellow', False),   # 股价在黄线之上
        ('bc_no_upper_shadow', False), # 不能有长上影线
        ('bc_no_lower_shadow', False),   # 不能有长下影线
        ('bc_raise_active_cap', True),   # 活跃市值多头趋势
        ('bc_undumping', False), # 非放量出货才买

        ('sc_dumping', False), # 放量出货卖出
        ('sc_4_red', False), # 累计4块红砖卖出
    )

    def __init__(self):
        self.stock_name = self.data._name
        self.ind = ZhuAnIndicator(self.data)
        # 2. 白线：EMA(EMA(C,10),10)
        ema_inner = bt.indicators.EMA(self.data.close, period=10)
        self.white_line = bt.indicators.EMA(ema_inner, period=10)
        
        # 3. 黄线：(MA14+MA28+MA57+MA114)/4
        ma14 = bt.indicators.SMA(self.data.close, period=14)
        ma28 = bt.indicators.SMA(self.data.close, period=28)
        ma57 = bt.indicators.SMA(self.data.close, period=57)
        ma114 = bt.indicators.SMA(self.data.close, period=114)
        self.yellow_line = (ma14 + ma28 + ma57 + ma114) / 4
        
        self.order = None
        self.stop_price = None  
        self.red_count = 0
        self.buy_value = 0 # 买入成本
        # 4. 辅助指标：过去30天最大量（不含当天）
        self.max_vol_30 = bt.indicators.Highest(self.data.volume(-1), period=self.params.vol_period)

        self.trade_pnl_list = []  # 新增：记录每一笔交易的百分比收益率

    def next(self):
        # --- 新增：日期拦截逻辑 ---
        if self.params.start_date:
            # 将当前回测到的日期转为 YYYYMMDD 格式的整数或字符串进行对比
            current_date = self.data.datetime.date(0).strftime('%Y%m%d')
            if current_date < self.params.start_date:
                # 在到达目标日期之前，我们依然允许维护计数器（可选）
                # 但绝对不执行买入逻辑
                zhuan_today = self.ind.zhuan[0]
                zhuan_yester = self.ind.zhuan[-1]
                if zhuan_today > zhuan_yester:
                    self.red_count += 1
                else:
                    self.red_count = 0
                return # 拦截，不走下面的买卖判断

        # self.log(f"股票代码：{self.stock_name} 股价:{self.data.close[0]:.2f}, 砖型图: {self.ind.zhuan[0]:.2f}，砖块高度：{self.ind.zhuan[0]-self.ind.zhuan[-1]:.2f}")
        # # --- 1. 手动清理昨日未成交挂单 (A股当日有效原则) ---

        # 获取砖型图数值（0为今天，-1为昨天，-2为前天）
        # 至少需要 3 天数据来判断“昨日绿、今日红”的转折
        if len(self.ind.zhuan) < 3:
            return

        zhuan_today = self.ind.zhuan[0]
        zhuan_yester = self.ind.zhuan[-1]
        zhuan_before = self.ind.zhuan[-2]

        # 计算高度逻辑
        # 红柱高度 = 今天砖值 - 昨天砖值
        # 绿柱高度 = 前天砖值 - 昨天砖值 (昨天是波谷)
        red_h = zhuan_today - zhuan_yester
        green_h = zhuan_before - zhuan_yester

        # 维护连续红砖计数
        if zhuan_today > zhuan_yester:
            self.red_count += 1
        else:
            self.red_count = 0

        # --- 2. 持仓管理（卖出逻辑） ---
        if self.position:
            sell_signal = False
            reason = ""

            # A. 止损逻辑：收盘价破第一根红柱最低价
            if self.data.close[0] < self.stop_price:
                sell_signal = True
                reason = f"触发止损,跌破最低价 {self.stop_price:.2f}"

            # B. 卖点1：连续红砖达到4天（第4天收盘发现，第5天开盘卖）
            if not sell_signal and self.params.sc_4_red and self.red_count >= 4:
                sell_signal = True
                reason = "连续4根红砖"

            if (not sell_signal) and self.params.sc_dumping:
                if (self.data.close[0] < self.data.open[0]) and (self.data.volume[0] > self.max_vol_30[0]):
                    sell_signal = True
                    reason = "放量大阴线"

            # C. 卖点2：出现绿柱（红转绿），即今日砖值小于昨天
            if (not sell_signal) and zhuan_today < zhuan_yester:
                sell_signal = True
                reason = "红砖变绿砖"

            if sell_signal:
                # 使用 Order.Close 实现今日尾盘即刻卖出
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

            # 收盘价在黄线之上
            cond_over_yellow = (self.data.close[0] > self.yellow_line[0]) if self.params.bc_overyellow else True
            if not cond_over_yellow:
                return

            # 活跃市值多头区间
            curr_date_str = self.data.datetime.date(0).strftime('%Y%m%d')
            cond_active_cap_raise = in_active_cap_raise(curr_date_str) if self.params.bc_raise_active_cap else True
            if not cond_active_cap_raise:
                return

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
            if not cond_nodump:
                return

            if self.params.bc_no_upper_shadow or self.params.bc_no_lower_shadow:
                # K线总长度
                body = abs(self.data.high[0] - self.data.low[0])
                # 十字星K线不做
                if body == 0:
                    return
                if self.params.bc_no_upper_shadow:
                    upper_shadow = self.data.high[0] - max(self.data.open[0], self.data.close[0])
                    if upper_shadow > (body * self.params.upper_shadow_ratio):
                        return
                if self.params.bc_no_lower_shadow:
                    lower_shadow = min(self.data.open[0], self.data.close[0]) - self.data.low[0]
                    if lower_shadow > (body * self.params.lower_shadow_ratio):
                        return

            # 1. 今天是红柱 (today > yester)
            # 2. 昨天是绿柱 (yester < before)
            # 3. 红柱高度 >= 绿柱高度的 2/3
            is_red = zhuan_today > zhuan_yester
            is_prev_green = zhuan_yester < zhuan_before
            height_ok = red_h >= (green_h * 2 / 3)

            if is_red and is_prev_green and height_ok:
                # 记录信号日最低价作为后续止损基准
                self.stop_price = self.data.low[0]
                
                # 计算股数 (100股整数倍)
                cash = self.broker.get_cash() * self.params.percents
                size = (cash / self.data.close[0]) // 100 * 100
                
                if size > 0:
                    # 核心：使用今日收盘价下单
                    self.order = self.buy(exectype=bt.Order.Market, size=size)
                    self.log(f"【尾盘买入】砖型触发，以今日收盘价成交: {self.data.close[0]:.2f}")

    def notify_order(self, order):
        # 处理订单状态流转
        if order.status in [order.Completed]:
            if order.isbuy():
                self.buy_value = order.executed.value + order.executed.comm
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
            
                # log 记录（可选）
                self.log(f"【交易结束】持仓天数: {trade.barlen}, 净收益率: {pnl_pct:.2f}%")

    def log(self, txt):
        if not self.params.log_open:
            return
        dt = self.data.datetime.date(0)
        print(f"{dt}, {txt}")

    def stop(self):
        # 回测结束时计算该股票的平均每笔收益
        # pdb.set_trace()
        self.avg_trade_pnl = sum(self.trade_pnl_list) / len(self.trade_pnl_list) if self.trade_pnl_list else 0

    def print_buy_condition(config={}):
        """打印买点条件"""
        print("买入条件：")
        # if config.get("bc_kdj", ShaoFuStrategy.params.bc_kdj):
        #     print(" - KDJ的J < " + str(ShaoFuStrategy.params.j_low))
        if config.get("bc_raise_trend", ZhuAnStrategy.params.bc_raise_trend):
            print(" - 上升趋势")
        # if config.get("bc_undumping", ShaoFuStrategy.params.bc_undumping):
        #     print(" - 非放量出货 时间区间:" + str(ShaoFuStrategy.params.vol_period) + "天")
        if config.get("bc_overyellow", ZhuAnStrategy.params.bc_overyellow):
            print(" - 股价在黄线之上")
        if config.get("bc_no_upper_shadow", ZhuAnStrategy.params.bc_no_upper_shadow):
            print(" - 不能有长上影线")
        if config.get("bc_no_lower_shadow", ZhuAnStrategy.params.bc_no_lower_shadow):
            print(" - 不能有长下影线")
        if config.get("bc_raise_active_cap", ZhuAnStrategy.params.bc_raise_active_cap):
            print(" - 活跃市值多头趋势")
        if config.get("bc_undumping", ZhuAnStrategy.params.bc_undumping):
            print(" - 非放量出货 时间区间:" + str(ZhuAnStrategy.params.vol_period) + "天")

        print("卖出条件：")
        if config.get("sc_dumping", ZhuAnStrategy.params.sc_dumping):
            print(" - 放量出货")
        if config.get("sc_4_red", ZhuAnStrategy.params.sc_4_red):
            print(" - 累计四块红砖")
    