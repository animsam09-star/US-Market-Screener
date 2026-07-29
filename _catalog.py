import sys, json; sys.path.insert(0,".")
from screener.net import fetch

def probe(sector, name, url, note=""):
    try:
        b = fetch(url, ttl_hours=0.05, timeout=20)
        head = b[:400].decode("utf-8","replace").lower()
        if "missing key" in head or "api key" in head and "invalid" in head:
            st = "키필요"
        elif b[:1] in (b"{", b"[") or b[:5]==b"%PDF-" or b"," in b[:200] and b"<html" not in head:
            st = "무키OK"
        elif "<html" in head or "<!doctype" in head:
            st = "HTML"
        else:
            st = "OK?"
        print(f"{st:7s} | {sector:12s} | {name:30s} | {len(b):>9,}B {note}")
    except Exception as e:
        msg = str(e)[:44]
        st = "키필요" if "403" in msg else "실패"
        print(f"{st:7s} | {sector:12s} | {name:30s} | {msg}")

T = [
 ("에너지","EIA v2 (키필요)","https://api.eia.gov/v2/petroleum/pnp/wiup/data/?frequency=weekly"),
 ("에너지","EIA 오픈데이터 브라우저","https://www.eia.gov/opendata/browser/"),
 ("농업","USDA NASS QuickStats","https://quickstats.nass.usda.gov/api/api_GET/?key=TEST&commodity_desc=CORN&format=JSON"),
 ("농업","USDA ESR(수출판매)","https://apps.fas.usda.gov/OpenData/api/esr/exports/commodityCode/401"),
 ("헬스케어","openFDA 의약품","https://api.fda.gov/drug/event.json?limit=1"),
 ("헬스케어","CMS 데이터","https://data.cms.gov/data-api/v1/dataset-summaries?size=1"),
 ("정부지출","USAspending","https://api.usaspending.gov/api/v2/references/agency/456/"),
 ("무역","Census Trade(키필요)","https://api.census.gov/data/timeseries/intltrade/exports/hs?get=CTY_NAME&time=2025-01"),
 ("운송","BTS 데이터포털","https://data.bts.gov/resource/gg82-cnge.json?$limit=1"),
 ("운송","FRA 철도안전","https://data.transportation.gov/resource/85tf-25kj.json?$limit=1"),
 ("노동","BLS v2 (키선택)","https://api.bls.gov/publicAPI/v1/timeseries/data/CES0000000001"),
 ("주택","FHFA 주택가격","https://www.fhfa.gov/hpi/download/monthly/hpi_master.csv"),
 ("규제","Federal Register","https://www.federalregister.gov/api/v1/documents.json?per_page=1"),
 ("규제","Regulations.gov(키필요)","https://api.regulations.gov/v4/documents?page[size]=1"),
 ("특허","USPTO PatentsView","https://search.patentsview.org/api/v1/patent/?q={\"_gte\":{\"patent_date\":\"2026-01-01\"}}"),
 ("광물","USGS 광물 API","https://mrdata.usgs.gov/mrds/wfs?service=WFS&request=GetCapabilities"),
 ("전력","EPA CAMPD(키필요)","https://api.epa.gov/easey/bulk-files/"),
 ("거시","World Bank","https://api.worldbank.org/v2/country/US/indicator/NY.GDP.MKTP.CD?format=json&per_page=1"),
 ("거시","OECD SDMX","https://sdmx.oecd.org/public/rest/dataflow/OECD.SDD.NAD/all/latest"),
]
print(f"{'상태':7s} | {'섹터':12s} | {'소스':30s} | 결과")
print("-"*95)
for sec,name,url in T:
    probe(sec,name,url)
