"""
一次性历史数据补录 — 从 stocks.json 读取配置
抓取2015年至今所有股票的历史最低价 + 历史分红
只需跑一次！
"""
import json, os, re, time, urllib.request
from datetime import datetime, timezone, timedelta

PRICES_FILE    = "data/prices.json"
DIVIDENDS_FILE = "data/dividends.json"
STOCKS_FILE    = "config/stocks.json"
BJT  = timezone(timedelta(hours=8))
START = "20150101"
END   = datetime.now(BJT).strftime("%Y%m%d")

def fetch_url(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try: return raw.decode("utf-8")
            except: return raw.decode("gbk", errors="replace")
    except Exception as e:
        print(f"    请求失败: {e}")
        return None

def load_json(path, default):
    if not os.path.exists(path): return default
    try:
        content = open(path, "r", encoding="utf-8").read().strip()
        return json.loads(content) if content else default
    except Exception: return default

def load_all_stocks():
    cfg = load_json(STOCKS_FILE, {})
    stocks = {}
    for sector_key, sector in cfg.get("sectors", {}).items():
        for key, info in sector.get("stocks", {}).items():
            stocks[key] = {**info, "sector": sector_key, "sector_name": sector["name"]}
    return stocks

def fetch_eastmoney_kline(secid):
    """东方财富日线接口，返回 {year: 最低价}"""
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt=101&fqt=1&beg={START}&end={END}&cb=jQuery"
    )
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.eastmoney.com"}
    text = fetch_url(url, headers)
    if not text: return {}
    m = re.search(r'jQuery\((.*)\)', text, re.DOTALL)
    if m: text = m.group(1)
    try:
        klines = json.loads(text).get("data", {}).get("klines", [])
    except Exception as e:
        print(f"    解析失败: {e}")
        return {}
    year_low = {}
    for line in klines:
        parts = line.split(",")
        if len(parts) < 5: continue
        year = parts[0][:4]
        try:
            low = float(parts[4])
            if low > 0 and (year not in year_low or low < year_low[year]):
                year_low[year] = round(low, 4)
        except ValueError: pass
    return year_low

def fetch_cninfo(code):
    url = f"http://www.cninfo.com.cn/data20/financialData/dividendList?scode={code}&pageNum=1&pageSize=50"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://www.cninfo.com.cn/"}
    text = fetch_url(url, headers)
    if not text: return {}
    try:
        records = json.loads(text).get("data", {}).get("dividendList", [])
        result = {}
        for rec in records:
            ex_date = rec.get("exDividendDate", "") or rec.get("recordDate", "")
            if not ex_date: continue
            year = ex_date[:4]
            div = rec.get("cashDividendRatio", 0)
            if div and float(div) > 0:
                per_share = round(float(div) / 10, 4)
                result[year] = round(result.get(year, 0) + per_share, 4)
        return result
    except Exception as e:
        print(f"    巨潮解析失败: {e}")
        return {}

def fetch_sina_div(code):
    url = f"https://money.finance.sina.com.cn/corp/go.php/vISSUE_ShareBonus/stockid/{code}.phtml"
    text = fetch_url(url, {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"})
    if not text: return {}
    result = {}
    for year, amount in re.findall(r'(\d{4})-\d{2}-\d{2}.*?派(\d+\.?\d*)元', text):
        per_share = round(float(amount) / 10, 4)
        result[year] = round(result.get(year, 0) + per_share, 4)
    return result

def main():
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    print(f"\n{'='*55}")
    print(f"  历史数据补录  {START[:4]}—{today[:4]}")
    print(f"{'='*55}")

    stocks = load_all_stocks()
    print(f"  共 {len(stocks)} 只股票，分 {len(set(s['sector'] for s in stocks.values()))} 个板块")

    os.makedirs("data", exist_ok=True)
    prices_db = load_json(PRICES_FILE, {
        "meta": {"description": "高股息股票每日/年度最低价", "source": "东方财富"},
        "prices": {}
    })
    divs_db = load_json(DIVIDENDS_FILE, {
        "meta": {"description": "高股息股票历年每股分红", "source": "巨潮资讯", "last_updated": ""},
        "banks": {}
    })

    for key in stocks:
        if key not in prices_db["prices"]:
            prices_db["prices"][key] = {}

    for key, stock in stocks.items():
        print(f"\n{'─'*50}")
        print(f"  [{stock['sector_name']}] {stock['name']}")
        print(f"{'─'*50}")

        # A股历史
        print(f"  A股历史日线...")
        a_lows = fetch_eastmoney_kline(f"{stock['market_a']}.{stock['code_a']}")
        if a_lows:
            print(f"  ✓ {len(a_lows)} 年: {a_lows}")
        else:
            print(f"  ✗ 失败")
        time.sleep(0.8)

        # H股历史
        print(f"  H股历史日线...")
        h_lows = fetch_eastmoney_kline(f"116.{stock['code_h']}")
        if h_lows:
            print(f"  ✓ {len(h_lows)} 年: {h_lows}")
        else:
            print(f"  ✗ 失败")
        time.sleep(0.8)

        # 写入年度最低价（key格式：YYYY-annual）
        for year in set(list(a_lows.keys()) + list(h_lows.keys())):
            year_key = f"{year}-annual"
            entry = prices_db["prices"][key].get(year_key, {})
            if year in a_lows: entry["a_low"] = a_lows[year]
            if year in h_lows: entry["h_low"] = h_lows[year]
            prices_db["prices"][key][year_key] = entry

        # 分红
        print(f"  分红数据...")
        divs = fetch_cninfo(stock["code_a"])
        if not divs:
            print(f"  巨潮失败，尝试新浪...")
            divs = fetch_sina_div(stock["code_a"])
        if divs:
            print(f"  ✓ {len(divs)} 年分红: {divs}")
            if key not in divs_db["banks"]:
                divs_db["banks"][key] = {
                    "name": stock["name"],
                    "sector": stock["sector"],
                    "dividends": {}
                }
            divs_db["banks"][key]["dividends"].update(divs)
            divs_db["banks"][key]["dividends"] = dict(
                sorted(divs_db["banks"][key]["dividends"].items())
            )
        else:
            print(f"  ✗ 分红获取失败")
        time.sleep(1)

    prices_db["meta"]["last_updated"] = today
    divs_db["meta"]["last_updated"] = today

    with open(PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump(prices_db, f, ensure_ascii=False, indent=2)
    with open(DIVIDENDS_FILE, "w", encoding="utf-8") as f:
        json.dump(divs_db, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*55}")
    print(f"  全部完成！")
    print(f"  价格 → {PRICES_FILE}")
    print(f"  分红 → {DIVIDENDS_FILE}")
    print(f"  后续每天由 fetch_prices.py 自动追加当日数据")
    print(f"  新增股票只需修改 config/stocks.json")
    print(f"{'='*55}")

if __name__ == "__main__":
    main()
