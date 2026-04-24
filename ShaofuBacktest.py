import backtrader as bt
import pandas as pd
import akshare as ak
import math
from datetime import datetime, timedelta # 导入时间处理模块
import os, pdb
from ShaoFuStrategy import ShaoFuStrategy, BC_CONFIG_LIST
from DataLoader import get_data
from BacktestResult import BacktestResult
from ZhuAnStrategy import ZhuAnStrategy

DATA_DIR = "stock_data_5y"

def run_backtest(file_path, symbol, start_date, end_date, config={}, log_detail=True):
    """单只股票的回测逻辑"""
    # print("开始回测" + symbol)
    # 计算预热时间
    # 将字符串转为日期对象
    dt_start = datetime.strptime(start_date, '%Y%m%d')
    # 往前推 165 天（114个交易日约为160天，多留几天 buffer 应对长假）
    dt_preheat = dt_start - timedelta(days=170)
    # 转回字符串格式给 get_data
    preheat_start_str = dt_preheat.strftime('%Y%m%d')

    data = get_data(symbol, preheat_start_str, end_date)
    if data is None or (len(data.p.dataname) < 170):
        # print(symbol + " 数据不足，无法回测")
        return None
    cerebro = bt.Cerebro()
    cerebro.addstrategy(ShaoFuStrategy, **config)
    cerebro.adddata(data)
    cerebro.broker.setcash(1000000.0)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="my_trades")
    
    cerebro_results = cerebro.run()
    strat = cerebro_results[0]

    final_value = cerebro.broker.getvalue()
    profit_pct = (final_value - 1000000.0) / 10000.0 # 收益率 %

    # 获取统计数据
    trades = strat.analyzers.my_trades.get_analysis()
    result = BacktestResult.build(symbol, profit_pct, 
        trades.total.closed if "total" in trades and "closed" in trades.total else 0, 
        trades.won.total if "won" in trades else 0, 
        trades.lost.total if "lost" in trades else 0)

    # print(f'{symbol} 回测完毕，最终账户金额：{final_value:.2f}，收益率：{profit_pct:.2f}%')
    if log_detail:
        result.show()
    return result

def batch_backtest(data_dir="stock_data_5y", target_start="20250101", end_date="20260401", config={}):
    """批量处理文件夹下所有股票"""
    files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    # files = [i for i in files if "002085" in i]
    # files = files[0:100]
    total_cnt = len(files)
    ignore_cnt = 0 # 跳过
    win_cnt = 0 # 盈利
    lose_cnt = 0 # 亏损
    balance_cnt = 0 # 盈亏平衡
    total_trade = 0
    win_trade = 0
    lose_trade = 0
    total_profit_pct = 0
    # print(f"开始全市场回测，共计 {len(files)} 只股票...")
    print("开始日期：" + target_start + "，结束日期：" + end_date)
    print_buy_condition(config)
    
    for i, filename in enumerate(files):
        symbol = filename.replace('.csv', '')
        file_path = os.path.join(data_dir, filename)
        
        try:
            result = run_backtest(file_path, symbol, target_start, end_date, config, log_detail=False)
            if result is not None:
                total_trade += result.total_trade
                win_trade += result.win_trade
                lose_trade += result.lose_trade
                total_profit_pct += result.profit_pct
                profit = result.profit_pct
                if profit > 0:
                    win_cnt += 1
                elif profit < 0:
                    lose_cnt += 1
                else:
                    balance_cnt += 1
            else:
                ignore_cnt += 1
        except Exception as e:
            print(symbol + " backtest is fail", e)
            continue
            
        _pretty_percent(i, len(files))
        # if i % 100 == 0:
        #     print(f"已完成: {i}/{len(files)}")
    print("\r\033[K", end='')
    # print("\r", flush=True)
    
    # 保存结果
    print("\n回测结果：")
    print(f"盈利数量： {win_cnt} 只  亏损数量： {lose_cnt} 只  盈亏平衡数量： {balance_cnt} 只  数据不足数量： {ignore_cnt} 只")
    print(f"交易次数： {total_trade} 次  盈利次数： {win_trade} 次  亏损次数： {lose_trade} 次")
    print(f"单次交易胜率: {win_trade / total_trade * 100 if total_trade != 0 else 0:.2f}%")
    print(f" - 盈利股票占比: {win_cnt / total_cnt * 100:.2f}%")

    print(f" - 平均收益率: {total_profit_pct / total_cnt:.2f}%")
    # print("最高收益股票:", res_df.iloc[0]['code'], f"{res_df.iloc[0]['profit_pct']:.2f}%")
    print('====================================================================================')

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

# def get_buy_condition_str(config={}):
#     """获取保存回测结果的文件名"""
#     rst_file_name = []
#     if config.get("bc_kdj", ShaoFuStrategy.params.bc_kdj):
#         rst_file_name.append("kdj")
#     if config.get("bc_raise_trend", ShaoFuStrategy.params.bc_raise_trend):
#         rst_file_name.append("raise_trend")
#     if config.get("bc_undumping", ShaoFuStrategy.params.bc_undumping):
#         rst_file_name.append("nodump")
#     if config.get("bc_overyellow", ShaoFuStrategy.params.bc_overyellow):
#         rst_file_name.append("over_yellow")
#     return "_".join(rst_file_name)

def _pretty_percent(current, total):
    p = int(current * 100 / total)
    total_len = len(str(total))
    tmp = "[" + "#" * p + "-" * (100-p) + "]" + str(p).rjust(3) + "% (" + str(current).rjust(total_len) + "/" + str(total) + ")"
    print("\r" + tmp, end="")

if __name__ == '__main__':
    # start("002766", start_date="20220101", end_date="20260401")
    # 请确保 data_dir 指向你下载 CSV 的文件夹
    # for config in BC_CONFIG_LIST:
    #     batch_backtest(data_dir="stock_data_5y", target_start="20220101", end_date="20260401", config=config)
    # config = {"bc_kdj": True, "bc_raise_trend": True, "bc_undumping":True, "bc_overyellow": True}
    # batch_backtest(data_dir="stock_data_5y", target_start="20240101", end_date="20260401", config=config)
    config={"log_open": True, "bc_kdj": True}
    run_backtest("stock_data_5y/002085.csv", "002085", start_date="20240101", end_date="20260401", config=config)