"""
分红数据抓取 — 通过 Cloudflare Worker 从 Yahoo Finance 获取
A股用 601398.SS 格式，H股用 1398.HK 格式
注意：Yahoo 年份是除息日年份，脚本自动修正为财年（-1年）
"""
import json, os, time, urllib.request
from datetime import datetime, timezone, timedelta

WORKER_URL     = "https://stock-proxy.changyoukin.workers.dev"
DIVIDENDS_FILE = "data/dividends.json"
STOCKS_FILE    = "config/stocks.json"
BJT = timezone(timedelta(hours=8))

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

def yahoo_ticker_a(code_a):
    """A股 Yahoo ticker: 601398 → 601398.SS（沪市），深市用.SZ"""
    return f"{code_a}.SS"  # 六大行、能源、电信都是沪市

def yahoo_ticker_h(ticker_h):
    """H股 Yahoo ticker: 1398.HK 直接用"""
    return ticker_h

def fetch_dividends_yahoo(yahoo_ticker):
    """通过 Worker 从 Yahoo Finance 拿历史分红，返回 {财年: 每股分红}"""
    url = f"{WORKER_URL}?type=div&ticker={yahoo_ticker}"
    text = fetch_url(url)
    if not text:
        return {}
    try:
        data = json.loads(text)
        if "error" in data:
            print(f"    Worker错误: {data['error']}")
            return {}

        raw = data.get("dividends", {})
        currency = data.get("currency", "")

        # Yahoo 年份是除息日年份，财年 = 除息年 - 1
        # 例：2026年除息 → 2025年财报分红
        result = {}
        for year_str, amount in raw.items():
            year = int(year_str)
            fiscal_year = str(year - 1)  # 修正为财年
            # 同一财年可能有中期+末期，累加
            result[fiscal_year] = round(result.get(fiscal_year, 0) + amount, 4)

        return result
    except Exception as e:
        print(f"    解析失败: {e}")
        return {}

def main():
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    print(f"\n{'='*55}\n  分红数据更新 {today}\n{'='*55}")

    stocks = load_all_stocks()
    os.makedirs("data", exist_ok=True)

    db = load_json(DIVIDENDS_FILE, {
        "meta": {
            "description": "高股息股票历年每股分红",
            "source": "Yahoo Finance via Cloudflare Worker",
            "last_updated": ""
        },
        "banks": {}
    })

    for key, stock in stocks.items():
        print(f"\n[{stock['sector_name']}] {stock['name']}")

        # 优先用 A股数据（人民币，更直接）
        ticker_a = yahoo_ticker_a(stock["code_a"])
        print(f"    A股 {ticker_a}...")
        divs_a = fetch_dividends_yahoo(ticker_a)

        if divs_a:
            print(f"    ✓ A股分红 {len(divs_a)} 年: {divs_a}")
        else:
            print(f"    ✗ A股失败，尝试H股...")

        # H股作为补充（港元，需标注）
        ticker_h = yahoo_ticker_h(stock["ticker_h"])
        print(f"    H股 {ticker_h}...")
        divs_h = fetch_dividends_yahoo(ticker_h)

        if divs_h:
            print(f"    ✓ H股分红 {len(divs_h)} 年: {divs_h}")

        # 写入数据库，A股优先
        divs = divs_a if divs_a else divs_h
        currency = "CNY" if divs_a else "HKD"

        if divs:
            if key not in db["banks"]:
                db["banks"][key] = {
                    "name": stock["name"],
                    "sector": stock["sector"],
                    "dividends": {},
                    "h_dividends": {}
                }
            # A股分红（人民币）
            if divs_a:
                db["banks"][key]["dividends"] = dict(sorted(divs_a.items()))
            # H股分红（港元）单独存，供参考
            if divs_h:
                db["banks"][key]["h_dividends"] = dict(sorted(divs_h.items()))
            db["banks"][key]["currency"] = currency
        else:
            print(f"    ✗ 两个接口都失败")

        time.sleep(0.5)

    db["meta"]["last_updated"] = today
    db["meta"]["source"] = "Yahoo Finance via Cloudflare Worker"

    with open(DIVIDENDS_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 已写入 {DIVIDENDS_FILE}")

if __name__ == "__main__":
    main()
