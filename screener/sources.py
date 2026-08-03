"""데이터 소스 어댑터 — 전부 무료·무키.

FRED CSV      : 거시·산업 시계열 (가동률, 산업생산, 신규수주, 재고, PPI)
SEC XBRL      : 기업 재무 (매출, capex, D&A, 재고, PP&E, 부채, 주식수)
SEC 전문검색   : 10-K/10-Q 키워드 확산 (신기술 축)
Yahoo Finance : 주가
Federal Register : 규제 시행 (정책 축)
"""
from __future__ import annotations

import io
import re
import statistics
import urllib.parse
import zipfile
from pathlib import Path
from datetime import date, datetime, timedelta

from .net import FetchError, fetch, fetch_json, fetch_text

# ---------------------------------------------------------------- FRED

_FRED_TTL = 24 * 7  # 월간 시계열이라 주 단위 캐시로 충분


_FRED_SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "fred_snapshot.json"
_fred_snap: dict | None = None
_fred_snap_used: set[str] = set()


def _fred_from_snapshot(series_id: str) -> list[tuple[date, float]] | None:
    """동봉 스냅샷 폴백.

    러너는 캐시가 안 쌓여 매 실행 FRED 를 버스트로 받다가 일시 차단당한다
    (run 39~43 실측, 재시도 정책도 소용없음). FRED 는 월간이라 며칠 낡아도
    신호가 안 바뀐다 — SEC 재무 스냅샷과 같은 논리다. export_fred.py 로 갱신.
    """
    global _fred_snap
    if _fred_snap is None:
        if _FRED_SNAPSHOT.exists():
            import json as _json
            _fred_snap = _json.loads(_FRED_SNAPSHOT.read_text(encoding="utf-8"))
        else:
            _fred_snap = {}
    rows = (_fred_snap.get("series") or {}).get(series_id)
    if not rows:
        return None
    if series_id not in _fred_snap_used:
        _fred_snap_used.add(series_id)
        print(f"[주의] FRED {series_id} 실시간 실패 — 동봉 스냅샷 사용"
              f"({_fred_snap.get('generated', '?')} 기준)")
    return [(datetime.strptime(d, "%Y-%m-%d").date(), float(v)) for d, v in rows]


def fred_series(series_id: str) -> list[tuple[date, float]]:
    """FRED 시계열. API 키 없이 graph CSV 엔드포인트를 쓴다.

    실시간이 우선이고, 실패하면 동봉 스냅샷으로 폴백한다.
    """
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={urllib.parse.quote(series_id)}"
    try:
        raw = fetch(url, ttl_hours=_FRED_TTL)
    except FetchError:
        snap = _fred_from_snapshot(series_id)
        if snap is not None:
            return snap
        raise
    if raw[:2] == b"PK":  # FRED 가 가끔 zip 으로 준다
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise FetchError(f"FRED {series_id}: zip 안에 csv 없음")
        text = z.read(names[0]).decode("utf-8", "replace")
    else:
        text = raw.decode("utf-8", "replace")

    lines = [l for l in text.strip().split("\n") if l.strip()]
    if not lines or "<" in lines[0]:
        raise FetchError(f"FRED {series_id}: 시리즈 없음")
    out: list[tuple[date, float]] = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            d = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
            v = float(parts[1].strip())
        except ValueError:
            continue  # 결측은 "."
        out.append((d, v))
    if not out:
        raise FetchError(f"FRED {series_id}: 관측치 0")
    return out


# ---------------------------------------------------------------- SEC

_SEC_TTL = 24 * 3

# 태그는 회사마다 다르게 쓴다. 우선순위대로 시도한다.
TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
    "ebit": ["OperatingIncomeLoss"],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquirePropertyPlantAndEquipmentExcludingCapitalizedInterest",
    ],
    "dep": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    "inventory": ["InventoryNet"],
    "ppe_gross": ["PropertyPlantAndEquipmentGross"],
    "accum_dep": ["AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment"],
    "ppe_net": ["PropertyPlantAndEquipmentNet"],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "debt": ["LongTermDebt", "LongTermDebtNoncurrent", "DebtLongtermAndShorttermCombinedAmount"],
    "shares": ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"],
}


_VENDORED_TICKERS = Path(__file__).resolve().parent.parent / "data" / "ticker_cik.json"
_VENDORED_NAMES = Path(__file__).resolve().parent.parent / "data" / "ticker_name.json"
_names_cache: dict | None = None


def ticker_names() -> dict[str, str]:
    """티커 -> 회사명. 티커만 보고는 무슨 회사인지 알 수 없다."""
    global _names_cache
    if _names_cache is None:
        if _VENDORED_NAMES.exists():
            import json as _json
            _names_cache = _json.loads(_VENDORED_NAMES.read_text(encoding="utf-8"))
        else:
            _names_cache = {}
    return _names_cache


def sec_ticker_map() -> dict[str, int]:
    """티커 -> CIK.

    SEC 는 데이터센터 IP(GitHub Actions 러너 등)에 403 을 내는 일이 있다.
    이 매핑은 거의 변하지 않는데도 실패하면 실행 전체가 죽었다. 그래서
    저장소에 사본을 동봉하고, 원격 조회는 갱신 시도로만 쓴다.
    """
    try:
        d = fetch_json("https://www.sec.gov/files/company_tickers.json", ttl_hours=24 * 14)
        remote = {v["ticker"].upper(): int(v["cik_str"]) for v in d.values()}
        if len(remote) > 1000:
            return remote
    except Exception:
        pass

    if _VENDORED_TICKERS.exists():
        import json as _json
        m = _json.loads(_VENDORED_TICKERS.read_text(encoding="utf-8"))
        print(f"[주의] SEC 티커 목록 조회 실패 — 동봉 사본 사용 ({len(m):,}개, "
              f"{_VENDORED_TICKERS.name})")
        return {k.upper(): int(v) for k, v in m.items()}
    raise FetchError("티커→CIK 매핑을 원격에서도 동봉 사본에서도 얻지 못함")


# 그룹 재무 집계에 쓰는 개념들. 스냅샷도 이 목록으로 뽑는다.
CONCEPTS = ("revenue", "ebit", "capex", "dep", "inventory",
            "ppe_gross", "accum_dep", "ppe_net", "cash", "debt", "shares")

_SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "financials.json"
_snap_cache: dict | None = None


def financials_snapshot() -> dict:
    """사내 PC 에서 뽑아 동봉한 재무 스냅샷.

    SEC 재무는 분기에 한 번 바뀐다. 매일 원격에서 받을 이유가 없고, SEC 는
    데이터센터 IP 를 막는다. export_financials.py 로 갱신한다.
    """
    global _snap_cache
    if _snap_cache is None:
        if _SNAPSHOT.exists():
            import json as _json
            _snap_cache = _json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
        else:
            _snap_cache = {}
    return _snap_cache


def snapshot_quarterly(ticker: str, concept: str) -> dict[tuple[int, int], float]:
    """스냅샷에서 분기 시계열을 꺼낸다. 없으면 빈 dict."""
    co = (financials_snapshot().get("companies") or {}).get(ticker.upper()) or {}
    out: dict[tuple[int, int], float] = {}
    for k, v in (co.get(concept) or {}).items():
        try:
            y, q = k.split("Q")
            out[(int(y), int(q))] = float(v)
        except (ValueError, AttributeError):
            continue
    return out


def sec_company_facts(cik: int) -> dict:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    return fetch_json(url, ttl_hours=_SEC_TTL)


_FRAME_RE = re.compile(r"^CY(\d{4})(?:Q([1-4]))?(I?)$")


def _frame_key(frame: str) -> tuple[int, int] | None:
    """'CY2024Q3' -> (2024, 3), 'CY2024' -> (2024, 4는 아님) 연간은 별도 처리."""
    m = _FRAME_RE.match(frame or "")
    if not m:
        return None
    yr, q, _inst = m.group(1), m.group(2), m.group(3)
    if q is None:
        return None  # 연간 프레임은 분기 시계열에 섞지 않는다
    return int(yr), int(q)


STOCK_CONCEPTS = {"inventory", "ppe_gross", "accum_dep", "ppe_net", "cash", "debt", "shares"}


def _quarter_of(d: str) -> tuple[int, int] | None:
    """마감일 → 분기. 마감일에서 10일을 빼고 매긴다 — 4-4-5 회계달력 기업
    (LHX 등)은 분기말이 7/4·1/2 처럼 다음 달 초로 넘어가는데, 달력 월 그대로
    매기면 Q2가 Q3, Q4가 이듬해 Q1이 되어 TTM 이 오염된다(방산 실측)."""
    try:
        dt = datetime.strptime(d, "%Y-%m-%d").date() - timedelta(days=10)
    except (ValueError, TypeError):
        return None
    return dt.year, (dt.month - 1) // 3 + 1


def xbrl_periods(facts: dict, concept: str) -> list[list[tuple]]:
    """태그별 원시 기간 목록 [(start, end, filed, val), …] — 태그 폴백 순서 유지.

    백테스트가 스냅샷마다 수 MB 짜리 facts JSON 을 재파싱하면 몇 시간이 된다.
    파싱은 여기서 티커당 한 번만 하고, 시점 컷·분기 복원은
    quarterly_from_periods 가 이 경량 구조 위에서 반복한다.
    """
    is_stock = concept in STOCK_CONCEPTS
    out: list[list[tuple]] = []
    for tag in TAGS.get(concept, [concept]):
        rows: list[tuple] = []
        for ns in ("us-gaap", "dei", "ifrs-full"):
            for unit, entries in (facts.get("facts", {}).get(ns, {})
                                  .get(tag, {}).get("units", {}).items()):
                if unit not in ("USD", "shares"):
                    continue
                for e in entries:
                    end = e.get("end")
                    if not end:
                        continue
                    start = e.get("start")
                    if is_stock and start:
                        continue              # 저량인데 기간이 있으면 다른 개념
                    if not is_stock and not start:
                        continue
                    try:
                        rows.append((start or "", end, e.get("filed", ""),
                                     float(e["val"])))
                    except (TypeError, ValueError):
                        continue
        if rows:
            out.append(rows)
    return out


def quarterly_from_periods(tag_lists: list[list[tuple]], concept: str,
                           asof: str | None = None) -> dict[tuple[int, int], float]:
    """원시 기간 목록 → 분기 시계열. asof 는 접수일(filed) 컷.

    태그는 '첫 번째로 결과가 나온 것'이 아니라 **가장 최신이고 긴 것**을
    고른다 — LMT 는 옛 태그에 2017~19년 7건이 남아 있어 그게 먼저 걸리면
    38분기짜리 진짜 태그(Revenues)가 통째로 가려졌다(방산 실측).
    """
    is_stock = concept in STOCK_CONCEPTS
    best: dict[tuple[int, int], float] = {}
    for rows in tag_lists:
        # (start, end) -> val, 수정 공시는 (asof 이내에서) 가장 최근 접수분 채택
        periods: dict[tuple[str, str], tuple[str, float]] = {}
        for start, end, filed, val in rows:
            if asof is not None and (not filed or filed > asof):
                continue      # 그 시점엔 아직 접수 전 — 미래 정보
            key = (start, end)
            prev = periods.get(key)
            if prev is None or filed >= prev[0]:
                periods[key] = (filed, val)
        if not periods:
            continue

        if is_stock:
            out: dict[tuple[int, int], float] = {}
            for (_, end), (_, v) in sorted(periods.items(), key=lambda x: x[0][1]):
                k = _quarter_of(end)
                if k:
                    out[k] = v
            if out and (not best or (max(out), len(out)) > (max(best), len(best))):
                best = out
            continue

        # 유량: 미국 기업은 누적(YTD)으로 보고한다. 같은 start 를 공유하는 기간들을
        # end 순으로 차분해 개별 분기를 복원한다. Q2 = H1 − Q1, Q3 = 9M − H1 ...
        by_start: dict[str, list[tuple[str, float]]] = {}
        for (start, end), (_, v) in periods.items():
            by_start.setdefault(start, []).append((end, v))

        cand: dict[tuple[int, int], list[float]] = {}
        for start, items in by_start.items():
            items.sort()
            prev_end, prev_val = start, 0.0
            for end, val in items:
                try:
                    days = (datetime.strptime(end, "%Y-%m-%d")
                            - datetime.strptime(prev_end, "%Y-%m-%d")).days
                except ValueError:
                    continue
                if 80 <= days <= 100:          # 직전 구간과의 차이가 딱 한 분기
                    k = _quarter_of(end)
                    if k:
                        cand.setdefault(k, []).append(val - prev_val)
                prev_end, prev_val = end, val
        discrete = _repair_annual_in_quarter(_resolve_quarters(cand))
        if discrete and (not best
                         or (max(discrete), len(discrete)) > (max(best), len(best))):
            best = discrete
    return best


def _repair_annual_in_quarter(q: dict) -> dict:
    """연간 누적값이 분기 하나에 통째로 태깅된 공시를 복원한다.

    LHX 실측: (start 10/4, end 1/2, 90일) 기간에 연간값 21.86B 가 태깅돼
    분기 시계열에 그대로 박혔고 TTM·YoY(+83%)가 전부 틀어졌다. 경쟁 후보가
    없어 중앙값 판정도 못 잡는다. 앞 3개 분기가 있으면 '의심값 − 앞 3분기 합'
    으로 진짜 분기를 복원하고, 복원 불가면 버린다(오염보다 구멍이 낫다).
    """
    if len(q) < 6:
        return q
    vals = sorted(abs(v) for v in q.values())
    med = vals[len(vals) // 2]
    if med <= 0:
        return q

    def back(k, n):
        idx = k[0] * 4 + (k[1] - 1) - n
        return idx // 4, idx % 4 + 1

    out = dict(q)
    for k in sorted(q):
        v = q[k]
        if abs(v) <= 2.5 * med:
            continue
        prevs = [out.get(back(k, i)) for i in (1, 2, 3)]
        if all(p is not None and abs(p) <= 2.5 * med for p in prevs):
            fixed = v - sum(prevs)
            if 0.3 * med <= abs(fixed) <= 2.5 * med:
                out[k] = fixed
                continue
        del out[k]
    return out


def _resolve_quarters(cand: dict) -> dict:
    """같은 분기에 서로 다른 값이 오면 이웃 분기 중앙값에 가까운 쪽을 택한다.

    LHX 실측: 연간값(21.86B)을 분기 기간(90일 span)으로 태깅한 공시가 있어
    진짜 분기값(5.66B)과 경쟁했다. '먼저 온 것 승리'는 순서 운에 좌우된다 —
    후보가 2.5배 넘게 벌어지면 정상 분기들의 중앙값으로 판정한다.
    """
    uni = [vs[0] for vs in cand.values() if len(vs) == 1]
    med = statistics.median(uni) if uni else None
    out: dict = {}
    for k, vs in cand.items():
        lo = min(abs(x) for x in vs)
        if len(vs) == 1 or max(abs(x) for x in vs) <= 2.5 * max(lo, 1e-9):
            out[k] = vs[0]
        elif med is not None:
            out[k] = min(vs, key=lambda x: abs(x - med))
        else:
            out[k] = min(vs, key=abs)
    return out


def xbrl_quarterly(facts: dict, concept: str,
                   asof: str | None = None) -> dict[tuple[int, int], float]:
    """companyfacts 에서 분기 시계열을 뽑는다.

    SEC 의 'frame' 필드만 쓰면 안 된다 — SEC 는 프레임을 일부 사실에만 붙인다
    (한 기업의 capex 127건 중 31건). 프레임만 쓰면 기업마다 채워진 분기가
    달라져, 그룹 합계에서 '60% 이상 보고' 교집합이 거의 남지 않는다.

    따라서 start/end 날짜에서 직접 분기를 유도한다.
      유량(매출·capex·감가상각) : 기간 길이 80~100일인 항목 = 분기
      저량(재고·PP&E·주식수)     : end 시점만 있는 항목 = 그 분기 말 잔액
    같은 분기에 값이 여러 번 나오면(수정 공시) 가장 최근 접수분을 쓴다.

    asof('YYYY-MM-DD') 를 주면 **그 날짜까지 접수(filed)된 공시만** 쓴다 —
    백테스트의 미래 정보 누출 방지 컷. filed 가 없는 항목은 언제 알 수 있었는지
    모르므로 보수적으로 버린다.
    """
    return quarterly_from_periods(xbrl_periods(facts, concept), concept, asof)


def edgar_fts(phrase: str, *, forms: str = "10-K,10-Q",
              start: str | None = None, end: str | None = None) -> dict:
    """10-K/10-Q 전문검색.

    건수(hits)뿐 아니라 entity_filter/sic_filter 집계를 함께 돌려준다.
    건수는 한 회사가 열 번 말해도 늘어난다 — 확산의 정직한 척도는 '기업 수'이고,
    'SIC 집중도'는 버즈워드와 실제 산업 채택을 가른다.

    주의: SEC 는 집계 버킷을 30개로 잘라서 준다. 따라서 기업 수는 30에서
    검열(censored)되며, 그 이상은 '30+' 로만 알 수 있다.
    """
    q = urllib.parse.quote(f'"{phrase}"')
    url = f"https://efts.sec.gov/LATEST/search-index?q={q}&forms={urllib.parse.quote(forms)}"
    if start and end:
        url += f"&dateRange=custom&startdt={start}&enddt={end}"
    try:
        d = fetch_json(url, ttl_hours=24 * 7)
    except FetchError:
        return {"hits": 0, "entities": [], "sic": [], "censored": False}

    agg = d.get("aggregations") or {}
    ents = [b.get("key", "") for b in (agg.get("entity_filter") or {}).get("buckets", [])]
    sic = [(b.get("key", ""), int(b.get("doc_count", 0)))
           for b in (agg.get("sic_filter") or {}).get("buckets", [])]
    return {
        "hits": int(d.get("hits", {}).get("total", {}).get("value", 0) or 0),
        "entities": ents,
        "sic": sic,
        "censored": len(ents) >= 30,
    }


def edgar_fts_count(phrase: str, **kw) -> int:
    return edgar_fts(phrase, **kw)["hits"]


def sec_sic(cik: int) -> tuple[str, str]:
    """기업의 SIC 코드와 설명. 고객군 자동 지정의 출발점."""
    try:
        d = fetch_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", ttl_hours=24 * 14)
    except FetchError:
        return "", ""
    return str(d.get("sic") or ""), str(d.get("sicDescription") or "")


# ---------------------------------------------------------------- 주가

def epoch_date(ts: float) -> date:
    """유닉스 초 → 날짜. Windows 의 utcfromtimestamp 는 음수(1970년 이전)에서
    OSError 를 낸다 — Yahoo 'max' 구간의 옛 상장 종목(CAT 등)이 그렇다."""
    return (datetime(1970, 1, 1) + timedelta(seconds=ts)).date()


def looks_daily(series: list) -> bool:
    """일간 시계열인지 검사. Yahoo 는 range=max 에서 interval=1d 를 조용히
    무시하고 월간을 줬다 — 그걸 일간으로 해석하면 '252일 전'이 21년 전이 되고
    백테스트 전방수익률이 전부 죽는다. 조용한 오염이라 게이트가 필요하다."""
    if len(series) < 30:
        return True                    # 짧으면 판단 유보 (신규 상장)
    span = (series[-1][0] - series[0][0]).days
    return span / (len(series) - 1) <= 5.0


def _yahoo(ticker: str, rng: str) -> list[tuple[date, float]]:
    base = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}"
    if rng == "max":
        # range=max 는 interval=1d 를 조용히 무시하고 월간을 준다(실측: SPY 402개).
        # period1/period2 명시 방식은 일간 전체 이력을 준다(SPY 8,433개).
        # p2 는 자정 기준으로 고정 — 초 단위로 바뀌면 캐시 키가 매번 달라져
        # 실행마다 전 종목을 다시 받는다
        p2 = int((datetime.combine(date.today(), datetime.min.time())
                  - datetime(1970, 1, 1)).total_seconds()) + 86400
        url = f"{base}?period1=315532800&period2={p2}&interval=1d"
    else:
        url = f"{base}?range={rng}&interval=1d"
    d = fetch_json(url, ttl_hours=12)
    res = (d.get("chart") or {}).get("result")
    if not res:
        raise FetchError(f"{ticker}: 주가 없음")
    r = res[0]
    ts = r.get("timestamp") or []
    adj = ((r.get("indicators", {}).get("adjclose") or [{}])[0]).get("adjclose") or []
    out = [(epoch_date(t), float(c)) for t, c in zip(ts, adj) if c is not None]
    if not out:
        raise FetchError(f"{ticker}: 종가 전부 결측")
    if not looks_daily(out):
        raise FetchError(f"{ticker}: 일간이 아닌 시계열({len(out)}개) — 해상도 오염")
    return out


def _stooq(ticker: str) -> list[tuple[date, float]]:
    """Yahoo 폴백. Stooq 는 키가 필요 없고 클라우드 IP 를 덜 가린다."""
    url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(ticker.lower())}.us&i=d"
    txt = fetch(url, ttl_hours=12).decode("utf-8", "replace")
    lines = [l for l in txt.strip().split("\n") if l]
    if len(lines) < 2 or not lines[0].lower().startswith("date"):
        raise FetchError(f"{ticker}: Stooq 응답이 CSV 가 아님")
    out = []
    for line in lines[1:]:
        p = line.split(",")
        if len(p) < 5:
            continue
        try:
            out.append((datetime.strptime(p[0], "%Y-%m-%d").date(), float(p[4])))
        except ValueError:
            continue
    if not out:
        raise FetchError(f"{ticker}: Stooq 종가 없음")
    return out


def yahoo_prices(ticker: str, rng: str = "5y") -> list[tuple[date, float]]:
    """주가. Yahoo 우선, 실패하면 Stooq.

    Yahoo 는 클라우드 IP(GitHub Actions 러너 등)를 차단하는 일이 잦다.
    그러면 미반영 축 4개 중 2개(주가 미반응·고점 대비 눌림)가 통째로 죽는데,
    로컬에서는 멀쩡해서 눈치채기 어렵다. 그래서 폴백을 둔다.
    """
    try:
        return _yahoo(ticker, rng)
    except FetchError:
        return _stooq(ticker)


# ---------------------------------------------------------------- 정책

_FR = "https://www.federalregister.gov/api/v1/documents.json"


def fedreg_signal(terms: list[str], agencies: list[str] | None = None) -> dict:
    """정책 강제수요 신호.

    설계 초안은 '시행일이 미래인 최종규칙'만 셌으나 실측에서 무너졌다. 미국
    최종규칙은 공표 후 보통 30~60일이면 발효되므로, 어느 시점에나 '시행 예정'
    상태인 규칙이 거의 없다(한 테마 227건 중 1건). 12~24개월 선행 신호는
    최종규칙이 아니라 **입안예고(PRORULE)** 단계에 있다.

    또 하나: 전문검색은 일상 행정문서를 대량으로 긁는다(항공 '감항성 지침'
    243건). 그래서 **significant**(경제영향 1억달러 이상)로만 센다. 이 플래그가
    정책 명령과 정기 공지를 가르는 유일한 구조적 구분자다.

    agencies 는 게이트가 아니라 가중치다 — 소관기관이 일치하면 신뢰도가 높지만,
    기관 필터를 검색어와 AND 로 걸면 결과가 0이 된다(실측 확인).
    """
    if not terms:
        return {}
    today = date.today()
    year_ago = (today - timedelta(days=365)).isoformat()
    q = urllib.parse.quote(" OR ".join(f'"{t}"' for t in terms))
    fields = ("&fields[]=title&fields[]=effective_on&fields[]=significant"
              "&fields[]=publication_date&fields[]=agencies&fields[]=html_url&fields[]=type")

    def pull(extra: str) -> tuple[int, list[dict]]:
        try:
            d = fetch_json(f"{_FR}?per_page=20&order=newest&conditions[term]={q}"
                           f"&conditions[significant]=1{extra}{fields}", ttl_hours=24 * 3)
        except FetchError:
            return 0, []
        return int(d.get("count", 0) or 0), (d.get("results") or [])

    n_rule, r_rule = pull("&conditions[type][]=RULE"
                          f"&conditions[effective_date][gte]={today.isoformat()}")
    n_pro, r_pro = pull("&conditions[type][]=PRORULE"
                        f"&conditions[publication_date][gte]={year_ago}")

    ag = {a.lower() for a in (agencies or [])}
    items = []
    for it in r_rule + r_pro:
        names = {str(a.get("slug", "")).lower() for a in (it.get("agencies") or [])}
        eff = it.get("effective_on")
        months_out = None
        if eff:
            try:
                months_out = (datetime.strptime(eff, "%Y-%m-%d").date() - today).days / 30.44
            except ValueError:
                pass
        items.append({
            "title": (it.get("title") or "")[:160],
            "type": it.get("type", ""),
            "effective_on": eff,
            "months_out": months_out,
            "agency_match": bool(ag & names),
            "url": it.get("html_url", ""),
        })
    return {"n_rule": n_rule, "n_proposed": n_pro, "items": items,
            "n_agency_match": sum(1 for i in items if i["agency_match"])}
