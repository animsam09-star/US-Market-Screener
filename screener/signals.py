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
    edgar_fts,
    fedreg_signal,
    fred_series,
    sec_company_facts,
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
        return mean([s.score for s in self.unpriced])

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
                  f"12개월 상대수익률 {rel:+.1f}%p (절대 {px['abs_12m']:+.1f}%)")


def u4_drawdown(px: dict) -> Signal:
    dd = px.get("drawdown")
    if dd is None:
        return Signal("U4", "고점 대비 눌림", None, "nodata", "", "주가 이력 부족")
    return Signal("U4", "고점 대비 눌림", scale(dd, 0, 35), "ok",
                  f"52주 고점 대비 {-dd:.1f}%")


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
    missing = []
    for t in tickers:
        cik = tmap.get(t.upper())
        if not cik:
            missing.append(t)
            continue
        try:
            facts = sec_company_facts(cik)
        except FetchError:
            missing.append(t)
            continue
        per[t] = {c: xbrl_quarterly(facts, c) for c in
                  ("revenue", "ebit", "capex", "dep", "inventory",
                   "ppe_gross", "accum_dep", "ppe_net", "cash", "debt", "shares")}
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

    back = min(len(idx), 252)
    abs_12m = 100.0 * (idx[-1][1] / idx[-back][1] - 1.0)
    dd = 100.0 * (1.0 - idx[-1][1] / max(v for _, v in idx[-252:]))

    rel = None
    if bench and len(bench) > 260:
        bn, bt = _price_on(bench, days[-1]), _price_on(bench, days[-back])
        if bn and bt:
            rel = abs_12m - 100.0 * (bn / bt - 1.0)
    return {"abs_12m": abs_12m, "rel_12m": rel, "drawdown": dd, "index": idx}


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
        if sid not in series_cache:
            series_cache[sid] = fred_series(sid)
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
        axes.a5_policy(theme, fr),
        axes.a6_capex(group, fc, fred),
        axes.a7_spread(fc, group, fred),
        axes.a8_inventory(fc, fred),
        axes.a9_bottleneck(fc, fred),
        axes.a10_substitution(),
    ]
    res.unpriced = [u1_fundamental_inflection(group), u2_valuation_gap(group),
                    u3_price_unreacted(px), u4_drawdown(px)]
    res.series = {
        "price_index": px.get("index", [])[-500:],
        "rev_yoy": group.get("rev_yoy_series", []),
        "capex_dep": group.get("capex_dep_series", []),
        "ev_ebit": group.get("ev_ebit_series", []),
        "n_companies": group.get("n_companies", 0),
        "n_customers": cust_fin.get("n_companies", 0),
    }
    return res
