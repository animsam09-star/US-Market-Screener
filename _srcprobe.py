import sys; sys.path.insert(0,".")
from screener.net import fetch, fetch_json, FetchError

def probe(name, url, want=None):
    try:
        b = fetch(url, ttl_hours=0.02, timeout=25)
        t = b[:300].decode("utf-8","replace")
        ok = (want in t) if want else (b"<html" not in b[:200].lower())
        print(f"[{'OK  ' if ok else '?   '}] {name:34s} {len(b):>8,}B  {t[:70]!r}")
    except Exception as e:
        print(f"[FAIL] {name:34s} {type(e).__name__}: {str(e)[:52]}")

print("### EIA — 키 없이 되나")
probe("EIA v2 (키없음)", "https://api.eia.gov/v2/petroleum/pnp/wiup/data/?frequency=weekly")
probe("EIA 오픈데이터 CSV", "https://www.eia.gov/dnav/pet/hist_xls/WPULEUS3w.xls")
probe("EIA 정제가동률 페이지", "https://www.eia.gov/dnav/pet/pet_pnp_unc_dcu_nus_w.htm")

print("\n### 기타 산업 지표")
probe("BTS 항공(T-100)", "https://www.transtats.bts.gov/Data_Elements.aspx?Data=2")
probe("USGS 광물요약", "https://pubs.usgs.gov/periodicals/mcs2025/mcs2025.pdf")
probe("Census 시계열 API", "https://api.census.gov/data/timeseries/eits/marts?get=cell_value&time=2025&for=us:*")
probe("EPA 전력배출(eGRID)", "https://www.epa.gov/egrid/download-data")
probe("USITC DataWeb", "https://datstage.usitc.gov/api/")
probe("DOE 우라늄", "https://www.eia.gov/uranium/marketing/")
