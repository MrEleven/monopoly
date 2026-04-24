import akshare as ak

try:
    # 尝试抓取一次最稳的股票
    df = ak.stock_zh_a_hist(symbol="600519", period="daily", 
                            start_date="20240101", end_date="20241231", 
                            adjust="qfq")
    print(df.head())
except Exception as e:
    print(f"报错详情: {e}")