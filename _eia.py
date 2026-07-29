import sys,re; sys.path.insert(0,".")
from screener.sources import fred_series
from screener.net import fetch
def title(sid):
    try:
        h=fetch(f"https://fred.stlouisfed.org/series/{sid}",ttl_hours=24*30,timeout=25).decode("utf-8","replace")
        m=re.search(r"<title>(.*?)</title>",h,re.S)
        return re.sub(r"\s+"," ",m.group(1)).replace(" | FRED | St. Louis Fed","").strip() if m else ""
    except Exception: return ""
GROUPS={
 "정유 (EIA)": ["WPULEUS3","WCESTUS1","WGTSTUS1","WDISTUS1","WCRFPUS2","WRPUPUS2","WTTSTUS1"],
 "전력·원자력 (EIA)": ["IPN2211N2SQ","IPUTIL","IPG2211A2S","IPN2211A2RN","CAPUTLG2211A2S"],
 "천연가스 (EIA)": ["NGMPWA","WNGSTUS1"],
 "항공 (BTS/FRED)": ["AIRRPMTSID11","LOADFACTOR","AIRRPMTSI","TRUCKD11"],
 "철강·금속 (USGS/FRED)": ["IPG3311A2S","CAPUTLG3311A2S","PCU3311103311101"],
 "건설": ["TTLCONS","PRRESCONS","TLPRVCONS","PNRESCONS"],
}
for g,ids in GROUPS.items():
    print(f"\n### {g}")
    for sid in ids:
        try:
            s=fred_series(sid)
            print(f"   OK {sid:16s} {s[-1][0]} = {s[-1][1]:>12,.2f}  {title(sid)[:56]}")
        except Exception:
            pass
