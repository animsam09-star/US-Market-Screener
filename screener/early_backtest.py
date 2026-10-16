"""초기 신호 적중 기록 — '방향이 바뀌는 순간' 신호가 과거에 켜졌을 때, 그 뒤 실제로 올랐나.

    python -m screener.early_backtest              # 2010-01 ~ 가능한 최근
    python -m screener.early_backtest --start 2015-01-31

사용자 지정(2026-10-16): "난 '미리' 아는 게 중요해. 틀려도 되니까 가능성이
보이는 걸 알려주는 게 최우선". 초기 신호는 판정과 별도로 화면 상단에 뜬다.
그런데 '검증 전'이라고만 적어 두면 어느 신호를 믿을지 알 수 없다. 이 파일은
신호별로 과거 몇 번 켜졌고 켜진 뒤 1년 동안 시장(SPY)보다 더 올랐는지 센다.

## 방법

  - 매달 말, 그 시점에 **실제로 알 수 있던 자료만** 잘라(backtest.py 와 같은 규칙:
    주가는 그날까지, FRED/EIA 는 발표 지연 45일, SEC 재무는 접수일 기준)
    대시보드와 **같은 함수**(dashboard._early_signals)로 신호를 다시 계산한다.
  - '켜짐' 사건 = 지난달엔 꺼져 있다가 이번 달 켜진 것. 같은 테마에서 같은 신호가
    12개월 안에 다시 켜지면 같은 사건의 연장으로 보고 한 번만 센다(겹치는
    1년 창을 여러 번 세면 표본이 부풀려진다).
  - 결과 = 그 테마 종목 등가중 수익률 − SPY 수익률(6개월·1년).
  - 비교 기준 = 같은 기간 모든 테마·모든 달의 평균(신호와 상관없이 '평소').

## 한계 (화면에도 그대로 적는다)

  - 생존 편향: 오늘의 종목 구성을 과거로 소급한다.
  - FRED 수정치: 최초 발표치가 아니라 지금 시계열을 쓴다.
  - EIA 주간 자료(정유)는 로컬에 키가 없으면 빠진다 — 결과에 그 사실을 남긴다.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import date, timedelta

import yaml

from .insider import load_history as _ins_hist, window
from .backtest import ROOT, Ctx, _cut, _fred_at, last_complete_snapshot, theme_forward
from .signals import ThemeResult, aggregate_financials, price_stats
from .sources import CONCEPTS, sec_company_facts, sec_ticker_map, xbrl_periods, yahoo_prices

# 운영 evaluate_theme 과 같은 대응표 — 바뀌면 둘 다 바꾼다(테스트 F52 가 확인)
SERIES_KEYS = (("ppi_out", "ppi_output"), ("ppi_in", "ppi_input"),
               ("cap_util", "capacity_utilization"), ("inv", "inventories"),
               ("ship", "shipments"), ("orders", "new_orders"),
               ("ip", "industrial_production"))

INSIDER: list = []     # 과거 장내 매수(data/insider_hist.json) — run() 이 채운다
# 실물 신호 — 실제 경제 활동의 꺾임. 이것만 셀 때 예측력이 있었다(두 기간 모두).
FUND = ("재고 소진", "수주 반등", "생산·활동 반등", "가동률 바닥 탈출", "매출 가속 전환",
        "선행 지표 반등")
REARM_MONTHS = 12      # 같은 신호가 이 안에 다시 켜지면 같은 사건으로 본다
MIN_N = 8              # 이보다 적으면 '기록 적음'
SPLIT = date(2019, 1, 1)


def month_ends(start: date, end: date) -> list[date]:
    out = []
    y, m = start.year, start.month
    while True:
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        d = nxt - timedelta(days=1)
        if d > end:
            return out
        if d >= start:
            out.append(d)
        y, m = nxt.year, nxt.month


def load_ctx(themes: list, bench_tkr: str) -> Ctx:
    print("티커→CIK 매핑…", flush=True)
    ctx = Ctx(tmap=sec_ticker_map())
    ctx.bench = yahoo_prices(bench_tkr, "max")
    tick: set[str] = set()
    for th in themes:
        tick |= {t.upper() for t in th["tickers"]}
    print(f"주가·재무 수집 {len(tick)}종목…", flush=True)
    for t in sorted(tick):
        try:
            ctx.prices[t] = yahoo_prices(t, "max")
        except Exception as e:
            print(f"  [주의] 주가 {t}: {type(e).__name__}: {e}")
        cik = ctx.tmap.get(t)
        if not cik:
            continue
        try:
            facts = sec_company_facts(cik)
            ctx.percache[t] = {c: xbrl_periods(facts, c) for c in CONCEPTS}
            del facts
        except Exception as e:
            print(f"  [주의] 재무 {t}: {type(e).__name__}: {e}")
    return ctx


def theme_asof(theme: dict, when: date, ctx: Ctx) -> ThemeResult:
    """초기 신호 계산에 필요한 시계열만 그 시점 기준으로 재구성."""
    tickers = [t.upper() for t in theme["tickers"]]
    r = ThemeResult(name=theme["name"], thesis="", tickers=tickers)
    fred = _fred_at(ctx, when)
    fc = theme.get("fred", {}) or {}
    ser: dict = {}
    for k, key in SERIES_KEYS:
        if fc.get(key):
            try:
                ser[k] = list(fred(fc[key]))[-130:]
            except Exception:
                pass
    pcut = _cut(ctx.prices, tickers, when)
    bench = [(d, v) for d, v in ctx.bench if d <= when]
    px = price_stats(tickers, pcut, bench)
    group, _ = aggregate_financials(tickers, ctx.tmap, pcut, asof=when.isoformat(),
                                    percache=ctx.percache)
    lead = []
    for it in theme.get("early") or []:
        try:
            lead.append((it["name"], list(fred(it["id"]))[-130:]))
        except Exception:
            pass
    ser["lead"] = lead
    tk = set(tickers)
    ser["insider"] = window([b for b in INSIDER if b["ticker"] in tk], when)
    ser["price_index"] = (px.get("index") or [])[-500:]
    ser["rev_yoy"] = group.get("rev_yoy_series", [])
    r.series = ser
    # 예측력 개선 분석용 — 그때의 주가 위치(이미 올랐나·꺾였나)
    r.px_state = {k: px.get(k) for k in ("abs_12m", "rel_12m", "rel_3y", "vs_ma200", "drawdown")}
    return r


def run(start: date, end: date | None = None) -> dict:
    from .dashboard import _early_signals

    cfg = yaml.safe_load((ROOT / "themes.yaml").read_text(encoding="utf-8"))
    themes = cfg.get("themes", [])
    ctx = load_ctx(themes, cfg.get("benchmark", "SPY"))
    INSIDER[:] = _ins_hist()
    print(f"과거 내부자 매수 {len(INSIDER)}건", flush=True)
    last = end or last_complete_snapshot(date.today())
    months = month_ends(start, last)
    # 6개월 결과까지만 완결되는 최근 달도 넣는다(1년 결과는 None)
    if end is None:
        months += month_ends(last + timedelta(days=1), date.today() - timedelta(days=192))
    print(f"{len(months)}개월 × 테마 {len(themes)}개", flush=True)

    missing: dict[str, str] = {}
    recs = []
    for i, d in enumerate(months, 1):
        if i % 12 == 1:
            print(f"[{i}/{len(months)}] {d}", flush=True)
        for th in themes:
            try:
                r = theme_asof(th, d, ctx)
            except Exception as e:
                print(f"    {th['name']} {d} 실패: {type(e).__name__}: {e}")
                continue
            tickers = [t.upper() for t in th["tickers"]]
            bcut = [v for dd, v in ctx.bench if dd <= d]
            mkt = (bcut[-1] / (sum(bcut[-200:]) / 200) - 1) * 100 if len(bcut) >= 200 else None
            recs.append({
                "date": d.isoformat(), "theme": th["name"],
                "on": [n for n, _ in _early_signals(r)],
                "px": {k: (round(v, 2) if isinstance(v, (int, float)) else v)
                       for k, v in (getattr(r, "px_state", None) or {}).items()},
                "mkt_ma200": round(mkt, 2) if mkt is not None else None,
                "fwd6": theme_forward(ctx, tickers, d, 182),
                "fwd12": theme_forward(ctx, tickers, d, 365) if d <= last else None,
            })
    for sid, s in ctx.series.items():
        if isinstance(s, Exception):
            missing[sid] = str(s)[:120]
    return {"records": recs, "missing_series": missing,
            "start": months[0].isoformat() if months else None,
            "end": months[-1].isoformat() if months else None}


# ================================================================ 분석

def _st(v: list[float]) -> dict | None:
    v = [x for x in v if x is not None]
    if not v:
        return None
    return {"n": len(v), "mean": round(statistics.fmean(v), 2),
            "median": round(statistics.median(v), 2),
            "hit": round(100.0 * sum(1 for x in v if x > 0) / len(v), 1)}


def _mgap(a: str, b: str) -> int:
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


COMBO = "신호 2개 이상 동시"


def events(records: list[dict]) -> list[dict]:
    """'켜짐' 사건 목록 — 지난달 꺼짐 → 이번 달 켜짐, 12개월 재점등 제외."""
    by_theme: dict[str, list[dict]] = {}
    for r in records:
        by_theme.setdefault(r["theme"], []).append(r)
    out = []
    for th, rs in by_theme.items():
        rs.sort(key=lambda r: r["date"])
        last_ev: dict[str, str] = {}
        prev_on: set = set()
        prev_n = 0
        for r in rs:
            on = set(r["on"])
            names = [n for n in sorted(on) if n not in prev_on]
            if len(on) >= 2 and prev_n < 2:
                names.append(COMBO)
            for n in names:
                le = last_ev.get(n)
                if le and _mgap(le, r["date"]) < REARM_MONTHS:
                    continue
                last_ev[n] = r["date"]
                out.append({"theme": th, "date": r["date"], "signal": n,
                            "with": sorted(on), "fwd6": r["fwd6"], "fwd12": r["fwd12"]})
            prev_on, prev_n = on, len(on)
    out.sort(key=lambda e: (e["date"], e["theme"]))
    return out


def grade(s: dict | None, base: dict | None, robust: bool) -> str:
    if not s or s["n"] < MIN_N or not base:
        return "기록 적음"
    if s["hit"] >= base["hit"] + 8 and s["mean"] >= base["mean"] + 3 and robust:
        return "잘 맞았음"
    if s["hit"] >= base["hit"] and s["mean"] > base["mean"]:
        return "조금 나음"
    return "평소와 비슷"


def tier_of(fund_now: set, fund_prev: set, mkt_ma200) -> str | None:
    """강도 단계 — 화면과 백테스트가 같은 규칙을 쓴다(dashboard 가 import)."""
    if not fund_now:
        return None
    if len(fund_now) >= 2:
        return "실물 2개 이상"
    if mkt_ma200 is not None and mkt_ma200 < 0:
        return "시장 약세 중 실물 신호"
    if fund_now & fund_prev:
        return "실물 신호 이어짐"
    return "실물 신호 막 켜짐"


# 순서 = 과거 성적 순(2026-10-16: 65% · 65% · 56% · 52%, 평소 52%)
TIERS = ("실물 2개 이상", "시장 약세 중 실물 신호", "실물 신호 이어짐", "실물 신호 막 켜짐")


def tier_stats(recs: list[dict]) -> dict:
    """테마×달 관측을 강도 단계로 나눠 1년 뒤 성적(전체·앞·뒤 기간)."""
    by: dict[str, list] = {}
    for r in recs:
        by.setdefault(r["theme"], []).append(r)
    lab: dict[str, list] = {t: [] for t in TIERS}
    for rs in by.values():
        rs.sort(key=lambda r: r["date"])
        prev: set = set()
        for r in rs:
            now = set(r["on"]) & set(FUND)
            t = tier_of(now, prev, r.get("mkt_ma200"))
            if t:
                lab[t].append(r)
            prev = now
    out = {}
    for t, rs in lab.items():
        out[t] = {"all": _st([r["fwd12"] for r in rs]),
                  "early": _st([r["fwd12"] for r in rs if r["date"] < SPLIT.isoformat()]),
                  "late": _st([r["fwd12"] for r in rs if r["date"] >= SPLIT.isoformat()])}
    return out


def analyze(result: dict) -> dict:
    recs = result["records"]
    evs = events(recs)
    base12 = _st([r["fwd12"] for r in recs])
    base6 = _st([r["fwd6"] for r in recs])
    early_b = _st([r["fwd12"] for r in recs if r["date"] < SPLIT.isoformat()])
    late_b = _st([r["fwd12"] for r in recs if r["date"] >= SPLIT.isoformat()])
    sigs: dict[str, dict] = {}
    for name in sorted({e["signal"] for e in evs}):
        es = [e for e in evs if e["signal"] == name]
        s12 = _st([e["fwd12"] for e in es])
        s6 = _st([e["fwd6"] for e in es])
        a = _st([e["fwd12"] for e in es if e["date"] < SPLIT.isoformat()])
        b = _st([e["fwd12"] for e in es if e["date"] >= SPLIT.isoformat()])
        robust = bool(a and b and early_b and late_b
                      and a["mean"] > early_b["mean"] and b["mean"] > late_b["mean"])
        sigs[name] = {"n_events": len(es), "fwd12": s12, "fwd6": s6,
                      "early": a, "late": b, "robust": robust,
                      "grade": grade(s12, base12, robust),
                      "themes": len({e["theme"] for e in es})}
    return {"generated": date.today().isoformat(),
            "period": [result.get("start"), result.get("end")],
            "split": SPLIT.isoformat(), "rearm_months": REARM_MONTHS, "min_n": MIN_N,
            "base": {"fwd12": base12, "fwd6": base6, "early": early_b, "late": late_b,
                     "n_obs": len(recs)},
            "signals": sigs, "fund": list(FUND), "tiers": tier_stats(recs),
            "missing_series": result.get("missing_series", {})}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2010-01-31")
    ap.add_argument("--end", default=None)
    ap.add_argument("--reanalyze", action="store_true",
                    help="재계산 없이 cache/early_records.json 으로 통계만 다시")
    args = ap.parse_args()
    if args.reanalyze:
        from .net import CACHE_DIR
        recs = json.loads((CACHE_DIR / "early_records.json").read_text(encoding="utf-8"))
        old = json.loads((ROOT / "reports" / "early_signal_stats.json").read_text(encoding="utf-8"))
        res = {"records": recs, "missing_series": old.get("missing_series", {}),
               "start": recs[0]["date"] if recs else None,
               "end": max(r["date"] for r in recs) if recs else None}
    else:
        res = run(date.fromisoformat(args.start),
                  date.fromisoformat(args.end) if args.end else None)
    if not res["records"]:
        print("관측 0건 — 데이터 수집 실패")
        return 1
    ana = analyze(res)
    rep = ROOT / "reports"
    rep.mkdir(exist_ok=True)
    (rep / "early_signal_stats.json").write_text(
        json.dumps(ana, ensure_ascii=False, indent=1), encoding="utf-8")
    # 분석용 전체 관측(테마×달, 켜진 신호·주가 위치·결과) — 저장소 밖(cache)
    if not args.reanalyze:
        from .net import CACHE_DIR
        (CACHE_DIR / "early_records.json").write_text(
            json.dumps(res["records"], ensure_ascii=False), encoding="utf-8")
    (rep / "early_signal_events.json").write_text(
        json.dumps(events(res["records"]), ensure_ascii=False, indent=0), encoding="utf-8")
    b = ana["base"]["fwd12"]
    print(f"\n평소(모든 테마·달): 1년 뒤 시장 대비 평균 {b['mean']:+.1f}%p, "
          f"더 오른 비율 {b['hit']:.0f}% (n={b['n']})")
    for n, s in sorted(ana["signals"].items(), key=lambda kv: -(kv[1]["fwd12"] or {}).get("mean", -99)):
        f = s["fwd12"]
        if f:
            print(f"  {n}: {s['n_events']}번 → 평균 {f['mean']:+.1f}%p, 더 오른 비율 "
                  f"{f['hit']:.0f}% [{s['grade']}]")
    if ana["missing_series"]:
        print(f"  빠진 시계열 {len(ana['missing_series'])}개: "
              + ", ".join(list(ana["missing_series"])[:6]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
