"""테마 평가 오케스트레이션 — 촉매 축(axes.py) + 미반영 축.

촉매 점수는 9개 축의 단순평균이 아니라 **최강 2개 축의 평균**이다.
테마는 보통 한두 개 축으로 오르며, 9개를 평균하면 강한 신호가 무관한 축에
희석돼 '어느 축도 강하지 않은 무난한 테마'가 상위로 올라온다.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date

from . import axes
from .axes import Signal
from .net import FetchError
from .sources import (
    CONCEPTS,
    edgar_fts,
    fedreg_signal,
    financials_snapshot,
    fred_series,
    sec_company_facts,
    snapshot_quarterly,
    xbrl_quarterly,
    yahoo_prices,
)
from .stats import mean, pct_rank, scale, slope, top_n_mean, ttm


@dataclass
class ThemeResult:
    name: str
    thesis: str
    tickers: list[str]
    catalyst: list[Signal] = field(default_factory=list)
    unpriced: list[Signal] = field(default_factory=list)
    lead_time: str = ""
    notes: list[str] = field(default_factory=list)
    series: dict = field(default_factory=dict)
    customers: dict = field(default_factory=dict)
    claimed: set = field(default_factory=set)      # 테마가 선언한 촉매 축 키
    unknown_catalysts: list = field(default_factory=list)
    stocks: list = field(default_factory=list)     # 종목별 미반영 내역
    rebound: bool = False                          # 과열 되돌림 여부

    @property
    def claimed_axes(self) -> list[Signal]:
        """테마가 '이것 때문에 오른다'고 선언한 축들."""
        if not self.claimed:
            return list(self.catalyst)             # 미선언이면 종전대로 전체
        return [s for s in self.catalyst if s.key in self.claimed]

    @property
    def incidental_axes(self) -> list[Signal]:
        """선언하지 않았는데 강한 축 — 순위엔 안 넣고 단서로만 본다."""
        if not self.claimed:
            return []
        return sorted(
            [s for s in self.catalyst
             if s.key not in self.claimed and (s.effective or 0) >= 60],
            key=lambda s: -(s.effective or 0))

    @property
    def catalyst_score(self) -> float | None:
        # 점수는 주장 축 안에서만 낸다. 무관한 축이 우연히 높다고 순위를 만들면
        # 그건 '왜 오르나'가 아니라 '무엇이 마침 높나'가 된다.
        return top_n_mean([s.effective for s in self.claimed_axes], 2)

    @property
    def thesis_status(self) -> str:
        """논지 성립 여부 — 이 도구의 가장 중요한 출력.

        축의 '상태'만 보면 안 된다. 방산은 주장한 두 축이 모두 ok 였지만 점수가
        0.4 였다 — 수주잔고 배수가 10년 0분위였기 때문이다. 반증되지 않은 것과
        지금 작동 중인 것은 다르다. 그래서 세기까지 함께 본다.
        """
        if not self.claimed:
            return "미선언"
        live = [s for s in self.claimed_axes if s.status in ("ok", "unconfirmed")]
        if not live:
            return "미성립"
        if any(s.status == "rejected" for s in self.claimed_axes):
            return "일부기각"

        sc = self.catalyst_score or 0.0
        if sc < 25:
            # 논지가 틀렸다는 게 아니라, 지금 그 힘이 작동한다는 증거가 없다는 뜻
            return "성립하나 신호없음"
        if len(live) < len(self.claimed_axes):
            return "일부확인불가"
        return "성립" if all(s.status == "ok" for s in live) else "미확증"

    @property
    def unpriced_score(self) -> float | None:
        """미반영 점수.

        되돌림(3년간 크게 오른 뒤 최근 고점에서 하락 중)이면 절반으로 깎는다.
        드로다운이 크다는 것만으로 '미반영'이라고 하면, 올랐다 빠지는 것을
        저평가로 착각한다 — 실측에서 원자력이 그 경우였다(3년 +102%p).
        """
        base = mean([s.score for s in self.unpriced])
        if base is None:
            return None
        return base * 0.5 if self.rebound else base

    @property
    def top_axes(self) -> list[Signal]:
        live = [s for s in self.claimed_axes if s.effective is not None]
        return sorted(live, key=lambda s: -(s.effective or 0))[:2]

    @property
    def gate_passed(self) -> int:
        return sum(1 for s in self.unpriced if s.score is not None and s.score >= 60)

    @property
    def n_rejected(self) -> int:
        return sum(1 for s in self.catalyst if s.status == "rejected")

    @property
    def coverage(self) -> float:
        tot = len(self.catalyst)
        live = sum(1 for s in self.catalyst if s.status in ("ok", "unconfirmed"))
        return 100.0 * live / tot if tot else 0.0


# ================================================================ 미반영 축

def u1_fundamental_inflection(agg: dict) -> Signal:
    g = agg.get("rev_yoy_series") or []
    if len(g) < 6:
        return Signal("U1", "실적 변곡(리비전 대용)", None, "nodata", "", "TTM 매출 이력 부족")
    cur, acc = g[-1][1], slope(g, 4)
    sc = mean([scale(acc, -6, 8), scale(cur, -8, 20)])
    return Signal("U1", "실적 변곡(리비전 대용)", sc, "ok",
                  f"그룹 TTM 매출 YoY {cur:+.1f}%, 최근 4분기 가속도 {acc:+.1f}%p/분기")


def u2_valuation_gap(agg: dict) -> Signal:
    cur, hist = agg.get("ev_ebit_now"), agg.get("ev_ebit_hist") or []
    rank = pct_rank(cur, hist)
    if rank is None:
        return Signal("U2", "밸류에이션 여유", None, "nodata", "", "EV/EBIT 이력 부족")
    return Signal("U2", "밸류에이션 여유", 100.0 - rank, "ok",
                  f"그룹 EV/EBIT {cur:.1f}배 — 자체 5년 이력 {rank:.0f}분위")


def u3_price_unreacted(px: dict) -> Signal:
    rel = px.get("rel_12m")
    if rel is None:
        return Signal("U3", "주가 미반응(vs S&P)", None, "nodata", "", "주가 이력 부족")
    return Signal("U3", "주가 미반응(vs S&P)", scale(-rel, -35, 35), "ok",
                  f"12개월 상대수익률 {rel:+.1f}%p (절대 {px['abs_12m']:+.1f}%)",
                  raw=rel)


def u4_long_term(px: dict) -> Signal:
    """장기(3년) 미반영 — '올랐다 빠지는 것'을 걸러내는 핵심 축.

    드로다운만 보면 안 된다. +200% 오른 뒤 -35% 빠진 것도 드로다운이 크다.
    실측: 원자력은 12개월 상대수익률 -9%p 로 눌려 보이지만 3년 상대수익률이
    +102%p 다 — 이미 크게 오른 것의 되돌림이지 미반영이 아니다.
    반면 화학은 3년 -101%p, 고점이 1,513일 전이다. 그게 진짜 눌린 것이다.
    """
    rel3 = px.get("rel_3y")
    if rel3 is None:
        return Signal("U4", "장기 미반영(3년)", None, "nodata", "", "3년 주가 이력 부족")
    dd = px.get("drawdown")
    detail = f"3년 상대수익률 {rel3:+.0f}%p"
    if dd is not None:
        detail += f", 52주 고점 대비 {-dd:.1f}%"
    return Signal("U4", "장기 미반영(3년)", scale(-rel3, -60, 60), "ok", detail, raw=rel3)


def u5_basing(px: dict) -> Signal:
    """바닥 다지기 — 떨어지는 칼날과 다져진 바닥을 가른다.

    고점이 오래됐고 200일선 근처/위면 눌림이 소화된 것이다.
    고점이 최근이고 200일선을 크게 밑돌면 아직 내려가는 중이다.
    """
    age, ma = px.get("peak_age_days"), px.get("vs_ma200")
    if age is None or ma is None:
        return Signal("U5", "바닥 다지기", None, "nodata", "", "주가 이력 부족")
    # 고점 경과 250일 이상이면 만점권, 60일 미만이면 0점
    age_s = scale(age, 60, 400) or 0.0
    # 200일선 대비 -15% 이하면 0점, 0% 이상이면 만점권
    ma_s = scale(ma, -15, 3) or 0.0
    sc = 0.6 * age_s + 0.4 * ma_s
    state = ("바닥 다지는 중" if sc >= 55 else
             "아직 내려가는 중" if sc < 30 else "중간")
    return Signal("U5", "바닥 다지기", sc, "ok",
                  f"52주 고점 {age}일 전, 200일선 대비 {ma:+.1f}% — {state}", raw=sc)


# ================================================================ 재무 집계

def aggregate_financials(tickers: list[str], tmap: dict[str, int],
                         prices: dict[str, list]) -> tuple[dict, list[str]]:
    """그룹 재무 집계.

    한 기업이 특정 분기를 공시 안 하면 합계가 툭 떨어진다. 해당 분기를 보고한
    기업이 그룹의 60% 이상일 때만 그 분기를 채택해, 구성 변화로 생긴 가짜
    급변을 배제한다.
    """
    notes: list[str] = []
    per: dict[str, dict] = {}
    missing, from_snap = [], []
    for t in tickers:
        cik = tmap.get(t.upper())
        facts = None
        if cik:
            try:
                facts = sec_company_facts(cik)
            except FetchError:
                facts = None
        if facts is not None:
            per[t] = {c: xbrl_quarterly(facts, c) for c in CONCEPTS}
            continue
        # SEC 가 막혔으면 동봉 스냅샷으로. 재무는 분기에 한 번 바뀌므로
        # 며칠 낡아도 신호가 달라지지 않는다.
        snap = {c: snapshot_quarterly(t, c) for c in CONCEPTS}
        if any(snap.values()):
            per[t] = snap
            from_snap.append(t)
        else:
            missing.append(t)
    if from_snap:
        gen = (financials_snapshot().get("generated") or "?")
        notes.append(f"동봉 재무 스냅샷 사용({gen} 기준) {len(from_snap)}개사: "
                     f"{', '.join(from_snap)}")
    if missing:
        notes.append(f"SEC 재무 미확보: {', '.join(missing)}")
    if not per:
        return {}, notes

    min_co = max(1, int(round(len(per) * 0.6)))

    def gsum(concept: str) -> dict:
        b: dict = {}
        for d in per.values():
            for k, v in d.get(concept, {}).items():
                b.setdefault(k, []).append(v)
        return {k: sum(v) for k, v in b.items() if len(v) >= min_co}

    rev, ebit = gsum("revenue"), gsum("ebit")
    capex, dep = gsum("capex"), gsum("dep")
    ppe_g, acc, ppe_n = gsum("ppe_gross"), gsum("accum_dep"), gsum("ppe_net")
    inv, cash, debt, shares = gsum("inventory"), gsum("cash"), gsum("debt"), gsum("shares")

    agg: dict = {"n_companies": len(per)}
    rev_ttm = ttm(rev)
    rev_map = dict(rev_ttm)

    if len(rev_ttm) >= 5:
        agg["rev_yoy_series"] = [
            (k, 100.0 * (v / rev_map[(k[0] - 1, k[1])] - 1.0))
            for k, v in rev_ttm
            if (k[0] - 1, k[1]) in rev_map and rev_map[(k[0] - 1, k[1])]
        ]

    cx, dp = dict(ttm(capex)), dict(ttm(dep))
    ratios = [(k, cx[k] / dp[k]) for k in sorted(set(cx) & set(dp)) if dp[k]]
    if ratios:
        agg["capex_dep_now"] = ratios[-1][1]
        agg["capex_dep_3y"] = statistics.fmean([v for _, v in ratios[-12:]])
        agg["capex_dep_series"] = ratios

    # 설비 소진율은 분자·분모를 반드시 같은 기업 집합에서 내야 한다.
    # gsum 을 따로 쓰면 감가상각누계는 5개사, 총PP&E 는 8개사에서 나올 수 있고
    # 그러면 비율이 실제보다 낮게 찍힌다(유틸리티 소진율 15% 가 그 결과였다).
    ages = []
    for k in sorted(set(ppe_g) & set(acc)):
        num = den = 0.0
        n = 0
        for d in per.values():
            g, a = d.get("ppe_gross", {}).get(k), d.get("accum_dep", {}).get(k)
            if g and a:
                den += g
                num += a
                n += 1
        if n >= min_co and den:
            ages.append((k, num / den))
    if ages:
        agg["ppe_age"] = ages[-1][1]
        agg["ppe_age_hist"] = [v for _, v in ages[-40:]]
        agg["ppe_age_n"] = n

    # 영업이익률 — ⑦ 스프레드의 '아직 마진에 안 왔다' 확증에 쓰인다
    eb = dict(ttm(ebit))
    om = [(k, 100.0 * eb[k] / rev_map[k]) for k in sorted(set(eb) & set(rev_map)) if rev_map[k]]
    if om:
        agg["op_margin_series"] = om

    # PP&E/매출 — ⑥ 캐펙스의 '자산경량화' 기각에 쓰인다
    pr = [(k, ppe_n[k] / rev_map[k]) for k in sorted(set(ppe_n) & set(rev_map)) if rev_map[k]]
    if pr:
        agg["ppe_to_rev_series"] = pr

    # 재고 증감 — ① 낙수의 '주문이 실제로 들어오는 중' 확증
    if len(inv) >= 5:
        ks = sorted(inv)
        prev = (ks[-1][0] - 1, ks[-1][1])
        if prev in inv and inv[prev]:
            agg["inv_yoy"] = 100.0 * (inv[ks[-1]] / inv[prev] - 1.0)

    ev_hist = []
    for k in sorted(eb):
        if k not in shares or eb[k] <= 0:
            continue
        qend = _quarter_end(k)
        mcap, have = 0.0, 0
        for t in per:
            p = _price_on(prices.get(t) or [], qend)
            sh = per[t].get("shares", {}).get(k)
            if p and sh:
                mcap += p * sh
                have += 1
        if have < min_co or mcap <= 0:
            continue
        ev = mcap + debt.get(k, 0.0) - cash.get(k, 0.0)
        if ev > 0:
            ev_hist.append((k, ev / eb[k]))
    if len(ev_hist) >= 8:
        agg["ev_ebit_now"] = ev_hist[-1][1]
        agg["ev_ebit_hist"] = [v for _, v in ev_hist[-20:]]
        agg["ev_ebit_series"] = ev_hist

    return agg, notes


def _quarter_end(k) -> date:
    y, q = k
    m = q * 3
    return date(y, m, {3: 31, 6: 30, 9: 30, 12: 31}[m])


def _price_on(series: list, when: date) -> float | None:
    prior = [v for d, v in series if d <= when]
    return prior[-1] if prior else None


def price_stats(tickers: list[str], prices: dict, bench: list) -> dict:
    curves = [prices[t] for t in tickers if prices.get(t) and len(prices[t]) > 260]
    if not curves:
        return {}
    maps = [dict(c) for c in curves]
    common = set(maps[0])
    for m in maps[1:]:
        common &= set(m)
    days = sorted(common)
    if len(days) < 260:
        return {}
    bases = [m[days[0]] for m in maps]
    idx = [(d, statistics.fmean([m[d] / b for m, b in zip(maps, bases)])) for d in days]

    def rel_over(n: int) -> tuple[float | None, float | None]:
        """n 거래일 절대·상대 수익률."""
        if len(idx) < n + 5:
            return None, None
        a = 100.0 * (idx[-1][1] / idx[-n][1] - 1.0)
        if not bench or len(bench) < n + 5:
            return a, None
        bn, bt = _price_on(bench, days[-1]), _price_on(bench, days[-n])
        if not (bn and bt):
            return a, None
        return a, a - 100.0 * (bn / bt - 1.0)

    abs_12m, rel_12m = rel_over(min(len(idx), 252))
    _, rel_3y = rel_over(756)

    # 52주 고점과 그 이후 경과일. '언제 고점이었나'가 눌림의 성격을 가른다 —
    # 최근 고점은 방금 꺾인 것, 오래된 고점은 소화된 것이다.
    win = idx[-252:] if len(idx) >= 252 else idx
    pk = max(range(len(win)), key=lambda i: win[i][1])
    dd = 100.0 * (1.0 - idx[-1][1] / win[pk][1])
    peak_age = (idx[-1][0] - win[pk][0]).days

    # 200일 이동평균 대비 위치. 크게 밑돌면 하락 추세가 진행 중이다.
    ma200 = statistics.fmean([v for _, v in idx[-200:]]) if len(idx) >= 200 else None
    vs_ma = (100.0 * (idx[-1][1] / ma200 - 1.0)) if ma200 else None

    # 되돌림 판정: 3년간 크게 초과 상승했는데 고점이 아직 최근이면
    # 그건 미반영이 아니라 과열의 되돌림이다.
    rebound = bool(rel_3y is not None and rel_3y > 60 and peak_age < 250)

    return {"abs_12m": abs_12m, "rel_12m": rel_12m, "rel_3y": rel_3y,
            "drawdown": dd, "peak_age_days": peak_age, "vs_ma200": vs_ma,
            "rebound": rebound, "index": idx}


# ================================================================ 시계열 해석

def _resolve_series(sid: str):
    """'eia:PET.WPULEUS3.W' -> EIA, 'fred:X' 또는 접두사 없음 -> FRED."""
    raw = str(sid or "").strip()
    if ":" in raw:
        src, ident = raw.split(":", 1)
        src, ident = src.strip().lower(), ident.strip()
    else:
        src, ident = "fred", raw
    if src == "eia":
        from .eia import eia_series
        return eia_series(ident)
    if src == "fred":
        return fred_series(ident)
    raise FetchError(f"알 수 없는 데이터 소스 접두사: {src!r} ({raw})")


def series_evidence(sid: str) -> str:
    """근거 링크. 소스마다 사람이 볼 수 있는 페이지가 다르다."""
    raw = str(sid or "").strip()
    if raw.lower().startswith("eia:"):
        from .eia import series_url
        return series_url(raw.split(":", 1)[1].strip())
    ident = raw.split(":", 1)[1].strip() if ":" in raw else raw
    return f"https://fred.stlouisfed.org/series/{ident}"


# ================================================================ 평가

def evaluate_theme(theme: dict, tmap: dict, bench: list, series_cache: dict) -> ThemeResult:
    tickers = [t.upper() for t in theme.get("tickers", [])]
    claimed, unknown = axes.resolve_catalysts(theme.get("catalysts") or [])
    res = ThemeResult(name=theme["name"], thesis=theme.get("thesis", ""),
                      tickers=tickers, lead_time=theme.get("lead_time", ""),
                      customers=theme.get("customers") or {},
                      claimed=claimed, unknown_catalysts=unknown)
    if unknown:
        res.notes.append(f"알 수 없는 촉매 이름: {', '.join(unknown)}")
    if not claimed:
        res.notes.append("촉매 미선언 — themes.yaml 에 catalysts 를 적으면 "
                         "'이 논지가 데이터로 성립하는가'를 판정할 수 있다")

    def fred(sid):
        """시계열 해석기.

        FRED 한 곳에만 묶여 있으면 산업 고유 지표를 못 쓴다. 접두사로 소스를
        고른다: 'eia:PET.WPULEUS3.W' 처럼. 접두사가 없으면 FRED(기존 설정 호환).
        """
        if sid not in series_cache:
            series_cache[sid] = _resolve_series(sid)
        return series_cache[sid]

    def fts(kw, start, end):
        return edgar_fts(kw, start=start, end=end)

    prices = {}
    for t in tickers:
        try:
            prices[t] = yahoo_prices(t)
        except FetchError:
            res.notes.append(f"주가 미확보: {t}")

    group, notes = aggregate_financials(tickers, tmap, prices)
    res.notes.extend(notes)
    px = price_stats(tickers, prices, bench)

    # 고객군 재무 — ①④축의 측정 대상
    cust_cfg = theme.get("customers") or {}
    cust_fin: dict = {}
    ct = [t.upper() for t in (cust_cfg.get("tickers") or [])]
    if ct:
        cprices = {}
        for t in ct:
            try:
                cprices[t] = yahoo_prices(t)
            except FetchError:
                pass
        cust_fin, cnotes = aggregate_financials(ct, tmap, cprices)
        res.notes.extend(f"[고객군] {n}" for n in cnotes)

    fr = fedreg_signal(theme.get("fedreg_terms") or [],
                       theme.get("fedreg_agencies"))
    fc = theme.get("fred", {})

    res.catalyst = [
        axes.a1_downstream(cust_cfg, group, fc, fred),
        axes.a2_supply(fc, fred),
        axes.a3_newtech(theme, group, fts),
        axes.a4_replacement(cust_fin),
        axes.a5_budget(theme, group) or axes.a5_policy(theme, fr),
        axes.a6_capex(group, fc, fred),
        axes.a7_spread(fc, group, fred),
        axes.a8_inventory(fc, fred),
        axes.a9_bottleneck(fc, fred),
        axes.a10_substitution(fc, fred),
    ]
    res.unpriced = [u1_fundamental_inflection(group), u2_valuation_gap(group),
                    u3_price_unreacted(px), u4_long_term(px), u5_basing(px)]
    res.rebound = bool(px.get("rebound"))
    res.series = {
        "price_index": px.get("index", [])[-500:],
        "rev_yoy": group.get("rev_yoy_series", []),
        "capex_dep": group.get("capex_dep_series", []),
        "ev_ebit": group.get("ev_ebit_series", []),
        "n_companies": group.get("n_companies", 0),
        "n_customers": cust_fin.get("n_companies", 0),
    }
    res.stocks = per_stock(tickers, tmap, prices, bench)
    return res


def per_stock(tickers: list[str], tmap: dict, prices: dict, bench: list) -> list[dict]:
    """종목별 내역.

    촉매는 테마 전체에 걸리지만, 그게 아직 가격에 안 들어간 정도는 종목마다
    다르다. 테마가 '어디를 볼까'를 답하면 이 표는 '그중 뭐가 아직 안 움직였나'를
    답한다. 종목을 고르는 모델이 아니라, 같은 테마 안의 미반영 정도 비교다.
    """
    out: list[dict] = []
    for t in tickers:
        px = prices.get(t) or []
        row: dict = {"ticker": t}
        if len(px) > 260:
            back = min(len(px), 252)
            abs12 = 100.0 * (px[-1][1] / px[-back][1] - 1.0)
            row["abs_12m"] = abs12
            if bench and len(bench) > 260:
                bn = _price_on(bench, px[-1][0])
                bt = _price_on(bench, px[-back][0])
                if bn and bt:
                    row["rel_12m"] = abs12 - 100.0 * (bn / bt - 1.0)
            peak = max(v for _, v in px[-252:])
            row["drawdown"] = 100.0 * (1.0 - px[-1][1] / peak)

        cik = tmap.get(t.upper())
        facts = None
        if cik:
            try:
                facts = sec_company_facts(cik)
            except FetchError:
                facts = None
        con = ({c: xbrl_quarterly(facts, c) for c in CONCEPTS} if facts is not None
               else {c: snapshot_quarterly(t, c) for c in CONCEPTS})

        rev_ttm = dict(ttm(con.get("revenue", {})))
        if rev_ttm:
            k = max(rev_ttm)
            prev = (k[0] - 1, k[1])
            if prev in rev_ttm and rev_ttm[prev]:
                row["rev_yoy"] = 100.0 * (rev_ttm[k] / rev_ttm[prev] - 1.0)
        eb = dict(ttm(con.get("ebit", {})))
        common = sorted(set(eb) & set(rev_ttm))
        if common:
            k = common[-1]
            if rev_ttm[k]:
                row["op_margin"] = 100.0 * eb[k] / rev_ttm[k]
        out.append(row)

    # 미반영도 순으로: 상대수익률이 낮고 눌림이 클수록 위
    def key(r):
        rel = r.get("rel_12m")
        dd = r.get("drawdown")
        if rel is None:
            return 1e9
        return rel - (dd or 0) * 0.3
    return sorted(out, key=key)
