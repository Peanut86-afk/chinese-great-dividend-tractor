"""
分红数据抓取 — 从 stocks.json 读取股票配置
数据源：巨潮资讯（备用：新浪财经）
"""
import json, os, re, time, urllib.request
from datetime import datetime, timezone, timedelta

DIVIDENDS_FILE = "data/dividends.json"
STOCKS_FILE    = "config/stocks.json"
BJT = timezone(timedelta(hours=8))

def fetch_url(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    请求失败: {e}")
        return None

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        content = open(path, "r", encoding="utf-8").read().strip()
        return json.loads(content) if content else default
    except Exception:
        return default

def load_all_stocks():
    cfg = load_json(STOCKS_FILE, {})
    stocks = {}
    for sector_key, sector in cfg.get("sectors", {}).items():
        for key, info in sector.get("stocks", {}).items():
            stocks[key] = {**info, "sector": sector_key}
    return stocks

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

def fetch_sina(code):
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
    print(f"\n{'='*55}\n  分红数据更新 {today}\n{'='*55}")

    stocks = load_all_stocks()
    os.makedirs("data", exist_ok=True)
    db = load_json(DIVIDENDS_FILE, {
        "meta": {"description": "高股息股票历年每股分红", "source": "巨潮资讯", "last_updated": ""},
        "banks": {}
    })

    for key, stock in stocks.items():
        print(f"\n[{stock['name']}]")
        divs = fetch_cninfo(stock["code_a"])
        if not divs:
            print("    巨潮失败，尝试新浪...")
            divs = fetch_sina(stock["code_a"])
        if divs:
            print(f"    ✓ {len(divs)} 年分红: {divs}")
            if key not in db["banks"]:
                db["banks"][key] = {"name": stock["name"], "sector": stock["sector"], "dividends": {}}
            db["banks"][key]["dividends"].update(divs)
            db["banks"][key]["dividends"] = dict(sorted(db["banks"][key]["dividends"].items()))
        else:
            print(f"    ✗ 获取失败")
        time.sleep(1)

    db["meta"]["last_updated"] = today
    with open(DIVIDENDS_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 已写入 {DIVIDENDS_FILE}")

if __name__ == "__main__":
    main()
