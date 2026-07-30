"""회귀 테스트 — 실제로 겪은 사고를 하나씩 고정한다.

    python tests/run_tests.py

규칙: 판별 로직을 고치면 이 스위트를 돌려 전부 PASS 를 확인한다. 새로 발견한
오류는 **고치기 전에** 여기 케이스를 먼저 추가한다. 각 테스트 이름 옆의 설명은
"무엇이 잘못됐었나"이지 "무엇을 검사하나"가 아니다 — 그래야 나중에 이 제약이
왜 있는지 알 수 있다.

네트워크를 쓰지 않는다. 전부 합성 데이터다.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))


# ---------------------------------------------------------------- F1
def f1_ytd_differencing():
    """미국 기업은 분기가 아니라 누적(YTD)으로 보고한다.

    사고: '3개월 구간'만 받았더니 Q1 만 잡혔다(Duke 매출 1건). capex 가
    15건밖에 안 나와 낙수·캐펙스 축이 통째로 죽어 있었다.
    """
    from screener.sources import xbrl_quarterly

    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"start": "2024-01-01", "end": "2024-03-31", "val": 100, "filed": "2024-04-30"},
        {"start": "2024-01-01", "end": "2024-06-30", "val": 250, "filed": "2024-07-30"},
        {"start": "2024-01-01", "end": "2024-09-30", "val": 420, "filed": "2024-10-30"},
        {"start": "2024-01-01", "end": "2024-12-31", "val": 600, "filed": "2025-02-28"},
    ]}}}}}
    q = xbrl_quarterly(facts, "revenue")
    check("F1 YTD→분기 복원: 4개 분기 전부", len(q) == 4, f"실제 {len(q)}개")
    check("F1 Q2 = H1 − Q1 = 150", q.get((2024, 2)) == 150, f"{q.get((2024, 2))}")
    check("F1 Q4 = FY − 9M = 180", q.get((2024, 4)) == 180, f"{q.get((2024, 4))}")


# ---------------------------------------------------------------- F2
def f2_no_economy_wide_fallback():
    """전 제조업 총계로 폴백하면 모든 테마가 같은 점수를 받는다.

    사고: ⑧⑨축이 ISRATIO/AMTMUO 로 폴백해 8개 테마 전부가 재고 1.28,
    잔고 2.42 를 받았고, 최강2축 방식이라 촉매 점수가 모두 80 으로 같아졌다.
    """
    from screener.axes import a8_inventory, a9_bottleneck

    def boom(_):
        raise AssertionError("산업 시리즈 미지정인데 네트워크를 호출했다")

    s8 = a8_inventory({}, boom)
    s9 = a9_bottleneck({}, boom)
    check("F2 재고축: 시리즈 미지정이면 nodata", s8.status == "nodata", s8.status)
    check("F2 병목축: 시리즈 미지정이면 nodata", s9.status == "nodata", s9.status)
    check("F2 사유를 남긴다", "미지정" in s8.reason, s8.reason[:40])


# ---------------------------------------------------------------- F3
def f3_bea_result_shapes():
    """BEA 는 메서드마다 Results 모양이 다르다.

    사고: GetParameterValues 는 dict, GetData 는 list 로 주는데 둘 다 dict 로
    가정해 'list' object has no attribute 'get' 로 죽었다.
    """
    from screener.bea import _collect, _find_error

    d = {"ParamValue": [{"Key": "259", "Desc": "Use ... Summary"}]}
    l = [{"Statistic": "Use", "Data": [{"RowCode": "335", "ColCode": "22"}]}]
    check("F3 dict 모양 파싱", len(_collect(d, "ParamValue")) == 1)
    check("F3 list 모양 파싱", len(_collect(l, "Data")) == 1)
    check("F3 list 안의 Error 탐지",
          _find_error([{"Error": {"APIErrorDescription": "x"}}]) is not None)
    check("F3 정상 응답은 Error 없음", _find_error(l) is None)


# ---------------------------------------------------------------- F4
def f4_bea_final_demand_excluded():
    """최종수요는 '고객 산업'이 아니다.

    사고: F02E(설비투자)가 한 테마에서 60% 를 차지하며 1위 고객으로 올라왔다.
    이름 필터로는 안 걸려서 코드(F로 시작)로 잘라내야 했다.
    """
    from screener.bea import downstream_of

    data = [{"RowCode": "335", "ColCode": "F02E", "ColDescr": "Nonresidential fixed investment", "DataValue": "1000"},
            {"RowCode": "335", "ColCode": "F02R", "ColDescr": "Residential fixed investment", "DataValue": "500"},
            {"RowCode": "335", "ColCode": "23", "ColDescr": "Construction", "DataValue": "300"},
            {"RowCode": "335", "ColCode": "333", "ColDescr": "Machinery", "DataValue": "100"}]
    r = downstream_of(data, "335")
    codes = [c for c, _, _ in r]
    check("F4 F02E 제외", "F02E" not in codes, str(codes))
    check("F4 F02R 제외", "F02R" not in codes, str(codes))
    check("F4 실제 산업만 남음", codes == ["23", "333"], str(codes))
    check("F4 비중은 남은 것끼리 재계산", abs(r[0][2] - 0.75) < 1e-6, f"{r[0][2]:.3f}")


# ---------------------------------------------------------------- F5
def f5_naics_matching_direction():
    """접두 비교 방향을 반대로 짜면 항공기가 자동차가 된다.

    사고: NAICS 3364(항공기)가 BEA 3361MV(자동차)로 매칭됐다.
    """
    from screener.bea import match_row_code, naics_from_fred

    codes = [("22", "Utilities"), ("333", "Machinery"), ("334", "Computer"),
             ("335", "Electrical"), ("3361MV", "Motor vehicles"),
             ("3364OT", "Other transportation equipment")]
    check("F5 3364 → 3364OT (자동차 아님)", match_row_code(codes, "3364")[0] == "3364OT",
          str(match_row_code(codes, "3364")))
    check("F5 3344 → 334", match_row_code(codes, "3344")[0] == "334")
    check("F5 335 정확일치", match_row_code(codes, "335")[0] == "335")
    check("F5 IPUTIL → 22 (코드가 이름에 없는 총계)", naics_from_fred("IPUTIL") == "22")
    check("F5 IPG3364T9S → 3364", naics_from_fred("IPG3364T9S") == "3364")


# ---------------------------------------------------------------- F6
def f6_circuit_breaker():
    """차단된 호스트에 계속 타임아웃을 먹으면 실행이 몇 시간짜리가 된다.

    사고: 러너에서 스크리너 실행이 4분을 넘겨 계속 돌았다. 로컬은 5초다.
    """
    import screener.net as N

    N._dead.clear()
    N._fail_streak.clear()
    host = "unit-test-blocked.invalid"
    for i in range(N._DEAD_AFTER):
        try:
            N.fetch(f"https://{host}/p{i}", ttl_hours=0, timeout=1, retries=1)
        except N.FetchError:
            pass
    check("F6 연속 실패 후 차단 판정", host in N._dead, str(N.host_status()))

    # 차단 후에는 네트워크를 건드리지 않고 즉시 실패해야 한다
    import time
    t0 = time.time()
    try:
        N.fetch(f"https://{host}/after", ttl_hours=0, timeout=30, retries=3)
    except N.FetchError as e:
        check("F6 차단 후 즉시 실패", time.time() - t0 < 0.5, f"{time.time() - t0:.2f}초")
        check("F6 사유 명시", "생략" in str(e), str(e)[:50])
    N._dead.clear()
    N._fail_streak.clear()


# ---------------------------------------------------------------- F7
def f7_empty_secret_fallback():
    """미설정 시크릿은 환경변수를 '없음'이 아니라 '빈 문자열'로 만든다.

    사고: os.environ.get(name, 기본값) 이 빈 문자열을 돌려줘 User-Agent 가
    비고, SEC 가 403 을 냈다.
    """
    import importlib
    import os

    old = os.environ.get("SCREENER_UA")
    try:
        os.environ["SCREENER_UA"] = ""
        import screener.net as N
        importlib.reload(N)
        check("F7 빈 시크릿이면 기본 UA", "@" in N.UA and len(N.UA) > 10, repr(N.UA))
        os.environ["SCREENER_UA"] = "Test RA t@x.com"
        importlib.reload(N)
        check("F7 설정되면 그 값 사용", N.UA == "Test RA t@x.com", repr(N.UA))
    finally:
        if old is None:
            os.environ.pop("SCREENER_UA", None)
        else:
            os.environ["SCREENER_UA"] = old
        import screener.net as N
        importlib.reload(N)


# ---------------------------------------------------------------- F8
def f8_catalyst_scoping():
    """점수는 테마가 선언한 축 안에서만 나와야 한다.

    사고: 방산이 1위였는데 점수를 만든 축이 ⑧재고와 ③신기술이었다.
    방산 논지는 예산 확정 다년 계약(정책·병목)인데 무관한 축이 순위를 만들었다.
    """
    from screener.axes import Signal, resolve_catalysts
    from screener.signals import ThemeResult

    r = ThemeResult(name="t", thesis="", tickers=["A"])
    r.claimed, _ = resolve_catalysts(["정책", "병목"])
    r.catalyst = [
        Signal("A5", "⑤ 정책", 10, "ok", "d"),
        Signal("A9", "⑨ 병목", 20, "ok", "d"),
        Signal("A8", "⑧ 재고", 95, "ok", "d"),      # 선언 안 한 축
        Signal("A3", "③ 신기술", 90, "ok", "d"),     # 선언 안 한 축
    ]
    check("F8 선언 축만 점수화 (15점)", abs((r.catalyst_score or 0) - 15) < 0.01,
          f"{r.catalyst_score}")
    check("F8 예상 밖 축은 따로 보고", {s.key for s in r.incidental_axes} == {"A8", "A3"},
          str([s.key for s in r.incidental_axes]))
    check("F8 축은 살아있으나 신호 약함을 구별",
          r.thesis_status == "성립하나 신호없음", r.thesis_status)

    r2 = ThemeResult(name="t2", thesis="", tickers=["A"])
    r2.claimed, _ = resolve_catalysts(["공급"])
    r2.catalyst = [Signal("A2", "② 공급", 0, "rejected", "", "사양산업")]
    check("F8 주장 축이 기각되면 미성립", r2.thesis_status == "미성립", r2.thesis_status)


# ---------------------------------------------------------------- F9
def f9_inventory_covid_window():
    """10년 창이 2020~22 재고 급증을 품고 있어 현재를 과도하게 낮게 보이게 한다.

    사고: 전기장비가 10년 기준 0분위인데 전체 이력으로는 47분위(중앙값)였다.
    """
    from screener.axes import a8_inventory

    base = date(2000, 1, 1)
    # 재현하려는 상황: 최근 10년은 재고가 높게 유지돼 현재(100)가 최저 분위로
    # 보이지만, 그 이전 오랜 기간은 더 낮아서 전체 이력으로는 중앙값 위다.
    # 즉 "10년 최저"는 참이고 "역사적으로 낮다"는 거짓인 경우.
    inv, ship = [], []
    for i in range(320):
        d = date(base.year + i // 12, i % 12 + 1, 1)
        if i == 319:
            v = 100.0                 # 현재
        elif i >= 200:
            v = 120.0                 # 최근 10년: 높게 유지
        else:
            v = 80.0                  # 그 이전: 더 낮았다
        inv.append((d, v))
        ship.append((d, 100.0))
    series = {"INV": inv, "SHIP": ship, "NO": [(d, 100 + i) for i, (d, _) in enumerate(ship)]}
    cfg = {"inventories": "INV", "shipments": "SHIP", "new_orders": "NO"}
    s = a8_inventory(cfg, lambda k: series[k])
    check("F9 코로나 왜곡 의심 시 미확증 강등", s.status == "unconfirmed", s.status)
    check("F9 사유에 근거 표시", "전체 이력" in s.reason, s.reason[:50])


# ---------------------------------------------------------------- F10
def f10_newtech_sample_floor():
    """표본이 작으면 확산이 아니라 잡음이다.

    사고: 방산 '탄약 생산' 언급이 4개사→5개사인데 +25% 확산으로 읽어 56점을 줬다.
    """
    from screener.axes import a3_newtech

    def tiny(kw, s, e):
        return {"hits": 6, "entities": ["a", "b", "c", "d", "e"][:5 if s > e else 4],
                "sic": [("3812", 6)], "censored": False}

    s = a3_newtech({"edgar_keywords": ["munitions production"]}, {}, tiny)
    check("F10 표본 8개사 미만이면 nodata", s.status == "nodata", f"{s.status} {s.score}")
    check("F10 사유에 모수 표시", "표본" in s.reason or "언급량" in s.reason, s.reason[:40])


# ---------------------------------------------------------------- F11
def f11_vendored_ticker_fallback():
    """SEC 가 403 을 내면 티커 매핑 하나 때문에 실행 전체가 죽었다."""
    import screener.sources as S
    from screener.net import FetchError

    orig = S.fetch_json
    try:
        S.fetch_json = lambda *a, **k: (_ for _ in ()).throw(FetchError("403 모사"))
        m = S.sec_ticker_map()
        check("F11 동봉 사본으로 폴백", len(m) > 1000, f"{len(m)}개")
        check("F11 값이 정상", m.get("NVDA") == 1045810, str(m.get("NVDA")))
    finally:
        S.fetch_json = orig


# ---------------------------------------------------------------- F12
def f12_snapshot_fallback():
    """SEC 재무는 분기에 한 번 바뀌는데 매일 원격에서 받고 있었다."""
    from screener.sources import financials_snapshot, snapshot_quarterly

    snap = financials_snapshot()
    n = len(snap.get("companies") or {})
    check("F12 재무 스냅샷 동봉됨", n > 50, f"{n}개사")
    q = snapshot_quarterly("ETN", "revenue")
    check("F12 분기 시계열 복원", len(q) > 10, f"{len(q)}개 분기")
    check("F12 키가 (연,분기) 튜플", all(isinstance(k, tuple) and len(k) == 2 for k in q))


# ---------------------------------------------------------------- F13
def f13_self_reference_excluded():
    """자기 산업 지수로 자기 매출을 설명하면 순환이다.

    사고: BEA 요약 코드가 항공기와 부품을 한 덩어리로 묶어, 항공 애프터마켓의
    1위 '고객'이 자기 산업(88.5%)으로 나왔다. 그대로 쓰면 낙수 축이 순환한다.
    """
    from screener.bea import downstream_of

    data = [{"RowCode": "3364OT", "ColCode": "3364OT", "ColDescr": "Other transportation equipment", "DataValue": "885"},
            {"RowCode": "3364OT", "ColCode": "481", "ColDescr": "Air transportation", "DataValue": "17"},
            {"RowCode": "3364OT", "ColCode": "333", "ColDescr": "Machinery", "DataValue": "98"}]
    r = downstream_of(data, "3364OT")
    top_code = r[0][0]
    check("F13 자기 산업이 표에는 남는다", top_code == "3364OT", str(top_code))
    # 제안 로직에서 걸러지는지는 discover_customers 쪽 규칙이므로 여기선 존재만 확인
    check("F13 외부 고객도 함께 나온다",
          {c for c, _, _ in r} == {"3364OT", "481", "333"}, str([c for c, _, _ in r]))


# ---------------------------------------------------------------- F14
def f14_evidence_matches_claim():
    """근거 링크가 주장과 다른 것을 가리키면 정반대로 읽힌다.

    사고: 8번 축은 '재고/출하 비율'이 낮다고 판정하는데, 근거 링크는 '재고 금액
    수준'을 가리켰다. 재고 금액은 물가와 성장 때문에 늘 사상 최고 근처라,
    "재고 바닥이라면서 재고가 최고치"라는 정당한 반박을 받았다.
    """
    from datetime import date as _d

    from screener.axes import a8_inventory, a9_bottleneck

    inv = [( _d(2000 + i // 12, i % 12 + 1, 1), 100.0) for i in range(320)]
    ship = list(inv)
    no = [(d, 100.0 + i) for i, (d, _) in enumerate(ship)]
    fred = lambda k: {"INV": inv, "SHIP": ship, "NO": no, "UO": inv}[k]

    s8 = a8_inventory({"inventories": "INV", "shipments": "SHIP", "new_orders": "NO"}, fred)
    check("F14 재고축 링크에 두 계열 모두", "INV,SHIP" in s8.evidence, s8.evidence)
    check("F14 재고축 라벨이 비율임을 밝힘",
          "원계열" in s8.evidence_label and "나눗셈" in s8.evidence_label, s8.evidence_label)
    check("F14 raw 가 라벨에 안 밀림", isinstance(s8.raw, float), repr(s8.raw))

    s9 = a9_bottleneck({"unfilled_orders": "UO", "shipments": "SHIP", "new_orders": "NO"}, fred)
    check("F14 병목축 링크에 두 계열 모두", "UO,SHIP" in s9.evidence, s9.evidence)

    # 위치인수로 evidence 뒤에 raw 를 넘기던 기존 호출이 깨지지 않아야 한다
    from screener.axes import Signal
    sig = Signal("A2", "x", 50, "ok", "d", "", "http://ev", 77.7)
    check("F14 기존 위치인수 호출 유지", sig.raw == 77.7 and sig.evidence_label == "근거",
          f"raw={sig.raw} label={sig.evidence_label}")


# ---------------------------------------------------------------- F15
def f15_notfound_not_host_failure():
    """404 는 서버 장애가 아니다.

    사고: 없는 FRED 시리즈를 몇 개 조회했더니 회로차단기가 FRED 전체를 죽은
    것으로 판정해 그 뒤 모든 조회가 막혔다.
    """
    import screener.net as N

    N._dead.clear()
    N._fail_streak.clear()
    for i in range(N._DEAD_AFTER + 2):
        try:
            N.fetch(f"https://fred.stlouisfed.org/nosuchpath{i}", ttl_hours=0, timeout=10)
        except N.NotFound:
            pass
        except N.FetchError:
            pass
    check("F15 404 는 차단 판정에 안 셈", "fred.stlouisfed.org" not in N._dead,
          str(N.host_status()))
    N._dead.clear()
    N._fail_streak.clear()


# ---------------------------------------------------------------- F16
def f16_company_names():
    """티커만으로는 무슨 회사인지 알 수 없다."""
    from screener.sources import ticker_names

    n = ticker_names()
    check("F16 회사명 사전 동봉", len(n) > 5000, f"{len(n)}건")
    check("F16 값 확인", "Eaton" in (n.get("ETN") or ""), str(n.get("ETN")))


# ---------------------------------------------------------------- F17
def f17_source_prefix_routing():
    """FRED 한 곳에만 묶여 있으면 산업 고유 지표를 못 쓴다.

    정유는 주 단위로 움직이는데 EIA 주간 데이터는 FRED 에 재배포되지 않는다.
    접두사로 소스를 고를 수 있어야 한다. 그리고 키가 없을 때 조용히 죽으면
    안 된다 — 사유가 남아야 한다.
    """
    from screener.axes import _fred_pair, _ident, _series_url
    from screener.signals import _resolve_series

    check("F17 접두사 없으면 FRED", _ident("A35STI") == ("fred", "A35STI"))
    check("F17 eia 접두사 인식", _ident("eia:PET.WPULEUS3.W") == ("eia", "PET.WPULEUS3.W"))
    check("F17 FRED 링크", "fred.stlouisfed.org" in _series_url("A35STI"))
    check("F17 EIA 링크", "eia.gov" in _series_url("eia:PET.WPULEUS3.W"))
    check("F17 같은 소스 쌍은 합쳐 그림",
          "id=A35STI,A35SVS" in _fred_pair("A35STI", "A35SVS"))
    check("F17 다른 소스 쌍은 분자만",
          "eia.gov" in _fred_pair("eia:PET.WCESTUS1.W", "A24SVS"))

    try:
        _resolve_series("eia:PET.WPULEUS3.W")
        check("F17 키 없으면 사유와 함께 실패", False, "예외가 안 났다")
    except Exception as e:
        check("F17 키 없으면 사유와 함께 실패", "키 없음" in str(e), str(e)[:60])

    try:
        _resolve_series("bogus:X")
        check("F17 모르는 소스는 거부", False, "예외가 안 났다")
    except Exception as e:
        check("F17 모르는 소스는 거부", "소스" in str(e), str(e)[:50])


# ---------------------------------------------------------------- F18
def f18_eia_response_shape():
    """EIA 응답의 값 열 이름은 데이터셋마다 다르다.

    BEA 때 응답 구조를 잘못 가정해 죽은 적이 있다. 같은 실수를 막는다.
    """
    from screener.eia import _parse_period, _pick_value

    check("F18 주간 기간", _parse_period("2026-07-18") is not None)
    check("F18 월간 기간", _parse_period("2026-07") is not None)
    check("F18 연간 기간", _parse_period("2026") is not None)
    check("F18 value 열 우선", _pick_value({"period": "x", "value": "94.2"}) == 94.2)
    check("F18 다른 이름도 인식",
          _pick_value({"period": "x", "stocks": "220.5", "stocks-units": "kb"}) == 220.5)
    check("F18 단위 열은 값이 아님",
          _pick_value({"period": "x", "price-units": "3"}) is None,
          str(_pick_value({"period": "x", "price-units": "3"})))


# ---------------------------------------------------------------- F19
def f19_key_name_aliases():
    """시크릿 이름은 사람이 붙인다.

    사고 방지: 내가 안내한 이름(CENSUS_API_KEY)과 실제 등록한 이름(CENSUS_API)이
    달랐다. 이름이 안 맞아 키를 못 찾는 건 조용한 실패 중 가장 허무한 종류다.
    """
    import os

    from screener.keys import census_key, data_gov_key

    saved = {k: os.environ.get(k) for k in
             ("CENSUS_API", "CENSUS_API_KEY", "DATA_GOV_API", "DATA_GOV_API_KEY")}
    try:
        for k in saved:
            os.environ.pop(k, None)
        os.environ["CENSUS_API"] = "AAAAAAAAAAAAAAAAAAAAAAAA"
        check("F19 접미사 없는 이름도 인식", census_key() == "A" * 24, str(census_key()))
        os.environ.pop("CENSUS_API")
        os.environ["CENSUS_API_KEY"] = "BBBBBBBBBBBBBBBBBBBBBBBB"
        check("F19 접미사 있는 이름도 인식", census_key() == "B" * 24, str(census_key()))
        os.environ.pop("CENSUS_API_KEY")
        os.environ["DATA_GOV_API"] = "CCCCCCCCCCCCCCCCCCCCCCCC"
        check("F19 data.gov 도 동일", data_gov_key() == "C" * 24, str(data_gov_key()))
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


# ---------------------------------------------------------------- F20
def f20_substitution_axis():
    """⑩ 대체 축 — 침투율이 내려가도 시장 자체가 줄면 의미가 없다."""
    from datetime import date as _d

    from screener.axes import a10_substitution

    # 국내 출하가 함께 줄어드는 경우 = 시장 축소로 기각돼야 한다
    dom = [(_d(2020 + i // 12, i % 12 + 1, 1), 100.0 - i * 0.5) for i in range(72)]
    fred = lambda k: dom

    import screener.axes as A
    import screener.census as C
    orig = C.trade_monthly
    try:
        # 수입은 더 빠르게 줄어 침투율이 하락하는 상황
        C.trade_monthly = lambda n, f="imports", years=6: [
            (d, 40.0 - i * 0.5) for i, (d, _) in enumerate(dom)]
        s = a10_substitution({"trade_naics": "331", "shipments": "SHIP"}, fred)
        check("F20 시장 축소면 기각", s.status == "rejected", f"{s.status} {s.reason[:40]}")
        check("F20 기각 사유 명시", "시장 축소" in s.reason, s.reason[:40])
    finally:
        C.trade_monthly = orig

    s2 = a10_substitution({"shipments": "SHIP"}, fred)
    check("F20 NAICS 미지정이면 nodata", s2.status == "nodata", s2.status)


# ---------------------------------------------------------------- F21
def f21_usaspending_incomplete_quarter():
    """진행 중인 분기를 그대로 쓰면 '계약 급감'으로 오독한다.

    실측: FY2026 Q4 = -11,407달러(직전 분기들은 90~178십억). 연방 계약은
    보고 지연이 1~3개월이라 분기가 끝나도 한동안 계속 채워진다. 크기로
    판정하면 '급감'과 '집계 미완'을 구별할 수 없어 날짜로 자른다.
    """
    from datetime import date as _d
    from datetime import timedelta as _td

    import screener.usaspending as U

    today = _d.today()
    check("F21 보고지연 상수 존재", U.LAG_DAYS >= 60, str(U.LAG_DAYS))

    # 회계분기 -> 달력 마감일
    check("F21 FY Q1 은 전년 12월말", U._fq_to_date(2026, 1) == _d(2025, 12, 31))
    check("F21 FY Q4 는 당년 9월말", U._fq_to_date(2026, 4) == _d(2026, 9, 30))

    # 잘라내기 경계: LAG_DAYS 안쪽 분기는 버려야 한다
    cutoff = today - _td(days=U.LAG_DAYS)
    check("F21 컷오프가 과거", cutoff < today)

    # TTM 이 계절성을 걷어내는지
    q = [(_d(2020 + i // 4, 3 * (i % 4) + 3, 28), 100.0 if i % 4 else 400.0)
         for i in range(16)]
    t = U.ttm(q)
    vals = [v for _, v in t]
    check("F21 TTM 은 4분기 합", all(abs(v - 700.0) < 1e-6 for v in vals),
          str(vals[:3]))


# ---------------------------------------------------------------- F22
def f22_budget_axis_precedence():
    """방산 수요는 규제가 아니라 예산이 만든다.

    사고: 방산 논지가 '예산 확정 다년 계약'인데 Federal Register 규제 검색으로
    재고 있었다. 애초에 맞지 않는 도구였고 결과는 촉매 0 이었다.
    """
    from screener.axes import a5_budget

    check("F22 usaspending 설정 없으면 None(규제 검색으로 넘김)",
          a5_budget({}, {}) is None)
    check("F22 설정 있으면 Signal 반환",
          a5_budget({"usaspending": {"agency": "Department of Defense"}}, {}) is not None)


# ---------------------------------------------------------------- F23
def f23_rebound_not_unpriced():
    """올랐다 빠지는 것을 '미반영'으로 착각하면 안 된다.

    사고: 고점 대비 눌림 축이 드로다운이 클수록 점수를 줬다. +200% 오른 뒤
    -35% 빠진 것도 드로다운이 크다. 실측에서 원자력이 12개월 상대수익률
    -9%p 로 눌려 보였지만 3년 상대수익률은 +102%p 였고 200일선을 26% 밑돌고
    있었다 — 과열 되돌림인데 미반영 90점(최고)을 받았다.
    """
    from screener.signals import ThemeResult, u4_long_term, u5_basing

    # 되돌림: 3년 크게 초과 + 고점이 최근
    px_rebound = {"rel_3y": 102.0, "drawdown": 26.0,
                  "peak_age_days": 182, "vs_ma200": -25.6, "rebound": True}
    # 진짜 눌림: 3년 마이너스 + 고점이 오래됨 + 200일선 위
    px_real = {"rel_3y": -101.0, "drawdown": 12.0,
               "peak_age_days": 1513, "vs_ma200": 0.8, "rebound": False}

    a = u4_long_term(px_rebound)
    b = u4_long_term(px_real)
    check("F23 장기축: 되돌림은 낮게", a.score < 20, f"{a.score:.0f}")
    check("F23 장기축: 진짜 눌림은 높게", b.score > 80, f"{b.score:.0f}")

    c = u5_basing(px_rebound)
    d = u5_basing(px_real)
    check("F23 바닥축: 내려가는 중은 낮게", c.score < 40, f"{c.score:.0f}")
    check("F23 바닥축: 다져진 바닥은 높게", d.score > 70, f"{d.score:.0f}")
    check("F23 상태를 말로 표시", "내려가는 중" in c.detail, c.detail[-24:])

    # 되돌림 플래그가 미반영 점수를 깎는지
    from screener.axes import Signal
    r1 = ThemeResult(name="a", thesis="", tickers=["X"], rebound=True)
    r2 = ThemeResult(name="b", thesis="", tickers=["X"], rebound=False)
    for r in (r1, r2):
        r.unpriced = [Signal("U1", "x", 80, "ok", "d"), Signal("U3", "y", 80, "ok", "d")]
    check("F23 되돌림이면 미반영 절반", abs(r1.unpriced_score - 40) < 0.01,
          f"{r1.unpriced_score}")
    check("F23 아니면 그대로", abs(r2.unpriced_score - 80) < 0.01, f"{r2.unpriced_score}")


# ---------------------------------------------------------------- F24
def f24_rebound_detection():
    """되돌림 판정 조건: 3년 초과 상승 + 최근 고점."""
    from datetime import date as _d
    from datetime import timedelta as _td

    from screener.signals import price_stats

    # 3년간 우상향 후 최근 급락 (되돌림), 벤치는 평평
    base = _d(2020, 1, 1)
    days = [base + _td(days=i) for i in range(1100)]
    up = [(d, 100.0 + i * 0.25) for i, d in enumerate(days[:1000])]
    up += [(d, up[-1][1] * (1 - 0.0012 * (i + 1))) for i, d in enumerate(days[1000:])]
    bench = [(d, 100.0) for d in days]
    st = price_stats(["X"], {"X": up}, bench)
    check("F24 3년 상대수익률 계산", st.get("rel_3y") is not None, str(st.get("rel_3y")))
    check("F24 되돌림으로 판정", st.get("rebound") is True,
          f"rel3y={st.get('rel_3y'):.0f} peak_age={st.get('peak_age_days')}")
    check("F24 고점 경과일 산출", 0 < st["peak_age_days"] < 250,
          str(st["peak_age_days"]))
    check("F24 200일선 대비 산출", st.get("vs_ma200") is not None)


# ---------------------------------------------------------------- F25
def f25_partial_thesis_disclosure():
    """축 하나가 점수 전부를 만들면 '성립'이라 부르지 않는다.

    사고: 방산이 정책 92 / 병목 0.4 로 평균 46, '논지 성립·볼 만함'이 됐다.
    병목 0.4 는 수주잔고가 10년 최저라는 뜻 — 논지 절반을 데이터가 반박하는데
    화면에는 깨끗한 '성립'으로 보였다. 사용자가 이를 지적했다.
    """
    from screener.axes import Signal, resolve_catalysts
    from screener.signals import ThemeResult

    r = ThemeResult(name="t", thesis="", tickers=["A"])
    r.claimed, _ = resolve_catalysts(["정책", "병목"])
    r.catalyst = [
        Signal("A5", "⑤ 정책", 92, "ok", "d"),
        Signal("A9", "⑨ 병목", 0.4, "ok", "d"),
    ]
    check("F25 한 축이 죽어 있으면 '일부만 작동'",
          r.thesis_status == "일부만 작동", r.thesis_status)

    r2 = ThemeResult(name="t2", thesis="", tickers=["A"])
    r2.claimed, _ = resolve_catalysts(["정책", "재고"])
    r2.catalyst = [
        Signal("A5", "⑤ 정책", 92, "ok", "d"),
        Signal("A8", "⑧ 재고", 85, "ok", "d"),
    ]
    check("F25 둘 다 살아 있으면 '성립'", r2.thesis_status == "성립", r2.thesis_status)


# ---------------------------------------------------------------- F26
def f26_supply_long_run():
    """공급 비탄력은 1년 능력 YoY 만으로 판정할 수 없다.

    사고: 전력기기는 능력이 10년간 연 -1.0% 씩 줄었고 가동률 92분위,
    3년 가격 +10.2% vs 물량 +2.6% 로 교과서적 비탄력인데, 1년 능력 +2.0%
    하나 때문에 점수가 절반으로 깎였다. 10년 수축 뒤의 +2% 는 증설이 아니라
    바닥에서의 미동이다. 사용자가 '공급 비탄력을 증명해봐'라고 지적했다.
    """
    from datetime import date as _d

    from screener.axes import a2_supply

    def series(vals_per_year):
        out, i = [], 0
        for y, v0, v1 in vals_per_year:
            for m in range(12):
                out.append((_d(y, m + 1, 1), v0 + (v1 - v0) * m / 11))
                i += 1
        return out

    yrs = list(range(2013, 2027))
    # 능력: 10년간 연 -1% 수축, 마지막 1년만 +2%
    cap = []
    v = 100.0
    for y in yrs:
        nxt = v * (1.02 if y == 2026 else 0.99)
        cap += [(_d(y, m + 1, 1), v + (nxt - v) * m / 11) for m in range(12)]
        v = nxt
    # 가동률: 상승 추세(최근이 10년 최고권)
    util = [(_d(2013 + i // 12, i % 12 + 1, 1), 70.0 + 15.0 * i / len(cap) )
            for i in range(len(cap))]
    # 생산: 완만한 증가 / 가격: 3년간 +10%
    ip = [(d, 100.0 + 3.0 * i / len(cap)) for i, (d, _) in enumerate(cap)]
    ppi = [(d, 100.0 * (1.10 ** (max(0, i - (len(cap) - 37)) / 36)))
           for i, (d, _) in enumerate(cap)]
    F = {"CAP": cap, "UTIL": util, "IP": ip, "PPI": ppi}

    cfg = {"capacity_utilization": "UTIL", "capacity_index": "CAP",
           "industrial_production": "IP", "ppi_output": "PPI"}
    s = a2_supply(cfg, lambda k: F[k])
    check("F26 10년 수축이면 1년 +2% 로 안 깎임", s.score is not None and s.score > 70,
          f"{s.status} {s.score}")
    check("F26 장기 CAGR 을 화면에 표시", "10년 연" in s.detail, s.detail[:60])
    check("F26 가격 반응 표시", "가격" in s.detail, s.detail[-60:])

    # 반대로 장기 확장(연 +7%)이면 낮거나 기각이어야 한다
    cap2 = []
    v = 100.0
    for y in yrs:
        nxt = v * 1.07
        cap2 += [(_d(y, m + 1, 1), v + (nxt - v) * m / 11) for m in range(12)]
        v = nxt
    F2 = dict(F); F2["CAP"] = cap2
    s2 = a2_supply(cfg, lambda k: F2[k])
    check("F26 장기 확장이면 기각/저점수",
          s2.status == "rejected" or (s2.score or 0) < 40, f"{s2.status} {s2.score}")


def main() -> int:
    for fn in [f1_ytd_differencing, f2_no_economy_wide_fallback, f3_bea_result_shapes,
               f4_bea_final_demand_excluded, f5_naics_matching_direction,
               f6_circuit_breaker, f7_empty_secret_fallback, f8_catalyst_scoping,
               f9_inventory_covid_window, f10_newtech_sample_floor,
               f11_vendored_ticker_fallback, f12_snapshot_fallback,
               f13_self_reference_excluded, f14_evidence_matches_claim,
               f15_notfound_not_host_failure, f16_company_names,
               f17_source_prefix_routing, f18_eia_response_shape,
               f19_key_name_aliases, f20_substitution_axis,
               f21_usaspending_incomplete_quarter, f22_budget_axis_precedence,
               f23_rebound_not_unpriced, f24_rebound_detection,
               f25_partial_thesis_disclosure, f26_supply_long_run]:
        try:
            fn()
        except Exception as e:
            import traceback
            check(f"{fn.__name__} 실행 실패", False, f"{type(e).__name__}: {e}")
            traceback.print_exc()

    ok = sum(1 for _, p, _ in RESULTS if p)
    for name, passed, detail in RESULTS:
        mark = "PASS" if passed else "FAIL"
        line = f"  [{mark}] {name}"
        if not passed and detail:
            line += f"  -> {detail}"
        print(line)
    print(f"\n{ok}/{len(RESULTS)} PASS")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
