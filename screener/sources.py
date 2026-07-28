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
import urllib.parse
import zipfile
from pathlib import Path
from datetime import date, datetime, timedelta

from .net import FetchError, fetch, fetch_json, fetch_text

# ---------------------------------------------------------------- FRED

_FRED_TTL = 24 * 7  # 월간 시계열이라 주 단위 캐시로 충분


def fred_series(series_id: str) -> list[tuple[date, float]]:
    """FRED 시계열. API 키 없이 graph CSV 엔드포인트를 쓴다."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={urllib.parse.quote(series_id)}"
    raw = fetch(url, ttl_hours=_FRED_TTL)
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
    try:
        dt = datetime.strptime(d, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return dt.year, (dt.month - 1) // 3 + 1


def xbrl_quarterly(facts: dict, concept: str) -> dict[tuple[int, int], float]:
    """companyfacts 에서 분기 시계열을 뽑는다.

    SEC 의 'frame' 필드만 쓰면 안 된다 — SEC 는 프레임을 일부 사실에만 붙인다
    (한 기업의 capex 127건 중 31건). 프레임만 쓰면 기업마다 채워진 분기가
    달라져, 그룹 합계에서 '60% 이상 보고' 교집합이 거의 남지 않는다.

    따라서 start/end 날짜에서 직접 분기를 유도한다.
      유량(매출·capex·감가상각) : 기간 길이 80~100일인 항목 = 분기
      저량(재고·PP&E·주식수)     : end 시점만 있는 항목 = 그 분기 말 잔액
    같은 분기에 값이 여러 번 나오면(수정 공시) 가장 최근 접수분을 쓴다.
    """
    is_stock = concept in STOCK_CONCEPTS

    for tag in TAGS.get(concept, [concept]):
        # (start, end) -> val, 수정 공시는 가장 최근 접수분 채택
        periods: dict[tuple[str, str], tuple[str, float]] = {}
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
                    key = (start or "", end)
                    filed = e.get("filed", "")
                    prev = periods.get(key)
                    if prev is None or filed >= prev[0]:
                        periods[key] = (filed, float(e["val"]))
        if not periods:
            continue

        if is_stock:
            out: dict[tuple[int, int], float] = {}
            for (_, end), (_, v) in sorted(periods.items(), key=lambda x: x[0][1]):
                k = _quarter_of(end)
                if k:
                    out[k] = v
            return out

        # 유량: 미국 기업은 누적(YTD)으로 보고한다. 같은 start 를 공유하는 기간들을
        # end 순으로 차분해 개별 분기를 복원한다. Q2 = H1 − Q1, Q3 = 9M − H1 ...
        by_start: dict[str, list[tuple[str, float]]] = {}
        for (start, end), (_, v) in periods.items():
            by_start.setdefault(start, []).append((end, v))

        discrete: dict[tuple[int, int], float] = {}
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
                        discrete.setdefault(k, val - prev_val)
                prev_end, prev_val = end, val
        if discrete:
            return discrete
    return {}


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

def _yahoo(ticker: str, rng: str) -> list[tuple[date, float]]:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}"
           f"?range={rng}&interval=1d")
    d = fetch_json(url, ttl_hours=12)
    res = (d.get("chart") or {}).get("result")
    if not res:
        raise FetchError(f"{ticker}: 주가 없음")
    r = res[0]
    ts = r.get("timestamp") or []
    adj = ((r.get("indicators", {}).get("adjclose") or [{}])[0]).get("adjclose") or []
    out = [(datetime.utcfromtimestamp(t).date(), float(c))
           for t, c in zip(ts, adj) if c is not None]
    if not out:
        raise FetchError(f"{ticker}: 종가 전부 결측")
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
