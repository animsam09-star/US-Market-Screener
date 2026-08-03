"""Census 무역 통계 — ⑩ 대체·점유율 축의 근거.

왜 필요한가: 산업 전체가 안 커도 한쪽이 다른 쪽을 먹으면 그 안에서 승자가 난다.
가장 측정 가능한 형태가 **수입 대 국내 생산**이다. 국내 출하는 M3(FRED)에,
수입은 Census 무역통계에 있고, 둘을 합쳐야 침투율이 나온다.

Census API 응답은 배열의 배열이다(첫 행이 헤더).
    [["NAICS","GEN_VAL_MO","time"],
     ["331","1234567","2026-01"], ...]

무료 키 필요. 없으면 조용히 죽지 않고 사유를 남긴다.
"""
from __future__ import annotations

from datetime import date, datetime

from .keys import census_key
from .net import FetchError, fetch_json, purge

BASE = "https://api.census.gov/data/timeseries/intltrade"


class CensusError(RuntimeError):
    pass


def _rows(url: str) -> list[dict]:
    try:
        d = fetch_json(url, ttl_hours=24 * 7)
    except FetchError as e:
        raise CensusError(f"조회 실패: {e}") from e
    if not isinstance(d, list) or len(d) < 2:
        purge(url)
        raise CensusError(f"예상과 다른 응답 구조: {type(d).__name__} {str(d)[:100]}")
    head, *body = d
    return [dict(zip(head, r)) for r in body]


def trade_monthly(naics: str, flow: str = "imports", years: int = 6) -> list[tuple[date, float]]:
    """NAICS 별 월간 수입(또는 수출) 금액.

    flow: 'imports' | 'exports'
    """
    k = census_key()
    if not k:
        raise CensusError("Census 키 없음 (CENSUS_API_KEY / CENSUS_API 또는 census_key.txt)")

    val = "GEN_VAL_MO" if flow == "imports" else "ALL_VAL_MO"
    this_year = date.today().year
    out: list[tuple[date, float]] = []
    for y in range(this_year - years, this_year + 1):
        url = _year_url(naics, flow, val, y, k)
        try:
            rows = _rows(url)
        except CensusError:
            continue          # 해당 연도가 아직 없을 수 있다
        for r in rows:
            t = r.get("time") or ""
            v = r.get(val)
            try:
                dt = datetime.strptime(t + "-01", "%Y-%m-%d").date()
                out.append((dt, float(v)))
            except (ValueError, TypeError):
                continue
    if not out:
        raise CensusError(f"NAICS {naics} {flow}: 데이터 없음")
    out.sort()
    return out


def _year_url(naics: str, flow: str, val: str, y: int, key: str) -> str:
    # time 파라미터에 '='가 빠진 채(&time from …) 나가던 버그가 있었다 —
    # 전 연도 조회가 무효 쿼리로 죽어 '데이터 없음' 4개 테마가 났다(run 50).
    return (f"{BASE}/{flow}/naics?get=NAICS,{val}"
            f"&NAICS={naics}&time=from {y}-01 to {y}-12&key={key}").replace(" ", "%20")


def series_url(naics: str) -> str:
    return f"https://usatrade.census.gov/  (NAICS {naics})"
