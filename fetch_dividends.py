import json, os, re, time, urllib.request
from datetime import datetime, timezone, timedelta

BANKS = {
    "icbc":  {"name": "工商银行", "code": "601398"},
    "ccb":   {"name": "建设银行", "code": "601939"},
    "abc":   {"name": "农业银行", "code": "601288"},
    "boc":   {"name": "中国银行", "code": "601988"},
    "comm":  {"name": "交通银行", "code": "601328"},
    "psbc":  {"name": "邮储银行", "code": "601658"},
}
DIVIDENDS_FILE = "dividends.json"
BJT = timezone(timedelta(hours=8))

def fetch_url(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  请求失败: {e}")
        return None

def load_db():
    default = {
        "meta": {
            "description": "六大国有银行历年每股分红（人民币/股，税前）",
            "source": "巨潮资讯",
            "last_updated": ""
        },
        "banks": {}
    }
    if not os.path.exists(DIVIDENDS_FILE):
        return default
    try:
        content = open(DIVIDENDS_FILE, "r", encoding="utf-8").read().strip()
        if not content:
            return default
        return json.loads(content)
    except Exception:
        print("dividends.json 读取失败，重新初始化")
        return default

def fetch_dividends_cninfo(code):
    url = f"http://www.cninfo.com.cn/data20/financialData/dividendList?scode={code}&pageNum=1&pageSize=50"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://www.cninfo.com.cn/",
    }
    text = fetch_url(url, headers)
    if not text:
        return {}
    try:
        data = json.loads(text)
        records = data.get("data", {}).get("dividendList", [])
        result = {}
        for rec in records:
            ex_date = rec.get("exDividendDate", "") or rec.get("recordDate", "")
            if not ex_date:
                continue
            year = ex_date[:4]
            div = rec.get("cashDividendRatio", 0)
            if div and float(div) > 0:
                per_share = round(float(div) / 10, 4)
                result[year] = round(result.get(year, 0) + per_share, 4)
        return result
    except Exception as e:
        print(f"  巨潮解析失败: {e}")
        return {}

def fetch_dividends_sina(code):
    url = f"https://money.finance.sina.com.cn/corp/go.php/vISSUE_ShareBonus/stockid/{code}.phtml"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
    text = fetch_url(url, headers)
    if not text:
        return {}
    result = {}
    pattern = r'(\d{4})-\d{2}-\d{2}.*?派(\d+\.?\d*)元'
    for year, amount in re.findall(pattern, text):
        per_share = round(float(amount) / 10, 4)
        result[year] = round(result.get(year, 0) + per_share, 4)
    return result

def main():
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    print(f"\n{'='*50}\n  抓取分红数据: {today}\n{'='*50}")
    db = load_db()

    for key, bank in BANKS.items():
        print(f"\n[{bank['name']}] 抓取中...")
        divs = fetch_dividends_cninfo(bank["code"])
        if not divs:
            print("  巨潮失败，尝试新浪备用...")
            divs = fetch_dividends_sina(bank["code"])
        if divs:
            print(f"  获取到 {len(divs)} 年数据: {divs}")
            if key not in db["banks"]:
                db["banks"][key] = {"name": bank["name"], "code": bank["code"], "dividends": {}}
            db["banks"][key]["dividends"].update(divs)
            db["banks"][key]["dividends"] = dict(sorted(db["banks"][key]["dividends"].items()))
        else:
            print(f"  未能获取 {bank['name']} 分红数据")
        time.sleep(1)

    db["meta"]["last_updated"] = today
    with open(DIVIDENDS_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f"\n完成，已写入 {DIVIDENDS_FILE}")

if __name__ == "__main__":
    main()
