"""
一次性历史数据补录 — 通过 Cloudflare Worker 从 Yahoo Finance 获取
只抓历史年度最低价，分红由 fetch_dividends.py 单独处理
"""
import json, os, time, urllib.request
from datetime import datetime, timezone, timedelta

WORKER_URL  = "https://stock-proxy.changyoukin.workers.dev"
PRICES_FILE = "data/prices.json"
STOCKS_FILE = "config/stocks.json"
BJT = timezone(timedelta(hours=8))

def fetch_url(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
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

def fetch_history_via_worker(yahoo_ticker):
    """通过 Worker 拿 Yahoo Finance 10年日线，返回 {year: 最低价}"""
    url = f"{WORKER_URL}?type=history&ticker={yahoo_ticker}"
    text = fetch_url(url)
    if not text:
        return {}
    try:
        data = json.loads(text)
        if "error" in data:
            print(f"    Worker错误: {data['error']}")
            return {}
        return data.get("year_lows", {})
    except Exception as e:
        print(f"    解析失败: {e}")
        return {}

def yahoo_ticker_a(code_a):
    return f"{code_a}.SS"  # 全部沪市

def main():
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    print(f"\n{'='*55}")
    print(f"  历史数据补录  2015—{today[:4]}")
    print(f"{'='*55}")

    stocks = load_all_stocks()
    print(f"  共 {len(stocks)} 只股票，分 {len(set(s['sector'] for s in stocks.values()))} 个板块")

    os.makedirs("data", exist_ok=True)
    db = load_json(PRICES_FILE, {
        "meta": {"source": "Yahoo Finance via Cloudflare Worker"},
        "prices": {}
    })
    for key in stocks:
        if key not in db["prices"]:
            db["prices"][key] = {}

    for key, stock in stocks.items():
        print(f"\n{'─'*50}")
        print(f"  [{stock['sector_name']}] {stock['name']}")
        print(f"{'─'*50}")

        # A股历史
        ticker_a = yahoo_ticker_a(stock["code_a"])
        print(f"  A股 {ticker_a}...")
        a_lows = fetch_history_via_worker(ticker_a)
        if a_lows:
            print(f"  ✓ {len(a_lows)} 年: {a_lows}")
        else:
            print(f"  ✗ A股历史失败")
        time.sleep(0.8)

        # H股历史
        ticker_h = stock["ticker_h"]
        print(f"  H股 {ticker_h}...")
        h_lows = fetch_history_via_worker(ticker_h)
        if h_lows:
            print(f"  ✓ {len(h_lows)} 年: {h_lows}")
        else:
            print(f"  ✗ H股历史失败")
        time.sleep(0.8)

        # 写入年度最低价（key格式：YYYY-annual）
        all_years = set(list(a_lows.keys()) + list(h_lows.keys()))
        for year in all_years:
            year_key = f"{year}-annual"
            entry = db["prices"][key].get(year_key, {})
            if year in a_lows:
                entry["a_low"] = a_lows[year]
            if year in h_lows:
                entry["h_low"] = h_lows[year]
            db["prices"][key][year_key] = entry

        print(f"  ✓ 写入 {len(all_years)} 年数据")

    db["meta"]["last_updated"] = today
    with open(PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*55}")
    print(f"  完成！已写入 {PRICES_FILE}")
    print(f"{'='*55}")

if __name__ == "__main__":
    main()
