import sys,re; sys.path.insert(0,".")
from screener.net import fetch
from screener.sources import fred_series
def title(sid):
    try:
        h=fetch(f"https://fred.stlouisfed.org/series/{sid}",ttl_hours=24*30,timeout=30).decode("utf-8","replace")
        m=re.search(r"<title>(.*?)</title>",h,re.S)
        return re.sub(r"\s+"," ",m.group(1)).replace(" | FRED | St. Louis Fed","").strip() if m else ""
    except Exception: return ""
print("### 산업별 재고/출하 비율 시리즈 탐색")
for sid in ["A31SIR","A32SIR","A33SIR","A34SIR","A35SIR","A36SIR","A24SIR",
            "ADEFIR","ANAPIR","MNFCTRIRSA","A31SIM","U35SIR"]:
    try:
        s=fred_series(sid)
        print(f"  OK {sid:12s} 최신 {s[-1][0]} = {s[-1][1]:.2f}  {title(sid)[:64]}")
    except Exception: pass
