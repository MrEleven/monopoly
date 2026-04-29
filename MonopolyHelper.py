
def get_limit_price(prev_close, stock_name):
    """
    根据代码识别板块并判断今日收盘是否封死涨跌停
    """
    # 识别板块比例（主板10%，双创20%，北交30%）
    if stock_name.startswith(('688', '30')): 
        limit_ratio = 0.20
    elif stock_name.startswith(('8', '4')): 
        limit_ratio = 0.30
    else: 
        limit_ratio = 0.10

    # 计算理论涨跌停价（精确到分）
    limit_up_price = round(prev_close * (1 + limit_ratio) + 0.0001, 2)
    limit_down_price = round(prev_close * (1 - limit_ratio) + 0.0001, 2)
    return limit_up_price, limit_down_price