"""
从巨潮资讯爬取六大银行历史分红数据
运行时机：每年4月手动触发一次（年报季结束后）
也可以在 GitHub Actions 里设置每月1号自动跑，有新数据就更新
"""

import json
import os
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

BANKS = {
    "icbc":  {"name": "工商银行", "code": "601398", "market": "沪市"},
    "ccb":   {"name": "建设银行", "code": "601939", "market": "沪市"},
    "abc":   {"name": "农业银行", "code": "601288", "market": "沪市"},
    "boc":   {"name": "中国银行", "code": "601988", "market": "沪市"},
    "comm":  {"name": "交通银行", "code": "601328", "market": "沪市"},
    "psbc":  {"name": "邮储银行", "code": "601658", "market": "沪市"},
}

DIVIDENDS_FILE = "dividends.json"
BJT = timezone(timedelta(hours=8))

def fetch_url(url, headers=None, data=None, timeout=15):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ✗ 请求失败: {e}")
        return None

def fetch_dividends_cninfo(code):
    """
    巨潮资讯 API 获取分红数据
    接口: http://www.cninfo.com.cn/new/hisAnnouncement/query
    """
    url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "http://www.cninfo.com.cn/",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    # 巨潮分红数据接口
    dividend_url = f"http://www.cninfo.com.cn/data20/financialData/dividendList?scode={code}&pageNum=1&pageSize=50"
    text = fetch_url(dividend_url, headers)
    if not text:
        return {}

    try:
        data = json.loads(text)
        records = data.get("data", {}).get("dividendList", [])
        result = {}
        for rec in records:
            # 取除权除息日年份
            ex_date = rec.get("exDividendDate", "") or rec.get("recordDate", "")
            if not ex_date:
                continue
            year = ex_date[:4]
            # 每股现金股利（税前）
            div_per_share = rec.get("cashDividendRatio", 0)
            if div_per_share and float(div_per_share) > 0:
                # 巨潮给的是每10股，换算成每股
                per_share = round(float(div_per_share) / 10, 4)
                # 同一年可能有中期+末期，累加
                result[year] = round(result.get(year, 0) + per_share, 4)
        return result
    except Exception as e:
        print(f"  ✗ 解析失败: {e}")
        return {}

def fetch_dividends_backup(code):
    """
    备用方案：爬取新浪财经分红页面
    """
    url = f"https://money.finance.sina.com.cn/corp/go.php/vISSUE_ShareBonus/stockid/{code}.phtml"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn"
    }
    text = fetch_url(url, headers)
    if not text:
        return {}

    result = {}
    # 匹配年份和每股分红
    # 新浪页面格式: 2024-05-13 ... 每10股派X元
    pattern = r'(\d{4})-\d{2}-\d{2}.*?派(\d+\.?\d*)元'
    matches = re.findall(pattern, text)
    for year, amount in matches:
        per_share = round(float(amount) / 10, 4)
        result[year] = round(result.get(year, 0) + per_share, 4)
    return result

def main():
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    print(f"\n{'='*50}")
    print(f"  抓取分红数据: {today}")
    print(f"{'='*50}")

    # 读取已有数据
    if os.path.exists(DIVIDENDS_FILE):
        with open(DIVIDENDS_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {
            "meta": {
                "description": "六大国有银行历年每股分红（人民币/股，税前）",
                "source": "巨潮资讯",
                "update_frequency": "每年4月年报季后更新",
                "last_updated": ""
            },
            "banks": {}
        }

    for key, bank in BANKS.items():
        print(f"\n[{bank['name']}] 抓取中...")

        # 先试巨潮
        divs = fetch_dividends_cninfo(bank["code"])
        if not divs:
            print(f"  巨潮失败，尝试新浪备用...")
            divs = fetch_dividends_backup(bank["code"])

        if divs:
            print(f"  ✓ 获取到 {len(divs)} 年数据: {divs}")
            # 合并到已有数据（新数据优先）
            if key not in db["banks"]:
                db["banks"][key] = {
                    "name": bank["name"],
                    "code": bank["code"],
                    "dividends": {}
                }
            db["banks"][key]["dividends"].update(divs)
            # 按年份排序
            db["banks"][key]["dividends"] = dict(
                sorted(db["banks"][key]["dividends"].items())
            )
        else:
            print(f"  ✗ 未能获取 {bank['name']} 分红数据")

        time.sleep(1)

    db["meta"]["last_updated"] = today

    with open(DIVIDENDS_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 分红数据已写入 {DIVIDENDS_FILE}")

if __name__ == "__main__":
    main()
