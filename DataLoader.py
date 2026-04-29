import backtrader as bt
import pandas as pd
import akshare as ak
import math
from datetime import datetime, timedelta # 导入时间处理模块
import os, pdb

DATA_DIR = "stock_data_5y"

def get_data(symbol="600519", start_date="20240101", end_date="20251231"):
    """获取股票指定日期的历史数据"""
    return _get_data_native(symbol=symbol, start_date=start_date, end_date=end_date)

def _get_data(symbol="600519", start_date="20240101", end_date="20251231"):
    try:
        stock_info = ak.stock_info_a_code_name()
        name = stock_info[stock_info['code'] == symbol]['name'].values[0]
    except:
        name = symbol 
    df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
    df['日期'] = pd.to_datetime(df['日期'])
    df.set_index('日期', inplace=True)
    df.rename(columns={'开盘': 'open', '最高': 'high', '最低': 'low', '收盘': 'close', '成交量': 'volume', '成交额': 'amount'}, inplace=True)
    return bt.feeds.PandasData(dataname=df, name=name)

def _get_data_native(symbol="600519", start_date="20240101", end_date="20251231"):
    dt_start = datetime.strptime(start_date, '%Y%m%d')
    dt_end = datetime.strptime(end_date, '%Y%m%d')

    file_path = os.path.join(DATA_DIR, f"{symbol}.csv")
    # 读取本地 CSV
    df = pd.read_csv(file_path)
    df['日期'] = pd.to_datetime(df['日期'])
    # 过滤数据区间
    df = df[(df['日期'] >= dt_start) & (df['日期'] <= dt_end)]
    df.set_index('日期', inplace=True)
    df.rename(columns={'开盘': 'open', '最高': 'high', '最低': 'low', '收盘': 'close', '成交量': 'volume'}, inplace=True)
    data = bt.feeds.PandasData(dataname=df, name=symbol)
    return data

def get_all_stock_codes():
    """
        获取所有股票代码
    """
    return [f.replace(".csv", "") for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
