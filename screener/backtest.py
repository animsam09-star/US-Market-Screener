"""백테스트 — 'N년 전에 이 도구를 돌렸다면 무엇을 골랐고, 그 뒤 실제로 올랐나'.

    python -m screener.backtest                  # 기본: 2019-09 ~ 가능한 최근
    python -m screener.backtest --start 2020-12

## 미래 정보 누출 방지 (이 파일의 존재 이유)

과거 시점 D 의 판정은 **D 에 실제로 알 수 있었던 것**만으로 만든다.
  - 주가          : D 이전 종가만
  - SEC 재무      : 접수일(filed) <= D 인 공시만 (xbrl_quarterly asof 컷)
  - FRED/EIA     : 발표 지연을 감안해 D − 45일까지의 관측치만
                    (M3 는 +5주, 산업생산 +2주 — 보수적으로 통일)
  - 동봉 스냅샷    : 사용 금지 (현재 데이터라 과거에 넣으면 그 자체가 누출)

재구성이 불가능한 축은 통째로 제외하고 그 사실을 결과에 표시한다:
  ③ 신기술(EDGAR 전문검색) · ⑤ 정책·예산(Federal Register/USAspending)
  · ⑩ 수입침투율(Census)

## 알려진 한계 (결과 문서에도 명시)

  - 생존 편향: 오늘의 티커 구성을 과거로 소급한다. 상폐·교체된 종목이 빠져
    수익률이 실제보다 좋게 나올 수 있다.
  - FRED 수정치: 최초 발표치가 아니라 수정이 반영된 현재 시계열을 쓴다.
  - 표본 중첩: 분기 스냅샷에 12개월 전망 창이라 관측이 독립이 아니다.
    비중첩(연 1회) 부분집합을 따로 보고한다.
"""
from __future__ import annotations

import argparse
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

from . import axes
from .axes import Signal, resolve_catalysts
from .net import FetchError
from .signals import (
    ThemeResult,
    _resolve_series,
    aggregate_financials,
    price_stats,
    u1_fundamental_inflection,
    u2_valuation_gap,
    u3_price_unreacted,
    u4_long_term,
    u5_basing,
)
from .sources import CONCEPTS, sec_company_facts, sec_ticker_map, xbrl_periods, yahoo_prices

ROOT = Path(__file__).resolve().parent.parent

FRED_LAG_DAYS = 45

# 과거 시점 재구성이 불가능한 축 — 조용히 빼지 않고 사유를 남긴다
EXCLUDED = {
    "A3": ("③ 신기술 확산", "백테스트 제외 — EDGAR 전문검색은 과거 시점 재구성 불가"),
    "A5": ("⑤ 정책·예산", "백테스트 제외 — Federal Register·USAspending 재구성 불가"),
    "A10": ("⑩ 대체(수입침투율)", "백테스트 제외 — Census 과거 재구성 미검증"),
}


def series_asof(series: list, when: date, lag_days: int = FRED_LAG_DAYS) -> list:
    """발표 지연을 감안한 시점 컷 — when 에 '이미 발표돼 있던' 관측치만."""
    cut = when - timedelta(days=lag_days)
    return [(d, v) for d, v in series if d <= cut]


def price_at(series: list, when: date, max_stale_days: int = 10) -> float | None:
    """when 시점(직전 거래일 포함)의 가격. 너무 낡은 마지막 값은 쓰지 않는다 —
    상폐 종목의 옛 종가를 '그 날 가격'으로 쓰면 죽은 종목이 살아있는 척 한다."""
    prior = [(d, v) for d, v in series if d <= when]
    if not prior:
        return None
    d, v = prior[-1]
    if (when - d).days > max_stale_days:
        return None
    return v


def forward_return(series: list, start: date, days: int) -> float | None:
    """start → start+days 수익률(%). 양끝 다 실제 가격이 있어야 한다."""
    p0 = price_at(series, start)
    p1 = price_at(series, start + timedelta(days=days))
    if not p0 or not p1:
        return None
    return 100.0 * (p1 / p0 - 1.0)


def spearman(pairs: list) -> float | None:
    """순위 상관 — 축 점수가 이후 수익률 순서를 맞히는지. scipy 없이 구현."""
    if len(pairs) < 8:
        return None

    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                rk[order[k]] = avg
            i = j + 1
        return rk

    xs = ranks([p[0] for p in pairs])
    ys = ranks([p[1] for p in pairs])
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
    return num / den if den else None


# ================================================================ 재구성 평가

@dataclass
class Ctx:
    tmap: dict
    prices: dict = field(default_factory=dict)      # ticker -> 전체 시계열
    bench: list = field(default_factory=list)
    series: dict = field(default_factory=dict)      # FRED/EIA sid -> 시계열 or 예외
    percache: dict = field(default_factory=dict)    # ticker -> {개념: 원시 기간}


def _cut(prices: dict, tickers: list, when: date) -> dict:
    return {t: [(d, v) for d, v in (prices.get(t) or []) if d <= when]
            for t in tickers}


def _fred_at(ctx: Ctx, when: date):
    def f(sid):
        s = ctx.series.get(sid)
        if s is None:
            try:
                s = _resolve_series(sid)
            except Exception as e:      # EIA 키 없음 등 — 시점마다 재시도하지 않는다
                s = FetchError(f"{sid}: {e}")
            ctx.series[sid] = s
        if isinstance(s, Exception):
            raise s
        out = series_asof(s, when)
        if not out:
            raise FetchError(f"{sid}: {when} 시점에 발표된 관측치 없음")
        return out
    return f


def evaluate_asof(theme: dict, when: date, ctx: Ctx) -> ThemeResult:
    """운영 evaluate_theme 과 같은 축 함수를 쓰되, 입력을 전부 시점 컷한다."""
    tickers = [t.upper() for t in theme["tickers"]]
    asof = when.isoformat()
    r = ThemeResult(name=theme["name"], thesis=theme.get("thesis", ""),
                    tickers=tickers)
    r.claimed, _ = resolve_catalysts(theme.get("catalysts") or [])

    fred = _fred_at(ctx, when)
    pcut = _cut(ctx.prices, tickers, when)
    bench = [(d, v) for d, v in ctx.bench if d <= when]
    group, _ = aggregate_financials(tickers, ctx.tmap, pcut, asof=asof,
                                    percache=ctx.percache)
    px = price_stats(tickers, pcut, bench)

    cust_cfg = theme.get("customers") or {}
    ct = [t.upper() for t in (cust_cfg.get("tickers") or [])]
    cust_fin: dict = {}
    if ct:
        cust_fin, _ = aggregate_financials(ct, ctx.tmap, _cut(ctx.prices, ct, when),
                                           asof=asof, percache=ctx.percache)

    fc = theme.get("fred", {})

    def excl(key):
        label, why = EXCLUDED[key]
        return Signal(key, label, None, "nodata", "", why)

    r.catalyst = [
        axes.a1_downstream(cust_cfg, group, fc, fred),
        axes.a2_supply(fc, fred),
        excl("A3"),
        axes.a4_replacement(cust_fin),
        excl("A5"),
        axes.a6_capex(group, fc, fred),
        axes.a7_spread(fc, group, fred),
        axes.a8_inventory(fc, fred),
        axes.a9_bottleneck(fc, fred),
        excl("A10"),
    ]
    r.unpriced = [u1_fundamental_inflection(group), u2_valuation_gap(group),
                  u3_price_unreacted(px), u4_long_term(px), u5_basing(px)]
    r.rebound = bool(px.get("rebound"))
    return r


def latest_earnings_before(dates: list, when: date,
                           max_age_days: int = 120) -> date | None:
    """스냅샷 시점에 '알 수 있었던' 가장 최근 실적발표일.

    발표일 자체는 과거에도 사실이지만 D 이후 발표는 미래 정보다.
    120일 넘은 발표는 다음 발표가 이미 지났어야 하는 낡은 신호라 무효.
    """
    prior = [d for d in dates if d <= when and (when - d).days <= max_age_days]
    return max(prior) if prior else None


def run_pead(start: date, end: date | None = None) -> dict:
    """실적반응(PEAD) 신호의 예측력 검증 — 점수 편입 여부를 결정하는 근거.

    각 분기말 D 에: 직전 실적발표(≤D)의 시장 반응(발표 전일→후일, SPY 차감)을
    재고, 이후 6·12개월 종목 상대수익률과의 순위 상관(IC)·상하위 스프레드를
    본다. 관측 단위는 종목-분기(테마가 아니라 종목 수준 신호라서).
    """
    import yaml as _yaml

    from .signals import earnings_reaction
    from .sources import sec_earnings_dates

    cfg = _yaml.safe_load((ROOT / "themes.yaml").read_text(encoding="utf-8"))
    tickers = sorted({t.upper() for th in cfg.get("themes", [])
                      for t in th["tickers"]})
    bench_tkr = cfg.get("benchmark", "SPY")
    today = date.today()
    last = end or (today - timedelta(days=380))

    tmap = sec_ticker_map()
    bench = yahoo_prices(bench_tkr, "max")
    snaps = quarter_ends(start, last)
    print(f"PEAD 검증: 종목 {len(tickers)} × 스냅샷 {len(snaps)}", flush=True)

    recs = []
    for t in tickers:
        cik = tmap.get(t)
        if not cik:
            continue
        try:
            px = yahoo_prices(t, "max")
            eds = sec_earnings_dates(cik, 40)
        except Exception as e:
            print(f"  [주의] {t}: {type(e).__name__}: {e}")
            continue
        for d in snaps:
            e0 = latest_earnings_before(eds, d)
            if e0 is None:
                continue
            react = earnings_reaction([p for p in px if p[0] <= d],
                                      [b for b in bench if b[0] <= d], e0)
            if react is None:
                continue
            f6 = forward_return(px, d, 182)
            f12 = forward_return(px, d, 365)
            b6 = forward_return(bench, d, 182)
            b12 = forward_return(bench, d, 365)
            recs.append({"ticker": t, "date": d.isoformat(), "react": react,
                         "fwd6": (f6 - b6) if None not in (f6, b6) else None,
                         "fwd12": (f12 - b12) if None not in (f12, b12) else None})
    return {"records": recs}


def analyze_pead(recs: list) -> dict:
    out = {}
    for k in ("fwd6", "fwd12"):
        pairs = [(r["react"], r[k]) for r in recs if r.get(k) is not None]
        ic = spearman(pairs)
        top = bot = None
        if len(pairs) >= 30:
            srt = sorted(pairs)
            n3 = len(srt) // 3
            bot = statistics.fmean(v for _, v in srt[:n3])
            top = statistics.fmean(v for _, v in srt[-n3:])
        out[k] = {"ic": ic, "n": len(pairs), "top3rd": top, "bot3rd": bot}
    return out


# ================================================================ 실행

def quarter_ends(start: date, end: date) -> list[date]:
    out = []
    y, m = start.year, ((start.month - 1) // 3 + 1) * 3
    while True:
        d = date(y, m, {3: 31, 6: 30, 9: 30, 12: 31}[m])
        if d > end:
            return out
        if d >= start:
            out.append(d)
        m += 3
        if m > 12:
            y, m = y + 1, 3


def theme_forward(ctx: Ctx, tickers: list, when: date, days: int) -> float | None:
    """테마 등가중 수익률 − 벤치마크 수익률 (%p)."""
    rets = [forward_return(ctx.prices.get(t) or [], when, days) for t in tickers]
    rets = [x for x in rets if x is not None]
    b = forward_return(ctx.bench, when, days)
    if not rets or b is None:
        return None
    return statistics.fmean(rets) - b


def run(start: date, end: date | None = None) -> dict:
    from .dashboard import _verdict, rank_score

    cfg = yaml.safe_load((ROOT / "themes.yaml").read_text(encoding="utf-8"))
    themes = cfg.get("themes", [])
    bench_tkr = cfg.get("benchmark", "SPY")
    today = date.today()
    # 12개월 전방 수익률이 완결되는 마지막 스냅샷까지만
    last = end or (today - timedelta(days=380))

    print("티커→CIK 매핑…", flush=True)
    ctx = Ctx(tmap=sec_ticker_map())
    ctx.bench = yahoo_prices(bench_tkr, "max")

    all_tickers: set[str] = set()
    for th in themes:
        all_tickers |= {t.upper() for t in th["tickers"]}
        all_tickers |= {t.upper() for t in (th.get("customers", {}) or {}).get("tickers", [])}
    print(f"주가 수집(전체 이력) {len(all_tickers)}종목…", flush=True)
    for t in sorted(all_tickers):
        try:
            ctx.prices[t] = yahoo_prices(t, "max")
        except Exception as e:      # 종목 하나가 전체 실행을 죽이면 안 된다
            print(f"  [주의] {t}: {type(e).__name__}: {e}")

    # SEC facts 는 티커당 수 MB — 파싱은 여기서 한 번만 하고 경량 구조로 보관
    print(f"SEC 재무 수집·경량화 {len(all_tickers)}종목…", flush=True)
    for t in sorted(all_tickers):
        cik = ctx.tmap.get(t)
        if not cik:
            continue
        try:
            facts = sec_company_facts(cik)
            ctx.percache[t] = {c: xbrl_periods(facts, c) for c in CONCEPTS}
            del facts
        except Exception as e:
            print(f"  [주의] {t}: {type(e).__name__}: {e}")

    snaps = quarter_ends(start, last)
    print(f"스냅샷 {len(snaps)}개 × 테마 {len(themes)}개", flush=True)

    records: list[dict] = []
    for i, d in enumerate(snaps, 1):
        print(f"[{i}/{len(snaps)}] {d} …", flush=True)
        for th in themes:
            try:
                r = evaluate_asof(th, d, ctx)
            except Exception as e:
                print(f"    {th['name']} 실패: {type(e).__name__}: {e}")
                continue
            tag, _cls, _txt = _verdict(r)
            tickers = [t.upper() for t in th["tickers"]]
            rec = {
                "date": d.isoformat(), "theme": th["name"], "verdict": tag,
                "thesis_status": r.thesis_status,
                "catalyst": r.catalyst_score, "unpriced": r.unpriced_score,
                "rank": rank_score(r), "rebound": r.rebound,
                "gate": r.gate_passed,
                "axes": {s.key: s.effective for s in r.catalyst
                         if s.effective is not None},
                "uaxes": {s.key: s.score for s in r.unpriced
                          if s.score is not None},
                "fwd6": theme_forward(ctx, tickers, d, 182),
                "fwd12": theme_forward(ctx, tickers, d, 365),
            }
            records.append(rec)
    return {"records": records, "snapshots": [d.isoformat() for d in snaps],
            "benchmark": bench_tkr}


# ================================================================ 분석·보고

def _grp(records, keyfn):
    g: dict = {}
    for r in records:
        g.setdefault(keyfn(r), []).append(r)
    return g


def _stats(rs, k="fwd12"):
    v = [r[k] for r in rs if r.get(k) is not None]
    if not v:
        return None
    return {"n": len(v), "mean": statistics.fmean(v), "median": statistics.median(v),
            "hit": 100.0 * sum(1 for x in v if x > 0) / len(v)}


def analyze(result: dict) -> dict:
    records = result["records"]
    judged = [r for r in records if r["verdict"] != "판정 불가"]

    by_verdict = {k: _stats(v) for k, v in _grp(judged, lambda r: r["verdict"]).items()}
    by_verdict_6 = {k: _stats(v, "fwd6")
                    for k, v in _grp(judged, lambda r: r["verdict"]).items()}

    # 비중첩(연 1회, 12월 스냅샷) — 중첩 표본의 착시 점검용
    yearly = [r for r in judged if r["date"][5:7] == "12"]
    by_verdict_y = {k: _stats(v) for k, v in _grp(yearly, lambda r: r["verdict"]).items()}

    # 축별 유효성: 축 점수와 이후 12개월 상대수익률의 순위 상관
    axis_ic: dict = {}
    for group_key, sub in (("axes", "A"), ("uaxes", "U")):
        keys = sorted({k for r in records for k in r[group_key]})
        for k in keys:
            pairs = [(r[group_key][k], r["fwd12"]) for r in records
                     if k in r[group_key] and r.get("fwd12") is not None]
            axis_ic[k] = {"ic": spearman(pairs), "n": len(pairs)}

    by_rebound = {("되돌림" if k else "일반"): _stats(v)
                  for k, v in _grp(judged, lambda r: r["rebound"]).items()}

    # 종합점수 상/하위 절반 비교
    ranked = sorted((r for r in judged if r.get("fwd12") is not None),
                    key=lambda r: r["rank"], reverse=True)
    half = len(ranked) // 2
    top_bot = {"상위절반": _stats(ranked[:half]), "하위절반": _stats(ranked[half:])}

    return {"by_verdict": by_verdict, "by_verdict_6": by_verdict_6,
            "by_verdict_yearly": by_verdict_y, "axis_ic": axis_ic,
            "by_rebound": by_rebound, "top_bot": top_bot,
            "n_records": len(records), "n_judged": len(judged)}


AXIS_NAMES = {
    "A1": "① 낙수(전방수요)", "A2": "② 공급 비탄력", "A4": "④ 교체 주기",
    "A6": "⑥ 캐펙스 사이클", "A7": "⑦ 스프레드", "A8": "⑧ 재고 사이클",
    "A9": "⑨ 병목·수주잔고",
    "U1": "U1 실적 변곡", "U2": "U2 밸류에이션 여유", "U3": "U3 주가 미반응",
    "U4": "U4 장기 미반영(3년)", "U5": "U5 바닥 다지기",
}

VORDER = ["볼 만함", "이미 반영", "되돌림", "이유 약함", "지금은 아님"]


def _fmt_group(d: dict | None) -> str:
    if not d:
        return "— | — | — | —"
    return (f"{d['n']} | {d['mean']:+.1f}%p | {d['median']:+.1f}%p | "
            f"{d['hit']:.0f}%")


def write_report(result: dict, ana: dict, path_md: Path, path_html: Path) -> None:
    today = date.today().isoformat()
    snaps = result["snapshots"]
    lines = [
        "# 백테스트 결과 — 판정이 실제로 맞았는가",
        "",
        f"생성 {today} · 스냅샷 {len(snaps)}개 ({snaps[0]} ~ {snaps[-1]}, 분기마다) · "
        f"관측 {ana['n_records']}건(판정 가능 {ana['n_judged']}건) · "
        f"벤치마크 {result['benchmark']} 대비 상대수익률",
        "",
        "각 분기말에 '그 시점에 알 수 있었던 데이터만으로' 도구를 돌려 판정을 만들고,",
        "이후 6·12개월 상대수익률을 붙였다. 미래 정보 컷: SEC 접수일, 통계 발표 지연 45일,",
        "주가 시점 컷. ③신기술·⑤정책·⑩수입침투는 과거 재구성이 불가능해 제외했다.",
        "",
        "## 1. 판정별 이후 12개월 상대수익률",
        "",
        "| 판정 | n | 평균 | 중앙값 | 승률(>0) |",
        "|---|---|---|---|---|",
    ]
    for tag in VORDER:
        if tag in ana["by_verdict"]:
            lines.append(f"| {tag} | {_fmt_group(ana['by_verdict'][tag])} |")
    lines += [
        "",
        "판정 체계가 유효하려면 '볼 만함'이 '지금은 아님'보다 확실히 높아야 한다.",
        "",
        "### 6개월 전망",
        "",
        "| 판정 | n | 평균 | 중앙값 | 승률 |",
        "|---|---|---|---|---|",
    ]
    for tag in VORDER:
        if tag in ana["by_verdict_6"]:
            lines.append(f"| {tag} | {_fmt_group(ana['by_verdict_6'][tag])} |")
    lines += [
        "",
        "### 비중첩 표본(연 1회, 12월 스냅샷만) — 중첩 착시 점검",
        "",
        "| 판정 | n | 평균 | 중앙값 | 승률 |",
        "|---|---|---|---|---|",
    ]
    for tag in VORDER:
        if tag in ana["by_verdict_yearly"]:
            lines.append(f"| {tag} | {_fmt_group(ana['by_verdict_yearly'][tag])} |")
    lines += [
        "",
        "## 2. 축별 예측력 (IC = 축 점수와 이후 12개월 수익률의 순위 상관)",
        "",
        "| 축 | IC | n | 해석 |",
        "|---|---|---|---|",
    ]
    for k in ["A1", "A2", "A4", "A6", "A7", "A8", "A9",
              "U1", "U2", "U3", "U4", "U5"]:
        d = ana["axis_ic"].get(k)
        if not d or d["ic"] is None:
            lines.append(f"| {AXIS_NAMES.get(k, k)} | — | {d['n'] if d else 0} | 표본 부족 |")
            continue
        ic = d["ic"]
        verdictw = ("예측력 있음" if ic >= 0.15 else
                    "약함" if ic >= 0.05 else
                    "소음 수준" if ic > -0.05 else "역방향(주의)")
        lines.append(f"| {AXIS_NAMES.get(k, k)} | {ic:+.2f} | {d['n']} | {verdictw} |")
    lines += [
        "",
        "IC +0.15 이상이면 실전 팩터 수준의 예측력이다. 0 근처는 소음, 음수는",
        "그 축의 방향 설정을 의심해야 한다.",
        "",
        "## 3. 되돌림 필터 검증",
        "",
        "| 구분 | n | 평균 | 중앙값 | 승률 |",
        "|---|---|---|---|---|",
    ]
    for k in ("일반", "되돌림"):
        if k in ana["by_rebound"]:
            lines.append(f"| {k} | {_fmt_group(ana['by_rebound'][k])} |")
    lines += [
        "",
        "되돌림으로 걸러낸 테마-시점의 이후 수익률이 일반보다 낮아야 필터가 유효하다.",
        "",
        "## 4. 종합점수(기하평균 랭크) 상·하위 절반",
        "",
        "| 구분 | n | 평균 | 중앙값 | 승률 |",
        "|---|---|---|---|---|",
        f"| 상위 절반 | {_fmt_group(ana['top_bot']['상위절반'])} |",
        f"| 하위 절반 | {_fmt_group(ana['top_bot']['하위절반'])} |",
        "",
        "## 5. 한계 — 이 숫자를 믿기 전에",
        "",
        "- **생존 편향**: 오늘의 티커 구성을 과거로 소급했다. 상폐·교체 종목이 빠져",
        "  수익률이 실제보다 좋게 나올 수 있다.",
        "- **FRED 수정치**: 최초 발표치가 아니라 수정 반영된 현재 시계열이다.",
        "- **표본 중첩**: 분기 스냅샷 × 12개월 창이라 관측이 독립이 아니다 —",
        "  1절의 비중첩 표가 안전판이다.",
        "- **③⑤⑩축 제외**: 정책·신기술이 주 촉매인 테마(방산 등)는 판정이",
        "  실전과 다르게 나온다.",
        "- 테마 정의 자체가 현재 버전이다(과거의 우리가 이 테마를 골랐으리란 보장 없음).",
    ]
    # PEAD 검증 결과가 있으면 함께 싣는다 — '검증했고 탈락했다'도 기록이다
    pead_p = ROOT / "reports" / "pead_backtest.json"
    if pead_p.exists():
        import json as _json
        try:
            pd_ = _json.loads(pead_p.read_text(encoding="utf-8"))
            a6, a12 = pd_["analysis"]["fwd6"], pd_["analysis"]["fwd12"]
            lines += [
                "",
                "## 6. 실적반응(PEAD) 신호 검증 — 편입 보류",
                "",
                f"종목-분기 {pd_['n']:,}건: 6개월 IC {a6['ic']:+.3f}, "
                f"12개월 IC {a12['ic']:+.3f} — 소음 수준(기준 +0.10).",
                f"상위⅓ vs 하위⅓ 12개월 스프레드 {a12['top3rd']:+.1f}%p vs "
                f"{a12['bot3rd']:+.1f}%p.",
                "분기 스냅샷 설계상 발표 후 최대 120일 낡은 신호가 섞여 PEAD 의",
                "단기(60일) 효과가 희석된 탓일 수 있으나, 현 설계에서 예측력이",
                "없으므로 점수에 넣지 않는다. 표시·진단용으로만 유지.",
            ]
        except Exception:
            pass
    md = "\n".join(lines) + "\n"
    path_md.write_text(md, encoding="utf-8")

    # 같은 내용을 배포 가능한 HTML 로
    rows_html = md.replace("&", "&amp;").replace("<", "&lt;")
    html = _MD_HTML.replace("__BODY__", rows_html)
    path_html.parent.mkdir(exist_ok=True)
    path_html.write_text(html, encoding="utf-8")


_MD_HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>백테스트 결과 — 미국 섹터 스크리너</title>
<style>
body{font-family:Pretendard,-apple-system,'Malgun Gothic',sans-serif;
max-width:860px;margin:40px auto;padding:0 20px;line-height:1.65;
color:#2b2b33;background:#faf9f7}
pre{white-space:pre-wrap;font:inherit}
a{color:#1c3d6e}
</style></head><body>
<p><a href="./">← 대시보드로</a></p>
<pre>__BODY__</pre>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2019-09-30")
    ap.add_argument("--end", default=None)
    ap.add_argument("--pead", action="store_true",
                    help="실적반응(PEAD) 신호 검증만 실행")
    args = ap.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else None

    if args.pead:
        import json
        res = run_pead(start, end)
        ana = analyze_pead(res["records"])
        (ROOT / "reports" / "pead_backtest.json").write_text(
            json.dumps({"analysis": ana, "n": len(res["records"])},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nPEAD 관측 {len(res['records'])}건 (종목-분기)")
        for k, d in ana.items():
            ic = f"{d['ic']:+.3f}" if d["ic"] is not None else "—"
            spread = (f" 상위⅓ {d['top3rd']:+.1f}%p vs 하위⅓ {d['bot3rd']:+.1f}%p"
                      if d["top3rd"] is not None else "")
            print(f"  {k}: IC {ic} (n={d['n']}){spread}")
        return 0
    result = run(start, end)
    if not result["records"]:
        print("관측 0건 — 데이터 수집 실패 여부를 확인하세요")
        return 1
    ana = analyze(result)
    write_report(result, ana, ROOT / "백테스트_결과.md",
                 ROOT / "reports" / "backtest.html")

    import json
    (ROOT / "reports" / "backtest_records.json").write_text(
        json.dumps(result["records"], ensure_ascii=False, indent=1),
        encoding="utf-8")
    # 대시보드가 축 옆에 '검증됨/역방향' 배지를 달 때 읽는다
    (ROOT / "reports" / "axis_ic.json").write_text(
        json.dumps({k: v for k, v in ana["axis_ic"].items()},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n완료 — 관측 {ana['n_records']}건")
    print(f"  백테스트_결과.md / reports/backtest.html / reports/backtest_records.json")
    for tag in VORDER:
        d = ana["by_verdict"].get(tag)
        if d:
            print(f"  {tag}: n={d['n']} 12M 평균 {d['mean']:+.1f}%p 승률 {d['hit']:.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
