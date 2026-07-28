"""BEA 산업연관표 — '누가 이 산업의 산출물을 사는가'를 금액 비중으로 얻는다.

고객군을 10-K 본문 파싱으로 추정하는 것보다 훨씬 정확하다. Use 표는
행=상품(공급자 산업), 열=그 상품을 투입으로 쓰는 산업이고, 값은 달러다.
따라서 한 행을 가로로 읽으면 그 산업의 고객 명단이 금액 순으로 나온다.

주의: 이 모듈은 사내망에서 키가 없어 로컬 검증을 못 했다. 그래서
  - 표 ID 를 하드코딩하지 않고 런타임에 목록을 받아 고른다
  - 응답 구조를 그대로 덤프해 리포트에 남긴다 (다음 수정의 근거)
  - 어느 단계에서 실패했는지 반드시 사유를 남긴다
"""
from __future__ import annotations

import re
from collections import defaultdict

from .keys import bea_key
from .net import FetchError, fetch_json, purge

BASE = "https://apps.bea.gov/api/data"


class BeaError(RuntimeError):
    pass


def _call(params: str, ttl: float = 24 * 30) -> dict:
    k = bea_key()
    if not k:
        raise BeaError("BEA 키 없음 (환경변수 BEA_API_KEY 또는 bea_key.txt)")
    url = f"{BASE}?&UserID={k}&{params}&ResultFormat=JSON"

    # BEA 는 오류를 HTTP 200 에 담아 보낸다. 그런 응답이 캐시에 눌러앉으면
    # 키를 활성화한 뒤에도 계속 옛 오류를 읽는다. 그래서 오류를 만나면
    # 캐시를 걷어내고 한 번 다시 받는다 — 같은 실행 안에서 복구되도록.
    for attempt in (0, 1):
        try:
            d = fetch_json(url, ttl_hours=ttl if attempt == 0 else 0)
        except FetchError as e:
            raise BeaError(f"호출 실패: {e}") from e

        res = (d.get("BEAAPI") or {}).get("Results") or {}
        if "Error" not in res:
            return res

        err = res["Error"]
        msg = err.get("APIErrorDescription", err) if isinstance(err, dict) else err
        if attempt == 0 and purge(url):
            continue                      # 캐시된 오류였을 수 있다. 실물로 재확인
        purge(url)                        # 오류를 캐시에 남기지 않는다
        raise BeaError(f"BEA 거부: {msg}")
    raise BeaError("BEA 호출 실패")


def list_tables() -> list[dict]:
    res = _call("method=GetParameterValues&datasetname=InputOutput&ParameterName=TableID")
    return res.get("ParamValue", []) or []


def pick_use_table(tables: list[dict]) -> tuple[str, str]:
    """Use 표(요약 수준)를 고른다.

    '누가 샀나'는 Use 표에만 있다. Make 표는 '누가 만들었나'라 쓸 수 없다.
    Summary 수준을 쓴다 — Detail 은 5년마다만 나오고 코드가 너무 잘게 쪼개진다.
    """
    def desc(t):
        return str(t.get("Desc") or t.get("Description") or "")

    cands = [t for t in tables if "use" in desc(t).lower()]
    if not cands:
        raise BeaError(f"Use 표를 못 찾음. 사용 가능한 표: "
                       f"{[desc(t)[:60] for t in tables[:8]]}")
    # 우선순위: Summary + After Redefinitions > Summary > 그 외
    def rank(t):
        d = desc(t).lower()
        return (("summary" in d) * 2 + ("after redefinition" in d) * 1)
    best = max(cands, key=rank)
    return str(best.get("Key") or best.get("TableID")), desc(best)


def fetch_use_table(table_id: str, year: str) -> list[dict]:
    res = _call(f"method=GetData&datasetname=InputOutput&TableID={table_id}&Year={year}")
    data = res.get("Data") or []
    if not data:
        raise BeaError(f"TableID={table_id}, Year={year} 데이터 없음")
    return data


def _num(v) -> float:
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


# 최종수요·부가가치 열은 '고객 산업'이 아니다. 개인소비지출·수출·재고증감 등은
# 산업이 아니라 수요 항목이므로 고객 명단에서 빼야 한다.
_NON_INDUSTRY = re.compile(
    r"total|value added|compensation|surplus|taxes|import|export|"
    r"personal consumption|government|gross|inventor|residual|scrap|used",
    re.I)


def downstream_of(data: list[dict], row_code: str, top_n: int = 8) -> list[tuple[str, str, float]]:
    """한 상품(행)을 가로로 읽어 고객 산업을 금액 비중 순으로 낸다.

    돌려주는 값: (산업코드, 산업명, 비중 0~1)
    """
    row_code = str(row_code)
    buckets: dict[tuple[str, str], float] = defaultdict(float)
    for d in data:
        if str(d.get("RowCode", "")).strip() != row_code:
            continue
        col, name = str(d.get("ColCode", "")).strip(), str(d.get("ColDescr", "")).strip()
        if not col or _NON_INDUSTRY.search(name) or _NON_INDUSTRY.search(col):
            continue
        buckets[(col, name)] += _num(d.get("DataValue"))

    total = sum(v for v in buckets.values() if v > 0)
    if total <= 0:
        return []
    ranked = sorted(((c, n, v / total) for (c, n), v in buckets.items() if v > 0),
                    key=lambda x: -x[2])
    return ranked[:top_n]


def available_row_codes(data: list[dict]) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for d in data:
        c = str(d.get("RowCode", "")).strip()
        if c and c not in seen:
            seen[c] = str(d.get("RowDescr", "")).strip()
    return sorted(seen.items())


# NAICS 를 ID 에 담지 않는 총계 시리즈들
_FRED_SECTOR = {
    "IPUTIL": "22",     # 전기·가스 유틸리티
    "IPMINE": "21",     # 광업
    "IPMAN": "31G",     # 제조업 전체
    "IPCONGD": "23",    # 건설
}


def naics_from_fred(series_id: str) -> str:
    """테마가 이미 선언한 FRED 산업 시리즈에서 NAICS 를 뽑는다.

    IPG335S -> 335,  CAPG3344S -> 3344,  IPG3364T9S -> 3364
    테마마다 SIC 크로스워크를 새로 만드는 것보다, 이미 검증해 넣은 시리즈
    ID 를 재사용하는 게 오류가 적다.
    """
    sid = series_id or ""
    if sid in _FRED_SECTOR:
        return _FRED_SECTOR[sid]
    m = re.search(r"(?:IPG|CAPG|CAPUTLG)(\d{3,4})", sid)
    return m.group(1) if m else ""


def match_row_code(codes: list[tuple[str, str]], naics: str) -> tuple[str, str] | None:
    """NAICS 로 BEA 행 코드를 찾는다.

    BEA 요약 코드는 대체로 NAICS 3자리(335, 324…)지만 묶음 코드도 있다
    (31G = 식품·음료·담배, 33DG = 내구재 기타). 정확 일치 → 접두 일치 순으로 본다.
    """
    if not naics:
        return None
    for c, n in codes:
        if c == naics:
            return c, n
    for c, n in codes:
        if naics.startswith(c) and len(c) >= 3:
            return c, n
    for c, n in codes:
        if c.startswith(naics[:3]) and len(naics) >= 3:
            return c, n
    return None
