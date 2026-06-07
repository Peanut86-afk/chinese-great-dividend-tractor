import json, os, time, urllib.request
from datetime import datetime, timezone, timedelta

PRICES_FILE = "data/prices.json"
STOCKS_FILE = "config/stocks.json"
BJT = timezone(timedelta(hours=8))

def today_str():
    return datetime.now(BJT).strftime("%Y-%m-%d")

def fetch_url(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try: return raw.decode("gbk")
            except: return raw.decode("utf-8", errors="replace")
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

def fetch_a_prices(stocks):
    """一次请求所有A股，新浪支持批量"""
    tickers = ",".join(s["ticker_a"] for s in stocks.values())
    url = f"https://hq.sinajs.cn/list={tickers}"
    headers = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
    text = fetch_url(url, headers)
    if not text:
        return {}
    result = {}
    for key, s in stocks.items():
        marker = f'hq_str_{s["ticker_a"]}="'
        idx = text.find(marker)
        if idx == -1:
            continue
        fields = text[idx+len(marker):text.find('"', idx+len(marker))].split(",")
        if len(fields) >= 6:
            try:
                low = float(fields[5])
                if low > 0:
                    result[key] = round(low, 4)
                    print(f"    ✓ {s['name']} A股最低: ¥{low}")
            except ValueError:
                pass
    return result

def fetch_h_price(key, stock):
    ticker = stock["ticker_h"].replace(".", "-")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
    text = fetch_url(url)
    if not text:
        return None
    try:
        data = json.loads(text)
        low = data["chart"]["result"][0]["indicators"]["quote"][0]["low"][0]
        if low and low > 0:
            print(f"    ✓ {stock['name']} H股最低: HK${low:.2f}")
            return round(low, 4)
    except Exception as e:
        print(f"    ✗ {stock['name']} H股失败: {e}")
    return None

def main():
    today = today_str()
    print(f"\n{'='*55}\n  每日股价抓取 {today}\n{'='*55}")

    stocks = load_all_stocks()
    print(f"  共 {len(stocks)} 只股票")

    os.makedirs("data", exist_ok=True)
    db = load_json(PRICES_FILE, {"meta": {"source": "新浪财经+Yahoo Finance"}, "prices": {}})
    for key in stocks:
        if key not in db["prices"]:
            db["prices"][key] = {}

    print("\n[A股] 新浪财经...")
    a_prices = fetch_a_prices(stocks)

    print("\n[H股] Yahoo Finance...")
    h_prices = {}
    for key, stock in stocks.items():
        p = fetch_h_price(key, stock)
        if p:
            h_prices[key] = p
        time.sleep(0.4)

    updated = 0
    for key in stocks:
        entry = {}
        if key in a_prices: entry["a_low"] = a_prices[key]
        if key in h_prices: entry["h_low"] = h_prices[key]
        if entry:
            db["prices"][key][today] = entry
            updated += 1

    db["meta"]["last_updated"] = today
    with open(PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 完成，更新 {updated}/{len(stocks)} 只，已写入 {PRICES_FILE}")

if __name__ == "__main__":
    main()
