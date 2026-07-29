import sys; sys.path.insert(0,".")
from screener.net import fetch
def probe(sector, name, url):
    try:
        b = fetch(url, ttl_hours=0.05, timeout=25)
        head = b[:500].decode("utf-8","replace")
        low = head.lower()
        if "missing key" in low or ("api" in low and "key" in low and ("invalid" in low or "required" in low)):
            st="키필요"
        elif b[:1] in (b"{", b"[") or b[:5]==b"%PDF-":
            st="무키OK"
        elif "<html" in low or "<!doctype" in low:
            st="HTML"
        elif b"," in b[:300]:
            st="CSV OK"
        else: st="OK?"
        print(f"{st:7s} | {sector:10s} | {name:30s} | {len(b):>9,}B")
    except Exception as e:
        m=str(e)[:46]
        print(f"{'키필요' if '403' in m else '실패':7s} | {sector:10s} | {name:30s} | {m}")

T=[
 ("농업","USDA NASS QuickStats","https://quickstats.nass.usda.gov/api/api_GET/?key=INVALID&source_desc=SURVEY&format=JSON"),
 ("헬스케어","CMS 데이터셋 목록","https://data.cms.gov/data.json"),
 ("헬스케어","openFDA 기기","https://api.fda.gov/device/510k.json?limit=1"),
 ("운송","BTS T-100 (Socrata)","https://data.transportation.gov/resource/f6a3-x9nq.json?$limit=1"),
 ("주택","Census 건축허가","https://www.census.gov/construction/bps/txt/tb2u202601.txt"),
 ("주택","FHFA HPI","https://www.fhfa.gov/hpi/download/monthly/hpi_master.csv"),
 ("특허","PatentsView(키필요)","https://search.patentsview.org/api/v1/patent/?q=%7B%22patent_id%22%3A%228000000%22%7D"),
 ("광물","USGS MRDS","https://mrdata.usgs.gov/mrds/mrds-csv.zip"),
 ("해운","USACE 항만통계","https://www.iwr.usace.army.mil/About/Technical-Centers/WCSC-Waterborne-Commerce-Statistics-Center/"),
 ("반도체","Census 반도체 M3","https://fred.stlouisfed.org/graph/fredgraph.csv?id=A34SNO"),
 ("전력","EIA 전력(키필요)","https://api.eia.gov/v2/electricity/rto/daily-region-data/data/?frequency=daily"),
 ("전력","NRC 원자로 가동률","https://www.nrc.gov/reading-rm/doc-collections/event-status/reactor-status/2026/20260101ps.html"),
 ("화학","BLS PPI 화학","https://api.bls.gov/publicAPI/v1/timeseries/data/PCU325211325211"),
 ("무역","USITC DataWeb","https://dataweb.usitc.gov/api/v2/report"),
 ("방산","DoD 계약공고","https://api.usaspending.gov/api/v2/search/spending_by_award/"),
 ("거시","IMF SDMX","https://dataservices.imf.org/REST/SDMX_JSON.svc/Dataflow"),
]
print(f"{'상태':7s} | {'섹터':10s} | {'소스':30s} | 결과"); print("-"*90)
for s,n,u in T: probe(s,n,u)
