"""USAspending — 연방 계약 의무액. **키가 필요 없다.**

왜 필요한가: 방산 논지는 "예산이 확정된 다년 계약"인데, 그걸 FRED 의 국방자본재
출하 통계로 재고 있었다. 그건 제조 통계지 계약 통계가 아니다. 실제 계약 데이터가
공개돼 있으므로 그걸 봐야 한다.

Federal Register 는 "규제가 온다"를 말하고, 이 데이터는 "돈이 실제로 움직였다"를
말한다. ⑤ 정책 축에서 전자는 주장, 후자는 확증에 가깝다.

응답 구조(실측):
    {"results": [{"aggregated_amount": 9.02e10,
                  "time_period": {"fiscal_year": "2026", "quarter": "1"}, ...}]}

주의 — 실측으로 확인한 함정:
  * 진행 중인 분기가 0 또는 음수로 나온다(FY2026 Q4 = -11,407). 최신 분기를
    그대로 쓰면 "계약액 급감"으로 오독한다. 반드시 잘라낸다.
  * 연방 회계연도는 10월 시작이다. FY2026 Q1 = 2025년 10~12월.
  * NAICS 필터는 평면 리스트, PSC 는 [["Product","13"]] 형태다(둘 다 실측).
"""
from __future__ import annotations

from datetime import date

from .net import FetchError, fetch_json

URL = "https://api.usaspending.gov/api/v2/search/spending_over_time/"

# 계약(Contract) 유형. 보조금·대출은 뺀다 — 산업 수요와 무관하다.
CONTRACT_TYPES = ["A", "B", "C", "D"]

# 연방 계약은 보고 지연이 크다. 분기 마감 후 이 일수가 지나야 신뢰한다.
LAG_DAYS = 100


class UsaError(RuntimeError):
    pass


def _fq_to_date(fy: int, q: int) -> date:
    """회계분기 -> 그 분기의 마지막 날(달력 기준).

    FY Q1 = 전년 10~12월,  Q2 = 1~3월,  Q3 = 4~6월,  Q4 = 7~9월
    """
    if q == 1:
        return date(fy - 1, 12, 31)
    return {2: date(fy, 3, 31), 3: date(fy, 6, 30), 4: date(fy, 9, 30)}[q]


def contract_obligations(agency: str, *, naics: list[str] | None = None,
                         psc: list[str] | None = None,
                         years: int = 8) -> list[tuple[date, float]]:
    """분기별 계약 의무액. 진행 중인 분기는 잘라낸다."""
    today = date.today()
    filters: dict = {
        "time_period": [{"start_date": f"{today.year - years}-01-01",
                         "end_date": today.isoformat()}],
        "award_type_codes": CONTRACT_TYPES,
        "agencies": [{"type": "awarding", "tier": "toptier", "name": agency}],
    }
    if naics:
        filters["naics_codes"] = list(naics)
    if psc:
        filters["psc_codes"] = {"require": [["Product", p] for p in psc]}

    try:
        d = fetch_json(URL, json_body={"group": "quarter", "filters": filters},
                       ttl_hours=24, timeout=45)
    except FetchError as e:
        raise UsaError(f"조회 실패: {e}") from e

    rows = d.get("results") or []
    if not rows:
        raise UsaError(f"{agency}: 결과 없음 (필터가 너무 좁을 수 있음)")

    out: list[tuple[date, float]] = []
    for r in rows:
        tp = r.get("time_period") or {}
        try:
            fy, q = int(tp["fiscal_year"]), int(tp["quarter"])
            amt = float(r.get("aggregated_amount") or 0.0)
        except (KeyError, TypeError, ValueError):
            continue
        out.append((_fq_to_date(fy, q), amt))
    out.sort()

    # 미완 분기 제거 — 크기 휴리스틱이 아니라 날짜로 자른다.
    # 연방 계약은 보고 지연이 1~3개월이라, 분기가 끝났어도 한동안 계속 채워진다.
    # 실측: 오늘이 7/29 인데 6/30 마감 분기가 42B(직전 분기들은 90~178B)였다.
    # 크기로 판정하면 '급감'과 '집계 미완'을 구별할 수 없다.
    cutoff = today.toordinal() - LAG_DAYS
    out = [(d, v) for d, v in out if d.toordinal() <= cutoff]

    if len(out) < 8:
        raise UsaError(f"{agency}: 유효 분기 부족({len(out)}개, 보고지연 {LAG_DAYS}일 제외 후)")
    return out


def ttm(series: list[tuple[date, float]]) -> list[tuple[date, float]]:
    """4분기 이동합.

    연방 계약은 회계연도 말(9월)에 몰리는 계절성이 크다 — 분기 단독으로는
    178B/90B/131B 처럼 요동쳐 추세를 읽을 수 없다.
    """
    out = []
    for i in range(3, len(series)):
        out.append((series[i][0], sum(v for _, v in series[i - 3:i + 1])))
    return out


def evidence_url(agency: str) -> str:
    return "https://www.usaspending.gov/search"
