"""
每天自动抓取六大银行 A股 + H股 当日最低价
数据源：A股 → 新浪财经，H股 → Yahoo Finance
运行时机：GitHub Actions 每个交易日收盘后（北京时间 16:00）
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.error

# ── 配置 ────────────────────────────────────────────────────────
BANKS = {
    "icbc":  {"name": "工商银行", "ticker_a": "sh601398", "ticker_h": "1398.HK"},
    "ccb":   {"name": "建设银行", "ticker_a": "sh601939", "ticker_h": "939.HK"},
    "abc":   {"name": "农业银行", "ticker_a": "sh601288", "ticker_h": "1288.HK"},
    "boc":   {"name": "中国银行", "ticker_a": "sh601988", "ticker_h": "3988.HK"},
    "comm":  {"name": "交通银行", "ticker_a": "sh601328", "ticker_h": "3328.HK"},
    "psbc":  {"name": "邮储银行", "ticker_a": "sh601658", "ticker_h": "1658.HK"},
}

PRICES_FILE = "prices.json"
BJT = timezone(timedelta(hours=8))

def today_str():
    return datetime.now(BJT).strftime("%Y-%m-%d")

def fetch_url(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("gbk", errors="replace")
    except Exception as e:
        print(f"  ✗ 请求失败: {url} — {e}")
        return None

# ── A股最低价（新浪财经）────────────────────────────────────────
def fetch_a_prices():
    tickers = ",".join(b["ticker_a"] for b in BANKS.values())
    url = f"https://hq.sinajs.cn/list={tickers}"
    headers = {
        "Referer": "https://finance.sina.com.cn",
        "User-Agent": "Mozilla/5.0"
    }
    text = fetch_url(url, headers)
    if not text:
        return {}

    result = {}
    for key, bank in BANKS.items():
        # 新浪返回格式: var hq_str_sh601398="工商银行,开,收,现价,最高,最低,..."
        # 字段索引: 0=名称,1=今开,2=昨收,3=现价,4=最高,5=最低
        marker = f'hq_str_{bank["ticker_a"]}="'
        idx = text.find(marker)
        if idx == -1:
            print(f"  ✗ 未找到 {bank['name']} A股数据")
            continue
        start = idx + len(marker)
        end = text.find('"', start)
        fields = text[start:end].split(",")
        if len(fields) < 6:
            continue
        try:
            low = float(fields[5])
            if low > 0:
                result[key] = low
                print(f"  ✓ {bank['name']} A股最低价: ¥{low}")
        except ValueError:
            print(f"  ✗ {bank['name']} A股数据解析失败")
    return result

# ── H股最低价（Yahoo Finance）────────────────────────────────────
def fetch_h_price(key, bank):
    ticker = bank["ticker_h"].replace(".", "-")  # Yahoo用连字符
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
    headers = {"User-Agent": "Mozilla/5.0"}
    text = fetch_url(url, headers)
    if not text:
        return None
    try:
        data = json.loads(text)
        result = data["chart"]["result"][0]
        # 取当日最低价
        low = result["indicators"]["quote"][0]["low"][0]
        if low and low > 0:
            print(f"  ✓ {bank['name']} H股最低价: HK${low:.2f}")
            return round(low, 4)
    except Exception as e:
        print(f"  ✗ {bank['name']} H股数据解析失败: {e}")
    return None

# ── 主逻辑 ────────────────────────────────────────────────────────
def main():
    today = today_str()
    print(f"\n{'='*50}")
    print(f"  抓取日期: {today}")
    print(f"{'='*50}")

    # 读取已有数据
    if os.path.exists(PRICES_FILE):
        with open(PRICES_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {
            "meta": {"description": "六大国有银行每日最低价", "source": "新浪财经 + Yahoo Finance"},
            "prices": {key: {} for key in BANKS}
        }

    # 确保所有银行key都存在
    for key in BANKS:
        if key not in db["prices"]:
            db["prices"][key] = {}

    # 抓 A股
    print("\n[A股] 新浪财经...")
    a_prices = fetch_a_prices()

    # 抓 H股
    print("\n[H股] Yahoo Finance...")
    h_prices = {}
    for key, bank in BANKS.items():
        price = fetch_h_price(key, bank)
        if price:
            h_prices[key] = price
        time.sleep(0.5)  # 避免频率过高

    # 写入数据库
    updated = 0
    for key in BANKS:
        entry = {}
        if key in a_prices:
            entry["a_low"] = round(a_prices[key], 4)
        if key in h_prices:
            entry["h_low"] = round(h_prices[key], 4)
        if entry:
            db["prices"][key][today] = entry
            updated += 1

    db["meta"]["last_updated"] = today

    with open(PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 完成，更新了 {updated} 只股票的 {today} 数据")
    print(f"✓ 已写入 {PRICES_FILE}")

if __name__ == "__main__":
    main()
