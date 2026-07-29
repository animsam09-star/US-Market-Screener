"""EIA(미국 에너지정보청) 시계열.

왜 필요한가: 정유·전력은 FRED 의 월간 산업생산으로는 못 본다. 정제가동률과
원유·석유제품 재고는 **주간**으로 나오고 그게 실제로 마진을 움직인다. 그런데
EIA 석유 주간 데이터는 FRED 에 재배포되지 않는다(실측 확인).

API v2 는 무료 키를 요구한다. 키가 없으면 조용히 실패하지 않고 사유를 남긴다.

응답 구조(공식 문서 기준):
    {"response": {"data": [{"period": "2026-07-18", "value": "94.2"}, ...],
                  "frequency": "weekly", "dateFormat": "YYYY-MM-DD"},
     "request": {...}, "apiVersion": "2.1.0"}

레거시 시리즈 ID 라우트(/v2/seriesid/{ID})를 쓴다. 데이터셋마다 다른
facets/data 파라미터를 조립할 필요가 없어 오독 여지가 적다.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from .keys import load_key
from .net import FetchError, fetch_json, purge

BASE = "https://api.eia.gov/v2"


class EiaError(RuntimeError):
    pass


def eia_key() -> str | None:
    return load_key("EIA_API_KEY", "eia_key.txt")


def _parse_period(p: str) -> date | None:
    """주간 YYYY-MM-DD, 월간 YYYY-MM, 연간 YYYY 를 모두 받는다."""
    p = str(p or "").strip()
    for fmt, pad in (("%Y-%m-%d", None), ("%Y-%m", "-01"), ("%Y", "-01-01")):
        try:
            return datetime.strptime(p + (pad or ""), "%Y-%m-%d").date()
        except ValueError:
            continue
    return None


_NON_VALUE = {"period", "seriesId", "series", "units", "unit", "seriesDescription"}


def _pick_value(row: dict) -> float | None:
    """값 열 이름이 데이터셋마다 다르다(value, price, stocks…).

    'value' 를 우선하되, 없으면 숫자로 읽히는 첫 열을 쓴다. 단위·설명 열은
    이름으로 배제한다.
    """
    if "value" in row:
        try:
            return float(row["value"])
        except (TypeError, ValueError):
            return None
    for k, v in row.items():
        if k in _NON_VALUE or k.endswith("-units") or k.endswith("Description"):
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def eia_series(series_id: str) -> list[tuple[date, float]]:
    """EIA 레거시 시리즈 ID로 시계열을 가져온다. 예: PET.WPULEUS3.W"""
    k = eia_key()
    if not k:
        raise EiaError(f"EIA 키 없음 — {series_id} 조회 불가 "
                       "(환경변수 EIA_API_KEY 또는 eia_key.txt)")
    url = (f"{BASE}/seriesid/{series_id}?api_key={k}"
           "&sort[0][column]=period&sort[0][direction]=asc&length=5000")
    try:
        d = fetch_json(url, ttl_hours=12)
    except FetchError as e:
        raise EiaError(f"{series_id} 조회 실패: {e}") from e

    resp = d.get("response") or {}
    rows = resp.get("data") or []
    if not rows:
        # 오류를 200 에 담아 보내는 경우가 있으므로 캐시를 남기지 않는다
        purge(url)
        err = d.get("error") or resp.get("error") or "데이터 없음"
        raise EiaError(f"{series_id}: {str(err)[:120]}")

    out: list[tuple[date, float]] = []
    for r in rows:
        dt = _parse_period(r.get("period"))
        v = _pick_value(r)
        if dt and v is not None:
            out.append((dt, v))
    if not out:
        raise EiaError(f"{series_id}: 값 열을 찾지 못함 (열: {sorted(rows[0])[:8]})")
    out.sort()
    return out


def series_url(series_id: str) -> str:
    """근거 링크. 사람이 볼 수 있는 EIA 페이지로."""
    m = re.match(r"^([A-Z]+)\.(.+?)\.([WMAQ])$", series_id)
    if m:
        return f"https://www.eia.gov/opendata/browser/{m.group(1).lower()}"
    return "https://www.eia.gov/opendata/browser/"
