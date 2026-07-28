"""데이터 소스 실측 프로브 — 사내망에서 무엇이 되고 무엇이 안 되는지 확정한다."""
import truststore
truststore.inject_into_ssl()

import io
import json

import requests

UA = {"User-Agent": "DaolResearch RA animsam09@gmail.com"}
T = 25


def probe(name, fn):
    try:
        note = fn()
        print(f"[OK]   {name:26s} {note}")
        return True
    except Exception as e:
        print(f"[FAIL] {name:26s} {type(e).__name__}: {str(e)[:110]}")
        return False


def sec_frames():
    """업종 집계의 핵심: 한 개념(concept)의 전 기업 값을 한 번에."""
    u = "https://data.sec.gov/api/xbrl/frames/us-gaap/PaymentsToAcquirePropertyPlantAndEquipment/USD/CY2024.json"
    d = requests.get(u, headers=UA, timeout=T).json()
    return f"capex CY2024, {len(d['data'])}개 기업"


def sec_tickers():
    u = "https://www.sec.gov/files/company_tickers.json"
    d = requests.get(u, headers=UA, timeout=T).json()
    return f"티커→CIK 매핑 {len(d)}건"


def sec_fts():
    """신기술 축: 10-K/10-Q 전문검색 키워드 확산."""
    u = 'https://efts.sec.gov/LATEST/search-index?q=%22liquid+cooling%22&forms=10-K'
    d = requests.get(u, headers=UA, timeout=T).json()
    return f"FTS hits={d.get('hits', {}).get('total', {}).get('value')}"


def bls_ppi():
    """스프레드 축: 산출가격 PPI."""
    u = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    body = {"seriesid": ["PCU333611333611", "WPU061"], "startyear": "2022", "endyear": "2026"}
    d = requests.post(u, json=body, headers={**UA, "Content-Type": "application/json"}, timeout=T).json()
    n = [len(s["data"]) for s in d.get("Results", {}).get("series", [])]
    return f"status={d.get('status')} 시리즈별 관측치={n}"


def fred_csv():
    """가동률/거시: API 키 없이 CSV 엔드포인트."""
    u = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=TCU,MCUMFN"
    txt = requests.get(u, headers=UA, timeout=T).text
    lines = [l for l in txt.strip().split("\n") if l]
    return f"가동률 CSV {len(lines)}행, 최신={lines[-1][:40]}"


def census_m3():
    """재고·신규수주 축."""
    u = ("https://api.census.gov/data/timeseries/eits/m3adv"
         "?get=cell_value,data_type_code,category_code,seasonally_adj&time=2025&for=us:*")
    d = requests.get(u, headers=UA, timeout=T).json()
    return f"M3 advance {len(d) - 1}행"


def fed_register():
    """정책 축: 시행 예정 규제."""
    u = ("https://www.federalregister.gov/api/v1/documents.json"
         "?per_page=5&conditions[type][]=RULE&order=newest")
    d = requests.get(u, headers=UA, timeout=T).json()
    return f"규칙 {d.get('count')}건 검색가능"


def stooq(sym="xlk.us"):
    """가격 축: 무키 CSV."""
    u = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    txt = requests.get(u, headers=UA, timeout=T).text
    lines = txt.strip().split("\n")
    return f"{sym} {len(lines) - 1}일봉, 최신={lines[-1]}"


def yahoo():
    u = "https://query1.finance.yahoo.com/v8/finance/chart/XLK?range=2y&interval=1d"
    d = requests.get(u, headers=UA, timeout=T).json()
    n = len(d["chart"]["result"][0]["timestamp"])
    return f"XLK {n}일봉"


CHECKS = [
    ("SEC XBRL frames", sec_frames),
    ("SEC 티커매핑", sec_tickers),
    ("SEC 전문검색(FTS)", sec_fts),
    ("BLS PPI v2", bls_ppi),
    ("FRED CSV(무키)", fred_csv),
    ("Census M3", census_m3),
    ("Federal Register", fed_register),
    ("Stooq 주가", stooq),
    ("Yahoo 주가", yahoo),
]

if __name__ == "__main__":
    ok = sum(probe(n, f) for n, f in CHECKS)
    print(f"\n{ok}/{len(CHECKS)} 사용 가능")
