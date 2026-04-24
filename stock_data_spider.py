import akshare as ak
import pandas as pd
import os
import time
from datetime import datetime, timedelta
import pdb
import requests
from functools import partial
import random

# 1. 定义一个伪造的浏览器 User-Agent
# 建议定期更换，或者使用 fake_useragent 库生成
MY_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Connection': 'keep-alive',
}

# 隧道域名:端口号
tunnel = "a672.kdltpspro.com:15818"

# 用户名密码方式
username = "t17654107521269"
password = "3yhrajk1"
# proxies = {
#     "http": "http://%(user)s:%(pwd)s@%(proxy)s/" % {"user": username, "pwd": password, "proxy": tunnel},
#     "https": "http://%(user)s:%(pwd)s@%(proxy)s/" % {"user": username, "pwd": password, "proxy": tunnel}
# }

proxies = {
    "http": "http://%(proxy)s/" % {"proxy": tunnel},
    "https": "http://%(proxy)s/" % {"proxy": tunnel}
}

# # 2. 核心黑科技：重写 requests.get 方法
# # 这样无论 AKShare 内部哪个接口调用 requests.get，都会强制带上我们的 User-Agent
# original_get = requests.get
# requests.get = partial(original_get, headers=MY_HEADERS, timeout=10, proxies=proxies)

# # 3. 同样的，如果有 POST 请求也可以拦截
# original_post = requests.post
# requests.post = partial(original_post, headers=MY_HEADERS, timeout=10, proxies=proxies)
# print("已成功全局注入伪造 User-Agent")

def download_all_a_stocks(save_dir="stock_data_5y"):
    """
    下载所有A股近5年的前复权日线数据
    """
    # 1. 创建存储目录
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        print(f"创建目录: {save_dir}")

    # 2. 获取所有 A 股代码清单
    print("正在获取全 A 股代码清单...")
    try:
        stock_zh_a_spot_df = ak.stock_zh_a_spot_em()
        stock_codes = stock_zh_a_spot_df['代码'].tolist()
        # df = ak.stock_info_a_code_name()
        # stock_codes = df['code'].tolist()
        total_count = len(stock_codes)
        print(f"获取成功，共计 {total_count} 只股票。")
    except Exception as e:
        print(f"获取清单失败: {e}")
        return

    # stock_codes = ["301683", "603459", "688811", "688813", "920011", 
    #     "920012", "920055", "920177", "920181"]
    # total_count = 5506

    # 设定全局结束日期（今天）
    # today_str = datetime.now().strftime('%Y%m%d')
    today_str = '20260417'
    # 设定默认起始日期（如果是新股票，下载近5年）
    default_start = (datetime.now() - pd.DateOffset(years=5)).strftime('%Y%m%d')

    success_count = 0
    update_count = 0
    skip_count = 0
    
    for i, code in enumerate(stock_codes):
        file_path = os.path.join(save_dir, f"{code}.csv")
        start_date = default_start
        existing_df = pd.DataFrame()

        # --- 增量逻辑开始 ---
        if os.path.exists(file_path):
            try:
                # 读取已有数据，获取最后一行日期
                existing_df = pd.read_csv(file_path)
                if not existing_df.empty:
                    # 假设日期列名为 '日期'，根据 ak.stock_zh_a_hist 的返回结果
                    last_date_str = str(existing_df['日期'].iloc[-1]).replace('-', '')
                    
                    # 如果本地最后日期已经等于或超过今天（比如周末跑了两次），则跳过
                    if last_date_str >= today_str:
                        skip_count += 1
                        continue
                    
                    # 从最后日期的后一天开始下载
                    last_dt = datetime.strptime(last_date_str, '%Y%m%d')
                    start_date = (last_dt + timedelta(days=1)).strftime('%Y%m%d')
            except Exception as e:
                print(f"读取本地文件 {code} 失败，将重新下载: {e}")
        # --- 增量逻辑结束 ---

        try:
            # 下载新数据
            # df = ak.stock_zh_a_daily(symbol="sh600519", start_date="20240101", end_date="20251231")
            new_df = ak.stock_zh_a_hist(
                symbol=code, 
                period="daily", 
                start_date=start_date, 
                end_date=today_str, 
                adjust="qfq"
            )
            
            if not new_df.empty:
                if not existing_df.empty:
                    # 合并数据并去重（防止日期重叠）
                    combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                    combined_df.drop_duplicates(subset=['日期'], keep='last', inplace=True)
                    combined_df.to_csv(file_path, index=False, encoding='utf-8-sig')
                    update_count += 1
                else:
                    new_df.to_csv(file_path, index=False, encoding='utf-8-sig')
                    success_count += 1
            else:
                print("empty ", code)
                skip_count += 1
            
            # if i % 10 == 0:
            print(f"进度: {i}/{total_count} | 新增: {success_count} | 更新: {update_count} | 跳过: {skip_count}")
            
            time.sleep(0.2) # 增量更新请求量小，可以稍微快一点

        except Exception as e:
            print(f"\n股票 {code} 更新失败: {e}")
            time.sleep(2.5) # 失败时多歇一会儿
            continue
        # # 随机休眠：不要用固定的 0.5 秒，模拟人类不规则点击
        # sleep_time = random.uniform(0.8, 2.5) 
        # time.sleep(sleep_time)
        
        # # 每下载 20 只股票，停顿很久（比如 10 秒），假装去喝杯水
        # if i % 20 == 0:
        #     print("模拟人工休息中...")
        #     time.sleep(random.randint(5, 12))
        # if i % 60 == 0:
        #     print("60个股票之后休息一分钟...")
        #     time.sleep(60)


    print(f"\n任务完成！")
    print(f"最终统计 - 总数: {total_count} | 纯新下: {success_count} | 增量更: {update_count} | 已最新: {skip_count}")

def filter():
    """找出非股票的数据"""
    pdb.set_trace()
    df = ak.stock_info_a_code_name()
    stock_codes = df['code'].tolist()
    files = [f for f in os.listdir("stock_data_5y") if f.endswith('.csv')]
    symbols = [filename.replace('.csv', '') for filename in  files]
    x = [symbol for symbol in symbols if symbol not in stock_codes]
    print(x)

def start():
    df = ak.stock_info_a_code_name()
    stock_codes = df['code'].tolist()
    for i,r in df.iterrows():
        print(r['code'] + '|' + r['name'])

if __name__ == '__main__':
    # 建议在运行前确保网络通畅
    # download_all_a_stocks()
    filter()
    # start()