#!/usr/bin/env python3
"""北交所个股公开数据抓取（纯标准库）。用法:
  python3 fetch_bse.py --code 920029 --quote          # 实时快照
  python3 fetch_bse.py --code 920029 --kline 20240101  # 日K(前复权)
  python3 fetch_bse.py --code 920029 --fin             # 财务主要指标(按报告期)
  python3 fetch_bse.py --code 920029 --ann             # 公告列表(标题+art_code)
  python3 fetch_bse.py --code 920029 --ann-detail AN202610131830410921  # 公告正文
全部输出 JSON 到 stdout。"""
import argparse, json, sys, urllib.parse, urllib.request

UA = {"User-Agent": "Mozilla/5.0", "Referer": "http://quote.eastmoney.com/"}

def get(url, headers=None, data=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})},
                                 data=urllib.parse.urlencode(data).encode() if data else None)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def quote(code):
    fields = "f43,f44,f45,f46,f47,f48,f57,f58,f60,f84,f85,f92,f105,f107,f110,f111,f116,f117,f162,f167,f168,f169,f170,f171,f173,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192"
    # ut= 为东财网页公开参数（浏览器同款，非凭证）
  d = get(f"https://push2.eastmoney.com/api/qt/stock/get?ut=fa5fd1943c7b386f172d6893dbfba10b&invt=2&fltt=2&fields={fields}&secid=0.{code}")["data"]
    return d or {}

def kline(code, beg):
    d = get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.{code}&klt=101&fqt=1&beg={beg}&end=20500101&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f61")["data"]
    return {"name": d.get("name"), "klines": d.get("klines", [])}

def fin(code):
    u = ("https://datacenter.eastmoney.com/securities/api/data/v1/get?reportName=RPT_F10_FINANCE_MAINFINADATA"
         "&columns=ALL&filter=" + urllib.parse.quote(f'(SECUCODE="{code}.BJ")')
         + "&pageNumber=1&pageSize=12&sortTypes=-1&sortColumns=REPORT_DATE&source=HSF10&client=PC")
    return (get(u).get("result") or {}).get("data") or []

def ann(code):
    u = (f"https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=50&page_index=1"
         f"&ann_type=A&client_source=web&stock_list={code}&f_node=0&s_node=0")
    return (get(u).get("data") or {}).get("list") or []

def ann_detail(art_code):
    u = (f"https://np-cnotice-stock.eastmoney.com/api/content/ann?client_source=web&page_index=1"
         f"&art_code={art_code}&need_page=1")
    d = get(u).get("data") or {}
    return {"title": d.get("notice_title"), "pages": d.get("page_size"), "text": d.get("notice_content", "")[:20000]}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--code", required=True)
    p.add_argument("--quote", action="store_true")
    p.add_argument("--kline", metavar="BEG", nargs="?", const="20240101")
    p.add_argument("--fin", action="store_true")
    p.add_argument("--ann", action="store_true")
    p.add_argument("--ann-detail", metavar="ART_CODE")
    a = p.parse_args()
    out = {}
    try:
        if a.quote: out["quote"] = quote(a.code)
        if a.kline: out["kline"] = kline(a.code, a.kline)
        if a.fin: out["fin"] = fin(a.code)
        if a.ann: out["ann"] = ann(a.code)
        if a.ann_detail: out["ann_detail"] = ann_detail(a.ann_detail)
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
