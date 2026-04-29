import os, sys
os.environ['PYTHONWARNINGS'] = 'ignore'
import backtrader as bt
import pandas as pd
import akshare as ak
import math
from datetime import datetime, timedelta # 导入时间处理模块
import os, pdb
from ShaoFuStrategy import ShaoFuStrategy, SHAOFU_BC_CONFIG_LIST
from DataLoader import get_data, get_all_stock_codes
from BacktestResult import BacktestResult
from ZhuAnStrategy import ZhuAnStrategy, ZHUAN_BC_CONFIG_LIST
from SingleNeedleStrategy import SingleNeedleStrategy
from pathlib import Path

DATA_DIR = "stock_data_5y"

def run_single_stock_backtest(strategy, code, start_date, end_date, config={}, log_detail=True):
    """
        回测单只股票，单个策略
        log_detail:是否打印单只股票回测报告
    """
    config["start_date"] = start_date
    # 计算预热时间
    dt_start = datetime.strptime(start_date, '%Y%m%d')
    # 往前推 165 天（114个交易日约为160天，多留几天 buffer 应对长假）
    dt_preheat = dt_start - timedelta(days=170)
    preheat_start_str = dt_preheat.strftime('%Y%m%d')
    data = get_data(code, preheat_start_str, end_date)
    if data is None or (len(data.p.dataname) < 170):
        # print(code + " 数据不足，无法回测")
        return None

    
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addobserver(bt.observers.Value)
    if strategy.cheat_on_close:
        cerebro.broker.set_coc(True)
    cerebro.addstrategy(strategy, **config)
    cerebro.adddata(data)
    cerebro.broker.setcash(1000000.0)
    cerebro.broker.setcommission(commission=0.0006)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="my_trades")
    
    cerebro_results = cerebro.run()
    # cerebro.plot(style='bar')
    strat = cerebro_results[0]

    # 获取统计数据
    trades = strat.analyzers.my_trades.get_analysis()
    # 平均持仓天数
    avg_duration = getattr(strat, "avg_trade_duration", 0)
    # 平均单笔收益
    precise_avg_pnl = getattr(strat, 'avg_trade_pnl', 0)
    # 每笔交易收益明细
    all_pnl_details = strat.trade_pnl_list
    # 眉笔交易持仓天数明细
    all_durations = strat.trade_duration_list
    # 买入涨幅分层明细
    pnl_bucket = strat.pnl_bucket
    # 交易日期明细(看交易信号按照日期分布)
    trade_date_set = strat.trade_date_set

    result = BacktestResult.build(
        trades.total.closed if "total" in trades and "closed" in trades.total else 0, 
        trades.won.total if "won" in trades else 0, 
        trades.lost.total if "lost" in trades else 0,
        avg_duration = avg_duration,
        precise_avg_pnl = precise_avg_pnl,
        all_pnls = all_pnl_details,
        all_durations = all_durations,
        all_pnls_bucket = pnl_bucket,
        trade_date_set = trade_date_set
    )

    if log_detail:
        result.show()
    return result

def backtest_strategy(strategy, test_name='临时回测', start_date="20250101", end_date="20260401", config={}, save_stock_result=False):
    """
        批量回测不同参数配置下市场中全量股票的结果
    """
    print(f"开始日期：{start_date}，结束日期：{end_date}")
    print(f"策略名称：{strategy.strategy_name}，回测名称: {test_name}")
    print_buy_condition(strategy, config)

    # 全量股票回测中所有交易的收益明细
    global_all_pnls = []
    # 全量股票回测中所有交易的持仓天数明细
    global_durations = []
    # 用于保存股票维度的回测报告
    stock_result_list = []
    # 追涨幅度分层明细
    global_pnl_bucket = {}
    # 交易日期明细（用于统计交易信号发出日期的分布情况）
    global_trade_date_set = set()

    stock_codes = get_all_stock_codes()
    # stock_codes = stock_codes[0:100]

    for i, code in enumerate(stock_codes):
        try:
            result = run_single_stock_backtest(strategy, code, start_date, end_date, config, log_detail=False)
            if not result:
                continue
            global_all_pnls.extend(result.all_pnls)
            global_durations.extend(result.all_durations)
            global_trade_date_set.update(result.trade_date_set)

            item = {"股票代码": code}
            item["交易次数"] = result.total_trade
            item["盈利次数"] = result.win_trade
            item["亏损次数"] = result.lose_trade
            item["单次交易胜率(%)"] = round(result.win_rate, 2)
            item["平均单笔交易收益率(%)"] = round(result.precise_avg_pnl, 4)
            item["平均持仓时间"] = round(result.avg_duration, 2)
            stock_result_list.append(item)

            for k, v in result.all_pnls_bucket.items():
                if k in global_pnl_bucket:
                    global_pnl_bucket[k] = global_pnl_bucket[k] + v
                else:
                    global_pnl_bucket[k] = v
        except Exception as e:
            print(code + " backtest is fail", e)
            continue
        _pretty_percent(i, len(stock_codes))
    print("\r\033[K", end='')

    total_trades_count = len(global_all_pnls)
    avg_pnl = (sum(global_all_pnls) / total_trades_count) if total_trades_count > 0 else 0
    win_trades = len([x for x in global_all_pnls if x > 0])
    loss_trades = len([x for x in global_all_pnls if x < 0])
    avg_duration = sum(global_durations) / total_trades_count if total_trades_count > 0 else 0
    win_rate = (win_trades / total_trades_count) if total_trades_count > 0 else 0

    # 计算期望值 (Expectancy) = (胜率 * 平均盈利) - (败率 * 平均亏损)
    day_profit_pct = avg_pnl / avg_duration if avg_duration > 0 else 0

    print("\n回测结果：")
    print(f"交易次数： {total_trades_count} 次  盈利次数： {win_trades} 次  亏损次数： {loss_trades} 次")
    print(f"参与交易天数:{len(global_trade_date_set)}天")
    print(f"单次交易胜率: {win_rate*100:.2f}%")
    print(f"平均单笔交易收益率: {avg_pnl:.4f}%")
    print(f"平均持仓时间: {avg_duration:.2f} 天")
    print(f"持仓一天收益率: {day_profit_pct:.4f}%")
    print('====================================================================================')

    print("买入涨幅分层统计结果：")
    for k, v in sorted(global_pnl_bucket.items()):
        if not v:
            continue
        avg_bucket_pct = (sum(v) / len(v))
        print(f"涨幅:{k}%，总交易数:{len(v)}，收益率:{avg_bucket_pct:.2f}%")
    if save_stock_result:
        save_stock_report(strategy, test_name, stock_result_list, start_date, end_date, config=config)
    return BacktestResult.build(total_trades_count, win_trades, loss_trades, avg_duration, avg_pnl)

def save_stock_report(strategy, test_name, stock_result_list, start_date, end_date, config):
    file_name = [strategy.strategy_name, test_name, "股票明细", start_date, end_date]
    condtions = [k for k, v in config.items() if (k.startswith("bc_") or k.startswith("sc_")) and v]
    file_name.extend(condtions)
    file_name = "_".join(file_name) + ".csv"
    file_dir = Path("result") / strategy.strategy_name
    file_path = file_dir / file_name
    df_results = pd.DataFrame(stock_result_list)
    df_results.sort_values(by="平均单笔交易收益率(%)", ascending=False)
    df_results.to_csv(str(file_path), index=False, encoding='utf_8_sig')

def print_buy_condition(strategy, config={}):
    """打印参数"""
    strategy.print_buy_condition(config=config)

def _pretty_percent(current, total):
    """打印进度条"""
    p = int(current * 100 / total)
    total_len = len(str(total))
    tmp = "[" + "#" * p + "-" * (100-p) + "]" + str(p).rjust(3) + "% (" + str(current).rjust(total_len) + "/" + str(total) + ")"
    print("\r" + tmp, end="")

def batch_strage_backtest(strategy, test_name='', start_date='20250101', end_date='20260417', config_list=[{}], save_result=False):
    """
        批量回测同一个策略的不同配置，一般用于最佳因子选拔，与比较参数对回测结果的影响
    """
    result_list = []
    for i in range(len(config_list)):
        config = config_list[i]
        result = backtest_strategy(strategy, test_name=test_name, start_date=start_date, end_date=end_date, config=config, save_stock_result=True)
        result_list.append(result)
        print(f"一共回测策略数量：{len(config_list)}，目前已经完成：{i+1}，还剩：{len(config_list)-1-i}")
    if save_result:
        save_summary_report(strategy, test_name, config_list, result_list, start_date, end_date)

def save_summary_report(strategy, test_name='', config_list=[{}], result_list=[], start_date="20250101", end_date="20260417"):
    """
        保存整体测试报告，一般用于保存因子选拔，不同参数对策略结果的影响
    """
    final_result_list = []
    for i in range(len(config_list)):
        config = config_list[i]
        result = result_list[i]
        item = {"策略名称": strategy.strategy_name}
        for k, v in config.items():
            # if k.startswith("bc_") or k.startswith("sc_"):
                item[k] = v
        item["交易次数"] = result.total_trade
        item["盈利次数"] = result.win_trade
        item["亏损次数"] = result.lose_trade
        item["单次交易胜率(%)"] = round(result.win_rate, 2)
        item["平均单笔交易收益率(%)"] = round(result.precise_avg_pnl, 4)
        item["平均持仓时间"] = round(result.avg_duration, 2)
        day_profit_pct = result.precise_avg_pnl / result.avg_duration if result.avg_duration > 0 else 0
        item["持仓一天收益率(%)"] = round(day_profit_pct, 2)
        final_result_list.append(item)

    df_results = pd.DataFrame(final_result_list)
    df_results.sort_values(by="平均单笔交易收益率(%)", ascending=False)
    file_dir = Path("result") / strategy.strategy_name
    file_dir.mkdir(parents=True, exist_ok=True)

    file_name = "_".join([test_name, start_date, end_date]) + ".csv"
    file_path = file_dir / file_name
    df_results.to_csv(str(file_path), index=False, encoding='utf_8_sig')

if __name__ == '__main__':
    # batch_strage_backtest(SingleNeedleStrategy, test_name='不追高_涨幅因子选拔', start_date="20250101", end_date="20260101", config_list=ZHUAN_BC_CONFIG_LIST, save_result=True)
    # batch_strage_backtest(SingleNeedleStrategy, test_name='不追高_涨幅因子选拔', start_date="20240101", end_date="20250101", config_list=ZHUAN_BC_CONFIG_LIST, save_result=True)
    # batch_strage_backtest(SingleNeedleStrategy, test_name='不追高_涨幅因子选拔', start_date="20230101", end_date="20240101", config_list=ZHUAN_BC_CONFIG_LIST, save_result=True)
    # batch_strage_backtest(SingleNeedleStrategy, test_name='不追高_涨幅因子选拔', start_date="20220101", end_date="20230101", config_list=ZHUAN_BC_CONFIG_LIST, save_result=True)
    # # config_1 = {"bc_raise_trend": True, "bc_overyellow": True, 'bc_raise_active_cap': False, 'bc_no_upper_shadow': True, "bc_no_lower_shadow": False, 'sc_4_red': True, 'sc_dumping': False, 'sc_quick_leave_buy_price': True}
    config_1 = {
        # "log_open": True,
        "bc_raise_trend": True, 
        "bc_overyellow": True, 
        'bc_no_upper_shadow': True, 
        "bc_no_lower_shadow": False,
        "bc_undumping": False,
        "bc_raise_active_cap": False,
        "bc_nochase": False,
        "sc_quick_leave_buy_price": False,
        "sc_dumping": True,
        "sc_4_red": True
    }
    config_2 = {
        # "log_open": True,
        "bc_raise_trend": True, 
        "bc_overyellow": True, 
        'bc_no_upper_shadow': True, 
        "bc_no_lower_shadow": False,
        "bc_undumping": False,
        "bc_raise_active_cap": False,
        "bc_nochase": False,
        "sc_quick_leave_buy_price": True,
        "sc_dumping": True,
        "sc_4_red": True
    }
    batch_strage_backtest(ZhuAnStrategy, test_name='不追高', start_date="20250101", end_date="20260417", config_list=[config_1], save_result=True)
    # start("002766", start_date="20220101", end_date="20260401")
    # 请确保 data_dir 指向你下载 CSV 的文件夹
    # for config in ZHUAN_BC_CONFIG_LIST:
    #     batch_backtest(strategy=ZhuAnStrategy, data_dir="stock_data_5y", start_date="20250101", end_date="20260417", config=config)
    # config = {"bc_raise_trend": False,"bc_undumping": True, "bc_overyellow": False, 'bc_raise_active_cap': True, 'bc_no_upper_shadow': True, "bc_no_lower_shadow": True}
    # batch_backtest(strategy=ZhuAnStrategy, data_dir="stock_data_5y", start_date="20220101", end_date="20250101", config=config)
    # config={"log_open": True, "bc_raise_active_cap": True, 'bc_no_upper_shadow': True, 'bc_no_lower_shadow': True}
    # config_2["log_open"] = True
    # run_single_stock_backtest(ZhuAnStrategy, "000506", start_date="20250101", end_date="20260417", config=config_2)
    # run_single_stock_backtest(ZhuAnStrategy, "920642", start_date="20250101", end_date="20260417", config=config_2)
