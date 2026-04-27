import backtrader as bt
import pandas as pd
import akshare as ak
import math
from datetime import datetime, timedelta # 导入时间处理模块
import os, pdb
from ShaoFuStrategy import ShaoFuStrategy, SHAOFU_BC_CONFIG_LIST
from DataLoader import get_data
from BacktestResult import BacktestResult
from ZhuAnStrategy import ZhuAnStrategy, ZHUAN_BC_CONFIG_LIST

DATA_DIR = "stock_data_5y"

def run_backtest(strategy, file_path, symbol, start_date, end_date, config_list=[{}], log_detail=True):
    """单只股票的回测逻辑"""
    for config in config_list:
        config["start_date"] = start_date
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
        return []

    result_list = []
    for config in config_list:
        cerebro = bt.Cerebro(stdstats=False)

        # 图表配置
        # data.plotinfo.plot = False
        cerebro.addobserver(bt.observers.Value)
        # if ZhuAnStrategy.cheat_on_close:
        if strategy.cheat_on_close:
            cerebro.broker.set_coc(True)
        # cerebro.broker.set_checksubmit(False)
        cerebro.addstrategy(strategy, **config)
        cerebro.adddata(data)
        cerebro.broker.setcash(1000000.0)
        cerebro.broker.setcommission(commission=0.0006)
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="my_trades")
        
        cerebro_results = cerebro.run()
        # cerebro.plot(style='bar')
        strat = cerebro_results[0]

        # pdb.set_trace()

        final_value = cerebro.broker.getvalue()

        # 获取统计数据
        trades = strat.analyzers.my_trades.get_analysis()
        # 提取核心精确指标
        avg_duration = getattr(strat, "avg_trade_duration", 0)
        # 获取策略 stop() 时计算的平均单笔收益
        precise_avg_pnl = getattr(strat, 'avg_trade_pnl', 0)
        # 也可以把所有明细带出去做大数据分析
        all_pnl_details = strat.trade_pnl_list
        all_durations = strat.trade_duration_list
        pnl_bucket = strat.pnl_bucket

        result = BacktestResult.build(
            trades.total.closed if "total" in trades and "closed" in trades.total else 0, 
            trades.won.total if "won" in trades else 0, 
            trades.lost.total if "lost" in trades else 0,
            avg_duration = avg_duration,
            precise_avg_pnl = precise_avg_pnl,
            all_pnls = all_pnl_details,
            all_durations = all_durations,
            all_pnls_bucket = pnl_bucket
        )

        if log_detail:
            result.show()
        result_list.append(result)
    return result_list

def batch_backtest(strategy, data_dir="stock_data_5y", start_date="20250101", end_date="20260401", config_list=[{}], save_result=False):
    """批量处理文件夹下所有股票"""
    files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    # files = [i for i in files if "002085" in i]
    # files = files[0:100]
    print("开始日期：" + start_date + "，结束日期：" + end_date)
    print("策略名称：" + strategy.strategy_name)
    print("一共回测策略数量：" + str(len(config_list)))
    # print_buy_condition(strategy, config)

    final_all_pnls_list = []
    final_durations_list = []
    final_stock_result_list = []
    final_result_list = []
    final_pnl_bucket_list = []
    for i in range(len(config_list)):
        final_all_pnls_list.append([])
        final_durations_list.append([])
        final_stock_result_list.append([])
        final_pnl_bucket_list.append({})

    for j, filename in enumerate(files):
        symbol = filename.replace('.csv', '')
        file_path = os.path.join(data_dir, filename)
        
        try:
            symbol_result_list = run_backtest(strategy, file_path, symbol, start_date, end_date, config_list, log_detail=False)
            if not symbol_result_list:
                continue
            for i in range(len(config_list)):
                global_all_pnls = final_all_pnls_list[i]
                global_durations = final_durations_list[i]
                # 记录单只股票回测明细
                stock_result_list = final_stock_result_list[i]
                pnl_bucket = final_pnl_bucket_list[i]

                result = symbol_result_list[i]
                if result is not None:
                    global_all_pnls.extend(result.all_pnls)
                    global_durations.extend(result.all_durations)

                    item = {"股票代码": symbol}
                    item["交易次数"] = result.total_trade
                    item["盈利次数"] = result.win_trade
                    item["亏损次数"] = result.lose_trade
                    item["单次交易胜率(%)"] = round(result.win_rate, 2)
                    item["平均单笔交易收益率(%)"] = round(result.precise_avg_pnl, 4)
                    item["平均持仓时间"] = round(result.avg_duration, 2)
                    stock_result_list.append(item)

                    for k, v in result.all_pnls_bucket.items():
                        if k in pnl_bucket:
                            pnl_bucket[k] = pnl_bucket[k] + v
                        else:
                            pnl_bucket[k] = v
        except Exception as e:
            print(symbol + " backtest is fail", e)
            continue
            
        _pretty_percent(j, len(files))
    print("\r\033[K", end='')

    for i in range(len(config_list)):
        config = config_list[i]
        print_buy_condition(strategy, config)

        global_all_pnls = final_all_pnls_list[i]
        global_durations = final_durations_list[i]
        # 记录单只股票回测明细
        stock_result_list = final_stock_result_list[i]

        total_trades_count = len(global_all_pnls)
        avg_pnl = (sum(global_all_pnls) / total_trades_count) if total_trades_count > 0 else 0
        win_trades = len([x for x in global_all_pnls if x > 0])
        avg_duration = sum(global_durations) / len(global_durations) if len(global_durations) > 0 else 0
        win_rate = (win_trades/total_trades_count) if total_trades_count > 0 else 0

        # 计算期望值 (Expectancy) = (胜率 * 平均盈利) - (败率 * 平均亏损)
        win_pnl = [x for x in global_all_pnls if x > 0]
        loss_pnl = [x for x in global_all_pnls if x < 0]
        balance_pnl = [x for x in global_all_pnls if x == 0]
        day_profit_pct = avg_pnl/avg_duration if avg_duration > 0 else 0



        print("\n回测结果：")
        print(f"交易次数： {total_trades_count} 次  盈利次数： {len(win_pnl)} 次  亏损次数： {len(loss_pnl)} 次")
        print(f"单次交易胜率: {win_rate*100:.2f}%")
        print(f"平均单笔交易收益率: {avg_pnl:.4f}%")
        print(f"平均持仓时间: {avg_duration:.2f} 天")
        print(f"持仓一天收益率: {day_profit_pct:.4f}%")
        print('====================================================================================')

        # print("买入涨幅分层统计结果：")
        # bucket = final_pnl_bucket_list[i]
        # for k, v in sorted(bucket.items()):
        #     if not v:
        #         continue
        #     avg_bucket_pct = (sum(v) / len(v))
        #     print(f"涨幅:{k}%，总交易数:{len(v)}，收益率:{avg_bucket_pct:.2f}%")

        if save_result:
            file_name = [strategy.strategy_name, start_date, end_date]
            condtions = [k for k, v in config.items() if (k.startswith("bc_") or k.startswith("sc_")) and v]
            file_name.extend(condtions)
            file_name = "_".join(file_name) + ".csv"
            df_results = pd.DataFrame(stock_result_list)
            df_results.sort_values(by="平均单笔交易收益率(%)", ascending=False)
            # file_name = "_".join([strategy.strategy_name, start_date, end_date])
            df_results.to_csv("result\\" + file_name, index=False, encoding='utf_8_sig')
        final_result_list.append(BacktestResult.build(total_trades_count, len(win_pnl), len(loss_pnl), avg_duration, avg_pnl))
    return final_result_list

def print_buy_condition(strategy, config={}):
    strategy.print_buy_condition(config=config)
    

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

def backtest_all_config(strategy, test_name='', config_list=[{}], start_date="20250101", end_date="20260417"):
    result_list = batch_backtest(strategy=ZhuAnStrategy, data_dir="stock_data_5y", start_date=start_date, end_date=end_date, config_list=config_list, save_result=False)
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
    file_name = [test_name, start_date, end_date]
    file_name = "result\\" + strategy.strategy_name+"\\" + "_".join(file_name) + ".csv"
    df_results.to_csv(file_name, index=False, encoding='utf_8_sig')

if __name__ == '__main__':
    backtest_all_config(ZhuAnStrategy, test_name='不追高_涨幅因子选拔', start_date="20250101", end_date="20260101", config_list=ZHUAN_BC_CONFIG_LIST)
    backtest_all_config(ZhuAnStrategy, test_name='不追高_涨幅因子选拔', start_date="20240101", end_date="20250101", config_list=ZHUAN_BC_CONFIG_LIST)
    backtest_all_config(ZhuAnStrategy, test_name='不追高_涨幅因子选拔', start_date="20230101", end_date="20240101", config_list=ZHUAN_BC_CONFIG_LIST)
    backtest_all_config(ZhuAnStrategy, test_name='不追高_涨幅因子选拔', start_date="20220101", end_date="20230101", config_list=ZHUAN_BC_CONFIG_LIST)
    # config_1 = {"bc_raise_trend": True, "bc_overyellow": True, 'bc_raise_active_cap': False, 'bc_no_upper_shadow': True, "bc_no_lower_shadow": False, 'sc_4_red': True, 'sc_dumping': False, 'sc_quick_leave_buy_price': True}
    # config_2 = {"bc_raise_trend": True, "bc_overyellow": True, 'bc_raise_active_cap': False, 'bc_no_upper_shadow': False, "bc_no_lower_shadow": False, 'sc_4_red': False, 'sc_dumping': True, "sc_quick_leave_buy_price": True}
    # backtest_all_config(ZhuAnStrategy, start_date="20250101", end_date="20260417", config_list=[config_2])
    # start("002766", start_date="20220101", end_date="20260401")
    # 请确保 data_dir 指向你下载 CSV 的文件夹
    # for config in ZHUAN_BC_CONFIG_LIST:
    #     batch_backtest(strategy=ZhuAnStrategy, data_dir="stock_data_5y", start_date="20250101", end_date="20260417", config=config)
    # config = {"bc_raise_trend": False,"bc_undumping": True, "bc_overyellow": False, 'bc_raise_active_cap': True, 'bc_no_upper_shadow': True, "bc_no_lower_shadow": True}
    # batch_backtest(strategy=ZhuAnStrategy, data_dir="stock_data_5y", start_date="20220101", end_date="20250101", config=config)
    # config={"log_open": True, "bc_raise_active_cap": True, 'bc_no_upper_shadow': True, 'bc_no_lower_shadow': True}
    # config_2["log_open"] = True
    # run_backtest(ZhuAnStrategy, "stock_data_5y/600744.csv", "600744", start_date="20250101", end_date="20260417", config_list=[config_2])
