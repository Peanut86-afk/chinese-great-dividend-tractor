"""
每日股价抓取 — 通过 Cloudflare Worker 代理获取新浪数据
避免 GitHub Actions IP 被封问题
"""
import json, os, time, urllib.request
from datetime import datetime, timezone, timedelta

# ★ 部署 Cloudflare Worker 后填入你的 Worker URL
WORKER_URL = "https://stock-proxy.changyoukin.workers.dev"

PRICES_FILE = "data/prices.json"
STOCKS_FILE = "config/stocks.json"
BJT = timezone(timedelta(hours=8))

def today_str():
    return datetime.now(BJT).strftime("%Y-%m-%d")

def fetch_url(url, timeout=15):
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

def fetch_a_via_worker(stocks):
    """通过 Worker 获取 A股最低价"""
    tickers = ",".join(s["ticker_a"] for s in stocks.values())
    url = f"{WORKER_URL}?type=a&s={tickers}"
    text = fetch_url(url)
    if not text: return {}
    try:
        data = json.loads(text)
        result = {}
        for key, stock in stocks.items():
            ticker = stock["ticker_a"]
            if ticker in data:
                low = data[ticker]["low"]
                result[key] = round(low, 4)
                print(f"    ✓ {stock['name']} A股最低: ¥{low}")
        return result
    except Exception as e:
        print(f"    A股解析失败: {e}")
        return {}

def fetch_h_via_worker(stocks):
    """通过 Worker 获取 H股最低价，新浪港股代码格式 hk01398"""
    # 构建新浪港股代码: 1398.HK → hk01398
    def to_sina_hk(ticker_h):
        code = ticker_h.replace(".HK", "").replace(".hk", "")
        return f"hk{code.zfill(5)}"

    ticker_map = {to_sina_hk(s["ticker_h"]): key for key, s in stocks.items()}
    tickers = ",".join(ticker_map.keys())
    url = f"{WORKER_URL}?type=h&s={tickers}"
    text = fetch_url(url)
    if not text: return {}
    try:
        data = json.loads(text)
        result = {}
        for sina_code, stock_key in ticker_map.items():
            if sina_code in data:
                low = data[sina_code]["low"]
                result[stock_key] = round(low, 4)
                print(f"    ✓ {stocks[stock_key]['name']} H股最低: HK${low}")
        return result
    except Exception as e:
        print(f"    H股解析失败: {e}")
        return {}

def main():
    today = today_str()
    print(f"\n{'='*55}\n  每日股价抓取 {today}\n{'='*55}")

    if "你的worker名" in WORKER_URL:
        print("⚠ 请先在 fetch_prices.py 顶部填入你的 Cloudflare Worker URL！")
        return

    stocks = load_all_stocks()
    print(f"  共 {len(stocks)} 只股票")

    os.makedirs("data", exist_ok=True)
    db = load_json(PRICES_FILE, {"meta": {"source": "新浪财经(via Cloudflare Worker)"}, "prices": {}})
    for key in stocks:
        if key not in db["prices"]:
            db["prices"][key] = {}

    print("\n[A股]...")
    a_prices = fetch_a_via_worker(stocks)

    print("\n[H股]...")
    h_prices = fetch_h_via_worker(stocks)

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
    print(f"\n✓ 完成，更新 {updated}/{len(stocks)} 只")

if __name__ == "__main__":
    main()
