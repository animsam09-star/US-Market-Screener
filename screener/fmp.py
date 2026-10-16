"""FMP(Financial Modeling Prep) — 애널리스트 추정치·목표주가.

왜: 실적 추정치가 올라가기 시작하는 것(추정치 상향)은 주가보다 먼저 나타나는
대표적 선행 신호다. FMP 무료 등급은 하루 250회라, 같은 값을 3일 캐시하고 한 번
실행에 새로 부르는 횟수를 제한한다(실행당 110회 — 두 자료 × 종목 약 170개를
2~3번 실행에 나눠 갱신).

  - 목표주가 요약(price-target-summary): 최근 1개월 평균 목표주가 vs 최근 분기
    평균 — 바로 쓸 수 있다.
  - 추정치(analyst-estimates): 다음 회계연도 EPS 평균. 과거 추정치를 주지 않으므로
    매 실행 reports/estimates_history.jsonl 에 쌓고 약 한 달 전과 비교한다
    (그래서 첫 비교는 기록 시작 약 한 달 뒤부터).

키는 GitHub 시크릿 FMP_API_KEY 또는 fmp_key.txt(저장소 제외)에만 둔다.
"""
from __future__ import annotations

import json
import time
import urllib.parse
from datetime import date
from pathlib import Path

from .keys import load_key
from .net import FetchError, fetch_json, is_fresh

ROOT = Path(__file__).resolve().parent.parent
EST_HIST = ROOT / "reports" / "estimates_history.jsonl"
BASE = "https://financialmodelingprep.com/stable"
TTL_H = 72
BUDGET = {"left": 110}
# 배포본 진단용(페이지 숨은 표식) — 키 유무·자료별 성공/빈 응답/실패와 첫 실패 사유
STAT = {"key": None, "est_ok": 0, "est_empty": 0, "est_err": 0,
        "pt_ok": 0, "pt_empty": 0, "pt_err": 0, "skipped": 0, "why": ""}


def fmp_key() -> str | None:
    return load_key("FMP_API_KEY", "fmp_key.txt", "FMP_API", "FMP")


def _get(path: str, params: dict, kind: str):
    k = fmp_key()
    STAT["key"] = bool(k)
    if not k:
        return None
    q = urllib.parse.urlencode({**params, "apikey": k})
    url = f"{BASE}/{path}?{q}"
    if STAT.get(f"{kind}_off"):
        return None                       # 이번 실행에서 막힌 것으로 판정 — 하루 한도를 아낀다
    if not is_fresh(url, TTL_H):
        if BUDGET["left"] <= 0:
            STAT["skipped"] += 1
            return None
        BUDGET["left"] -= 1
        time.sleep(0.25)
    try:
        return fetch_json(url, ttl_hours=TTL_H, retries=1)
    except (FetchError, ValueError) as e:
        STAT[f"{kind}_err"] += 1
        msg = str(e).replace(k, "***")
        if "실패:" in msg:                  # 'URL 실패: HTTPError: 402 ...' → 사유만
            msg = msg.split("실패:", 1)[1]
        elif "apikey=" in msg:
            msg = msg.split("apikey=", 1)[0] + "…"
        STAT["why"] = STAT["why"] or f"{kind}: " + msg.strip()[:110]
        # 성공 없이 연속 3번 실패하면 이번 실행에선 그 자료를 끈다(유료 전용·키 오류 등)
        if STAT[f"{kind}_err"] >= 3 and not STAT[f"{kind}_ok"] and not STAT[f"{kind}_empty"]:
            STAT[f"{kind}_off"] = True
        return None


def _num(d: dict, *names):
    for n in names:
        v = d.get(n)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def parse_estimates(payload, today: date) -> tuple[str, float, int] | None:
    """다음 회계연도(아직 안 끝난 가장 가까운 연도)의 EPS 평균 추정치."""
    if not isinstance(payload, list):
        return None
    rows = []
    for e in payload:
        d = str(e.get("date") or "")[:10]
        eps = _num(e, "epsAvg", "estimatedEpsAvg")
        if not d or eps is None or d <= today.isoformat():
            continue
        n = int(_num(e, "numAnalystsEps", "numberAnalystsEstimatedEps") or 0)
        rows.append((d, eps, n))
    if not rows:
        return None
    return min(rows)          # 가장 가까운 미래 회계연도


def next_fy_eps(ticker: str, today: date | None = None):
    today = today or date.today()
    p = _get("analyst-estimates", {"symbol": ticker, "period": "annual",
                                   "page": 0, "limit": 10}, "est")
    if p is None:
        return None
    r = parse_estimates(p, today)
    STAT["est_ok" if r else "est_empty"] += 1
    return r


def parse_pt(payload) -> dict | None:
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, dict):
        return None
    out = {k: _num(payload, k) for k in ("lastMonthCount", "lastMonthAvgPriceTarget",
                                         "lastQuarterCount", "lastQuarterAvgPriceTarget")}
    if not out["lastQuarterAvgPriceTarget"]:
        return None
    return out


def pt_summary(ticker: str):
    p = _get("price-target-summary", {"symbol": ticker}, "pt")
    if p is None:
        return None
    r = parse_pt(p)
    STAT["pt_ok" if r else "pt_empty"] += 1
    return r


# ================================================================ 추정치 이력

_HIST: list | None = None


def load_est_history() -> list[dict]:
    global _HIST
    if _HIST is None:
        _HIST = []
        try:
            for line in EST_HIST.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    _HIST.append(json.loads(line))
        except Exception:
            pass
        _HIST.sort(key=lambda h: h.get("date", ""))
    return _HIST


def est_baseline(today: date, min_days: int = 25, max_days: int = 75) -> dict | None:
    """약 한 달 전 기록 — min_days~max_days 전 기록 중 가장 최근 것."""
    for h in reversed(load_est_history()):
        age = (today - date.fromisoformat(h["date"])).days
        if min_days <= age <= max_days:
            return h
    return None


def append_est_history(est: dict[str, list], today: date | None = None) -> None:
    """오늘 추정치 {티커: [회계연도말, EPS]} 를 한 줄로 쌓는다(같은 날은 덮어씀)."""
    if not est:
        return
    today = today or date.today()
    lines = []
    if EST_HIST.exists():
        lines = [l for l in EST_HIST.read_text(encoding="utf-8").splitlines()
                 if l.strip() and json.loads(l).get("date") != today.isoformat()]
    lines.append(json.dumps({"date": today.isoformat(), "est": est}, ensure_ascii=False))
    EST_HIST.parent.mkdir(exist_ok=True)
    EST_HIST.write_text("\n".join(lines) + "\n", encoding="utf-8")


def revisions(cur: dict[str, list], base: dict | None) -> list[tuple]:
    """[(티커, 옛 EPS, 지금 EPS, 기준일)] — 같은 회계연도끼리만 비교."""
    if not base:
        return []
    out = []
    for t, (fy, eps) in cur.items():
        old = (base.get("est") or {}).get(t)
        if old and old[0] == fy and old[1] not in (None, 0):
            out.append((t, float(old[1]), float(eps), base["date"]))
    return out
