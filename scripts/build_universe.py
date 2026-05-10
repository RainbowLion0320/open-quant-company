#!/usr/bin/env python3
"""
构建股票池 — 从沪深300+中证500成分股拉取，写入 data/universe_raw.json
用法: python scripts/build_universe.py
"""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(key, None)
os.environ["no_proxy"] = ".sina.com.cn,.10jqka.com.cn"

import akshare as ak

def fetch_index(index_symbol, pool_tag):
    """拉指数成分股并标记池"""
    print(f"拉取 {'沪深300' if pool_tag == 'hs300' else '中证500'} 成分股...")
    df = ak.index_stock_cons_sina(symbol=index_symbol)
    stocks = []
    for _, row in df.iterrows():
        stocks.append({
            "code": row["code"],
            "name": row["name"],
            "mktcap": float(row.get("mktcap", 0)),
            "pool": pool_tag,
        })
    stocks.sort(key=lambda x: -x["mktcap"])
    return stocks

def main():
    hs300 = fetch_index("000300", "hs300")
    print(f"  沪深300: {len(hs300)} 只")
    time.sleep(3)

    csi500 = fetch_index("000905", "csi500")
    print(f"  中证500: {len(csi500)} 只")

    # 合并去重（沪深300优先）
    seen = {s["code"] for s in hs300}
    merged = list(hs300)
    for s in csi500:
        if s["code"] not in seen:
            merged.append(s)
            seen.add(s["code"])

    print(f"  合并去重: {len(merged)} 只")

    output = os.path.join(os.path.dirname(__file__), "..", "data", "universe_raw.json")
    with open(output, "w") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"  已保存到 {output}")

    # 统计行业覆盖
    industries = {}
    for s in merged:
        ind = _guess_industry(s["code"], s["name"])
        industries[ind] = industries.get(ind, 0) + 1
    print(f"\n行业分布 (已知分类):")
    for ind, cnt in sorted(industries.items(), key=lambda x: -x[1]):
        print(f"  {ind}: {cnt} 只")
    print(f"  待分类: {industries.get('待分类', 0)} 只")

from data.symbols import KNOWN_INDUSTRY
def _guess_industry(code, name):
    if code in KNOWN_INDUSTRY:
        return KNOWN_INDUSTRY[code]
    return "待分类"

if __name__ == "__main__":
    main()
