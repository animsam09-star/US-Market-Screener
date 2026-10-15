"""HTML 대시보드 생성 — 외부 의존 없는 단일 파일."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path

from .signals import ThemeResult
from .sources import ticker_names

# SEC 등록명의 법인 접미("/DE/", "/MD/" 등 등록 주州 표기)는 화면에선 소음이다
NAMES = {k: re.sub(r"\s*/[A-Z]{2}/?\s*$", "", v).strip()
         for k, v in ticker_names().items()}

# dataviz 레퍼런스 팔레트의 검증된 상위 3슬롯을 값 변경 없이 사용.
# 리드타임 버킷이 정확히 3개라 all-pairs 게이트를 통과하는 범위 안에 있다.
BUCKETS = [
    ("단기", "3~9개월", "var(--series-1)"),
    ("중기", "6~18개월", "var(--series-2)"),
    ("장기", "12~36개월", "var(--series-3)"),
]


def bucket_of(lead: str) -> int:
    s = (lead or "").replace("M", "").replace("개월", "")
    try:
        hi = int(s.split("~")[-1])
    except Exception:
        return 1
    if hi <= 9:
        return 0
    if hi <= 18:
        return 1
    return 2


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _sparkline(points: list, width: int = 132, height: int = 30,
               color: str = "var(--series-1)") -> str:
    vals = [p[1] for p in points]
    if len(vals) < 3:
        return '<span class="nodata">—</span>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    step = width / (len(vals) - 1)
    pts = " ".join(
        f"{i * step:.1f},{height - 2 - (v - lo) / rng * (height - 4):.1f}"
        for i, v in enumerate(vals)
    )
    last_x = width
    last_y = height - 2 - (vals[-1] - lo) / rng * (height - 4)
    return (f'<svg class="spark" viewBox="0 0 {width + 3} {height}" width="{width + 3}" '
            f'height="{height}" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{last_x - 1:.1f}" cy="{last_y:.1f}" r="2.5" fill="{color}"/></svg>')


def _bar(score: float | None) -> str:
    if score is None:
        return '<div class="bar"><div class="barfill na"></div></div>'
    w = max(1.5, min(100.0, score))
    return f'<div class="bar"><div class="barfill" style="width:{w:.1f}%"></div></div>'


STATUS_TAG = {
    "ok": ("확증", "st-ok"),
    "unconfirmed": ("미확증", "st-warn"),
    "rejected": ("기각", "st-rej"),
    "nodata": ("데이터없음", "st-na"),
}


def _load_axis_ic() -> dict:
    """백테스트가 남긴 축별 예측력(IC). 없으면 배지 생략."""
    p = Path(__file__).resolve().parent.parent / "reports" / "axis_ic.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


AXIS_IC = _load_axis_ic()


def _ic_badge(key: str | None) -> str:
    """축 이름 옆 검증 배지 — 백테스트로 예측력이 확인됐는지.

    로드맵 1순위의 산출: '유효성 낮은 축은 예측력 미확인 표시'. 점수는 그대로
    두되(감으로 가중치를 바꾸면 과적합), 읽는 사람이 얼마나 믿을지 알게 한다.
    """
    d = AXIS_IC.get(key or "")
    if not d or d.get("ic") is None:
        return ""
    ic = d["ic"]
    if ic >= 0.15:
        return f'<span class="tag ic-ok" title="백테스트 IC {ic:+.2f}">검증 {ic:+.2f}</span>'
    if ic <= -0.10:
        return (f'<span class="tag ic-bad" title="백테스트 IC {ic:+.2f} — 점수가 높을수록 '
                f'이후 수익률이 낮았다">역방향 {ic:+.2f}</span>')
    return f'<span class="tag ic-na" title="백테스트 IC {ic:+.2f}">예측력 미확인</span>'


def _signal_rows(sigs, *, show_status: bool = True, claimed=None) -> str:
    """축별 행. 기각·미확증은 사유를 반드시 함께 보여준다.

    조용한 0점은 '신호가 약함'과 '논리가 틀림'을 구별하지 못하게 만든다.
    """
    rows = []
    for s in sigs:
        status = getattr(s, "status", "ok")
        eff = getattr(s, "effective", s.score)
        sc = "—" if eff is None else f"{eff:.0f}"
        cls = {"rejected": "rej", "nodata": "na", "unconfirmed": "warn"}.get(status, "")
        tag = ""
        if show_status:
            txt, tcls = STATUS_TAG.get(status, ("", ""))
            tag = f'<span class="tag {tcls}">{_e(txt)}</span>'
        lab = getattr(s, "evidence_label", "근거") or "근거"
        if lab == "근거":
            lab = "근거↗"
        ev = (f' <a class="ev" href="{_e(s.evidence)}" target="_blank" rel="noopener">'
              f'{_e(lab)}</a>' if s.evidence else "")
        reason = getattr(s, "reason", "")
        why = f'<div class="why">{_e(reason)}</div>' if reason else ""
        body = _e(s.detail) if s.detail else ""
        star = ('<span class="star">★</span>'
                if claimed and getattr(s, "key", None) in claimed else "")
        rows.append(
            f'<tr class="{cls}"><th scope="row">{star}{_e(s.label)}{tag}'
            f'{_ic_badge(getattr(s, "key", None))}</th>'
            f'<td class="bcell">{_bar(None if status in ("rejected", "nodata") else eff)}</td>'
            f'<td class="num">{sc}</td>'
            f'<td class="det">{body}{ev}{why}</td></tr>'
        )
    return "".join(rows)


def _scatter(results: list[ThemeResult]) -> str:
    """사분면 산점도 — 오른쪽 위가 '촉매는 강한데 아직 안 오른' 목표 구역."""
    pts = [r for r in results if r.catalyst_score is not None and r.unpriced_score is not None]
    if not pts:
        return '<p class="nodata">산점도를 그릴 데이터가 부족합니다.</p>'

    W, H = 760, 470
    PL, PR, PT, PB = 58, 26, 26, 52
    iw, ih = W - PL - PR, H - PT - PB

    def sx(v):
        return PL + v / 100 * iw

    def sy(v):
        return PT + (100 - v) / 100 * ih

    parts = [f'<svg class="scatter" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="촉매 점수 대비 미반영 점수 사분면 산점도">']

    # 목표 사분면 음영
    parts.append(f'<rect x="{sx(50):.0f}" y="{sy(100):.0f}" width="{iw / 2:.0f}" '
                 f'height="{ih / 2:.0f}" class="target-quad"/>')
    # 그리드
    for v in (0, 25, 50, 75, 100):
        parts.append(f'<line x1="{sx(v):.1f}" y1="{PT}" x2="{sx(v):.1f}" y2="{PT + ih}" class="grid"/>')
        parts.append(f'<line x1="{PL}" y1="{sy(v):.1f}" x2="{PL + iw}" y2="{sy(v):.1f}" class="grid"/>')
        parts.append(f'<text x="{sx(v):.1f}" y="{PT + ih + 18}" class="tick" text-anchor="middle">{v}</text>')
        parts.append(f'<text x="{PL - 10}" y="{sy(v) + 4:.1f}" class="tick" text-anchor="end">{v}</text>')
    # 중앙선
    parts.append(f'<line x1="{sx(50):.1f}" y1="{PT}" x2="{sx(50):.1f}" y2="{PT + ih}" class="mid"/>')
    parts.append(f'<line x1="{PL}" y1="{sy(50):.1f}" x2="{PL + iw}" y2="{sy(50):.1f}" class="mid"/>')

    parts.append(f'<text x="{PL + iw / 2:.0f}" y="{H - 12}" class="axlab" text-anchor="middle">'
                 f'촉매 점수 → (왜 오를 이유가 있나)</text>')
    parts.append(f'<text x="16" y="{PT + ih / 2:.0f}" class="axlab" text-anchor="middle" '
                 f'transform="rotate(-90 16 {PT + ih / 2:.0f})">미반영 점수 → (왜 아직 안 올랐나)</text>')
    parts.append(f'<text x="{sx(98):.0f}" y="{sy(97):.0f}" class="quadlab" text-anchor="end">'
                 f'목표 구역 — 이유 있고 가격 아직</text>')
    parts.append(f'<text x="{sx(98):.0f}" y="{sy(3):.0f}" class="quadlab dim" text-anchor="end">'
                 f'이미 반영됨</text>')
    parts.append(f'<text x="{sx(2):.0f}" y="{sy(97):.0f}" class="quadlab dim" text-anchor="start">'
                 f'눌렸지만 이유 약함</text>')
    parts.append(f'<text x="{sx(2):.0f}" y="{sy(3):.0f}" class="quadlab dim" text-anchor="start">'
                 f'지금은 아님</text>')

    # 라벨 충돌 회피 — 30개 테마에서 이름표가 겹쳐 읽을 수 없던 것(실측).
    # 이미 놓인 라벨 상자를 기억하고, 겹치면 위·아래로 한 줄씩 비켜 놓는다.
    placed: list[tuple[float, float, float, float]] = []

    def _label_y(x0, x1, y0):
        for dy in (0, -14, 14, -28, 28, -42, 42, -56, 56, -70, 70, -84, 84):
            yy = y0 + dy
            if all(x1 < a or x0 > b or yy < c - 12 or yy > d + 12
                   for a, b, c, d in placed):
                placed.append((x0, x1, yy - 6, yy + 6))
                return yy
        placed.append((x0, x1, y0 - 6, y0 + 6))
        return y0

    for r in sorted(pts, key=lambda r: -(r.unpriced_score or 0)):
        b = bucket_of(r.lead_time)
        x, y = sx(r.catalyst_score), sy(r.unpriced_score)
        gate = r.gate_passed
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{7 if gate >= 2 else 5.5}" '
            f'fill="{BUCKETS[b][2]}" class="pt{" gated" if gate >= 2 else ""}">'
            f'<title>{_e(r.name)} — 촉매 {r.catalyst_score:.0f} / 미반영 '
            f'{r.unpriced_score:.0f} / 게이트 {gate}개 통과</title></circle>')
        anchor = "end" if x > PL + iw * 0.72 else "start"
        dx = -11 if anchor == "end" else 11
        w = 13.5 * len(r.name) + 6
        x0, x1 = (x + dx - w, x + dx) if anchor == "end" else (x + dx, x + dx + w)
        ly = _label_y(x0, x1, y + 4)
        parts.append(f'<text x="{x + dx:.1f}" y="{ly:.1f}" class="ptlab" '
                     f'text-anchor="{anchor}">{_e(r.name)}</text>')

    parts.append("</svg>")

    legend = "".join(
        f'<span class="lg"><i style="background:{c}"></i>{_e(n)} <em>{_e(rng)}</em></span>'
        for n, rng, c in BUCKETS)
    # 좌표가 없는 테마를 조용히 빼면 "왜 없지"가 된다 — 사유와 함께 밝힌다.
    missing = [r for r in results if r not in pts]
    note = ""
    if missing:
        note = ('<p class="nodata" style="margin-top:6px">측정 불가로 제외: '
                + ", ".join(_e(r.name) for r in missing)
                + " — 촉매 또는 미반영 축의 데이터가 부족합니다(테마 카드 참조).</p>")
    return "".join(parts) + f'<div class="legend">{legend}</div>{note}'


def _card(r: ThemeResult, rank: int) -> str:
    b = bucket_of(r.lead_time)
    cs = "—" if r.catalyst_score is None else f"{r.catalyst_score:.0f}"
    us = "—" if r.unpriced_score is None else f"{r.unpriced_score:.0f}"
    gate = r.gate_passed
    gate_cls = "good" if gate >= 2 else ("warn" if gate == 1 else "bad")
    gate_txt = {0: "미통과", 1: "1개 통과", 2: "통과", 3: "통과", 4: "통과"}[min(gate, 4)]

    sp = r.series
    sparks = []
    for label, key, fmt in [("그룹 주가(동일가중)", "price_index", None),
                            ("TTM 매출 YoY %", "rev_yoy", None),
                            ("capex/감가상각", "capex_dep", None),
                            ("EV/EBIT", "ev_ebit", None)]:
        data = sp.get(key) or []
        val = ""
        if data:
            v = data[-1][1]
            val = f"{v:,.1f}" if abs(v) < 1e4 else f"{v:,.0f}"
        sparks.append(f'<div class="sp"><span class="splab">{_e(label)}</span>'
                      f'{_sparkline(data)}<span class="spval">{_e(val)}</span></div>')

    notes = ""
    if r.notes:
        notes = ('<details class="notes"><summary>데이터 한계 '
                 f'{len(r.notes)}건</summary><ul>'
                 + "".join(f"<li>{_e(n)}</li>" for n in r.notes) + "</ul></details>")

    tick_html = " · ".join(
        f'<span title="{_e(NAMES.get(t.upper(), ""))}">{_e(t)}</span>' for t in r.tickers)
    nc = sp.get("n_customers", 0)
    cust_txt = f" · 고객군 {nc}개사" if nc else " · 고객군 미지정"
    tops = r.top_axes
    vtag, vcls, vtext = _verdict(r)
    drivers = ("점수를 만든 축: "
               + " / ".join(f"<strong>{_e(s.label)}</strong> {s.effective:.0f}" for s in tops)
               ) if tops else "주장한 촉매 축이 전부 죽어 있음"

    # 논지 성립 여부 — 이 도구의 가장 중요한 출력.
    # "무엇이 마침 높나"가 아니라 "내가 말한 이유가 데이터로 서나"를 답한다.
    TH = {"성립": ("good", "논지 성립"), "미확증": ("warn", "논지 미확증"),
          "일부만 작동": ("warn", "논지 일부만 작동"),
          "일부기각": ("bad", "논지 일부 기각"), "일부확인불가": ("warn", "논지 일부 확인불가"),
          "성립하나 신호없음": ("warn", "반증 안 됐으나 신호 없음"),
          "미성립": ("bad", "논지 미성립"), "미선언": ("na", "촉매 미선언")}
    tcls, ttxt = TH.get(r.thesis_status, ("na", r.thesis_status))
    claim_names = " · ".join(s.label.split(" ", 1)[-1] for s in r.claimed_axes)
    thesis_line = (f'<p class="claim"><span class="verdict v-{tcls}">{_e(ttxt)}</span>'
                   f'<span class="claim-list">주장한 촉매: {_e(claim_names)}</span></p>')

    inc = r.incidental_axes
    inc_line = ""
    if inc:
        inc_line = ('<p class="incidental">예상 밖 촉매(순위 미반영): '
                    + " · ".join(f"{_e(s.label)} {s.effective:.0f}" for s in inc[:3])
                    + ' <em>— 논지에 없던 힘이 작동 중일 수 있다</em></p>')

    return f"""
<article class="card" id="t{rank}">
  <div class="chead">
    <div>
      <span class="rank">{rank}</span>
      <h3>{_e(r.name)}</h3>
      <span class="pill" style="--pc:{BUCKETS[b][2]}">{_e(BUCKETS[b][0])} · {_e(r.lead_time)}</span>
    </div>
    <div class="scores">
      <div class="sbox"><span>촉매</span><strong>{cs}</strong></div>
      <div class="sbox"><span>미반영</span><strong>{us}</strong></div>
      <div class="sbox gate {gate_cls}"><span>게이트</span><strong>{_e(gate_txt)}</strong></div>
    </div>
  </div>
  <p class="thesis">{_e(r.thesis)}</p>
  <p class="tick-list">{tick_html}
     <em>· SEC 재무 {sp.get('n_companies', 0)}개사{cust_txt} · 살아있는 축 {r.coverage:.0f}%
     · 기각 {r.n_rejected}개</em></p>
  <p class="verdict-line"><span class="vd {vcls}">{_e(vtag)}</span>{_e(vtext)}</p>
  {_history_line(r, vtag)}
  {inc_line}
  <details class="detail">
    <summary>근거 자세히 — 축별 판정과 원본 링크</summary>
    {thesis_line}
    <p class="drivers">{drivers}</p>
  <div class="sparks">{''.join(sparks)}</div>
  <div class="tables">
    <div>
      <h4>촉매 축 — 왜 오를 이유가 있나 <em>(★ 표시가 이 테마가 주장한 축)</em></h4>
      <table class="sig"><tbody>{_signal_rows(r.catalyst, claimed=r.claimed)}</tbody></table>
    </div>
    <div>
      <h4>미반영 축 — 왜 아직 안 올랐나</h4>
      <table class="sig"><tbody>{_signal_rows(r.unpriced, show_status=False)}</tbody></table>
    </div>
  </div>
  </details>
  {_stock_table(r)}
  {notes}
</article>"""


# 추천 우선순위. 점수보다 이게 먼저다 — 되돌림 종목이 '지금은 아님'보다
# 위에 오면 순서가 추천으로 읽히지 않는다.
VERDICT_ORDER = {
    "볼 만함": 0,      # 촉매도 있고 가격도 아직 — 주도 축이 안정 축
    "지켜볼 만": 1,    # 조건은 같지만 주도 축의 예측력이 시기 따라 뒤집힘
    "이미 반영": 2,    # 촉매는 맞지만 가격이 앞서감
    "이유 약함": 3,    # 눌렸지만 오를 근거 부족
    "지금은 아님": 4,
    "되돌림": 5,       # 과열 조정 — 명시적으로 피할 것
    "판정 불가": 6,
}

# '볼 만함' 게이트에 쓰는 안정 축: 백테스트에서 12M IC 가 전·후반 모두
# 양(+)으로 유지된 축(기준: 전체 IC > 0.15 이고 양 반기 모두 양수 —
# backtest.analyze 가 stable 플래그로 판정해 axis_ic.json 에 쓴다).
# A7 마진(+0.19/−0.24)·A8 재고(−0.20/+0.20)는 시기에 따라 부호가 뒤집혀,
# 이런 축이 촉매 최상위일 때 '볼 만함'은 승률 50%(동전 던지기)였다.
# 고정 목록이 아니라 백테스트를 다시 돌릴 때마다 최신 표본으로 재선정된다
# ("지금은 후반기인데 옛날 방식으로 하면 어떡해" 지적 반영). '최근 반기만
# 양수'는 안정으로 안 친다 — 12M 완결 지연 탓에 최근 레짐 IC 는 1년+ 늦게
# 도착하고, walk-forward 4변형 실측 전부 양반기 기준보다 나빴다.
_STABLE_FALLBACK = {"A1", "A2", "A9"}   # 2026-10-14 백테스트 400건 기준


def _stable_axes() -> set:
    s = {k for k, d in AXIS_IC.items() if isinstance(d, dict) and d.get("stable")}
    return s or set(_STABLE_FALLBACK)


STABLE_AXES = _stable_axes()


def _load_report_json(name: str):
    p = Path(__file__).resolve().parent.parent / "reports" / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# 판정별 백테스트 성적(n·평균·중앙·승률)과 관측 원장. 판정은 예측이 아니라
# 확률 진술이다 — 그 확률을 화면에 숫자로 보여준다("이 승률들도 써주고").
VERDICT_STATS: dict = _load_report_json("verdict_stats.json") or {}
BT_RECORDS: list = _load_report_json("backtest_records.json") or []
_POSITIVE_TAGS = ("볼 만함", "지켜볼 만")
_LOW_TAGS = ("이유 약함", "지금은 아님", "판정 불가", "되돌림")


def _rec_top1(rec: dict) -> str | None:
    ax = rec.get("axes") or {}
    return max(ax.items(), key=lambda kv: kv[1])[0] if ax else None


def _bt_stats(rs: list) -> dict | None:
    v = [x["fwd12"] for x in rs if x.get("fwd12") is not None]
    if not v:
        return None
    return {"n": len(v), "mean": sum(v) / len(v),
            "hit": 100.0 * sum(1 for y in v if y > 0) / len(v)}


def _vstat_span(tag: str) -> str:
    s = VERDICT_STATS.get(tag)
    if not s:
        return ""
    return (f'<span class="prio-stat">과거 {s["n"]}번 · 12M 평균 {s["mean"]:+.1f}%p '
            f'· 승률 {s["hit"]:.0f}%</span>')


def _history_line(r: ThemeResult, tag: str) -> str:
    """판정 밑의 전적 문장: 승률 → 예외는 언제였나 → 지금 조건이면 승률은 얼마.

    일반 면책이 아니라 조건부 통계다("승률을 말해주면서 예외는 언제였다,
    그러나 이럴 경우 승률은 ~에 불과하다"). 예외는 이 테마 자신의 전력을
    우선하고(정유가 2021~22 랠리를 '이유 약함'으로 놓친 류), 없으면 전체에서.
    """
    base = VERDICT_STATS.get(tag)
    recs = [x for x in BT_RECORDS if x.get("verdict") == tag]
    if not base or not recs:
        return ""
    pos = tag in _POSITIVE_TAGS
    parts = [f"과거 같은 판정 {base['n']}번 — 12개월 평균 {base['mean']:+.1f}%p, "
             f"승률 {base['hit']:.0f}%."]

    # 예외: 판정과 반대로 간 가장 큰 사례. 이 테마 자신의 것이 있으면 그걸로.
    def _worst(rs):
        rs = [x for x in rs if x.get("fwd12") is not None]
        if not rs:
            return None
        return min(rs, key=lambda x: x["fwd12"]) if pos \
            else max(rs, key=lambda x: x["fwd12"])

    own = _worst([x for x in recs if x.get("theme") == r.name])
    ex = own if own and ((pos and own["fwd12"] < 0) or (not pos and own["fwd12"] > 20)) \
        else _worst(recs)
    if ex and ((pos and ex["fwd12"] < 0) or (not pos and ex["fwd12"] > 20)):
        who = "이 테마가" if ex.get("theme") == r.name else f"{ex['theme']}가"
        direction = "하락" if pos else "랠리"
        parts.append(f"예외: {ex['date'][:7]} {who} 같은 판정에서 "
                     f"{ex['fwd12']:+.1f}%p {direction}.")

    # 지금 조건(주도 촉매 축의 안정성)으로 좁힌 조건부 승률.
    # 볼 만함·지켜볼 만은 정의 자체가 그 조건이라 중복 서술하지 않는다.
    if not pos and r.top_axes:
        stable = r.top_axes[0].key in STABLE_AXES
        sub = [x for x in recs if (_rec_top1(x) in STABLE_AXES) == stable]
        s = _bt_stats(sub)
        if s and s["n"] >= 5 and abs(s["hit"] - base["hit"]) >= 7:
            cond = ("낙수·공급·병목처럼 예측력이 검증된 축" if stable
                    else "시기 따라 예측력이 뒤집히는 축")
            tail = "에 불과합니다" if s["hit"] < base["hit"] else "로 올라갑니다"
            parts.append(f"그러나 지금처럼 주도 촉매가 {cond}인 경우로 좁히면 "
                         f"승률은 {s['hit']:.0f}%({s['n']}번, 평균 "
                         f"{s['mean']:+.1f}%p){tail}.")
    return '<p class="track">' + _e(" ".join(parts)) + "</p>"


def _honesty_html() -> str:
    """'한눈에' 맨 위 정직 고지 — 판정별 실측 승률 표 + 도구가 틀렸던 전력.

    사용자 지정: 한계 고지는 채팅이 아니라 눈에 잘 보이는 곳에 상설로.
    """
    if not VERDICT_STATS:
        return ""
    order = ["볼 만함", "지켜볼 만", "이미 반영", "되돌림", "이유 약함", "지금은 아님"]
    rows = []
    for tag in order:
        s = VERDICT_STATS.get(tag)
        if not s:
            continue
        rows.append(f"<tr><th scope='row'>{_e(tag)}</th><td class='num'>{s['n']}</td>"
                    f"<td class='num'>{s['mean']:+.1f}%p</td>"
                    f"<td class='num'>{s['median']:+.1f}%p</td>"
                    f"<td class='num'>{s['hit']:.0f}%</td></tr>")
    # 도구가 놓친 전력 — 낮은 판정이었는데 크게 오른 상위 사례
    misses = sorted((x for x in BT_RECORDS
                     if x.get("verdict") in _LOW_TAGS
                     and x.get("fwd12") is not None and x["fwd12"] > 40),
                    key=lambda x: -x["fwd12"])[:3]
    miss_txt = " · ".join(
        f"{m['date'][:7]} {m['theme']} '{m['verdict']}' → {m['fwd12']:+.0f}%p"
        for m in misses)
    vb = VERDICT_STATS.get("볼 만함") or {}
    return f"""
<div class="honesty">
<h2>이 도구를 읽는 법 — 판정은 예측이 아니라 확률이다</h2>
<div class="hon-cols">
<table class="summary hon-t"><thead><tr><th>판정</th><th>n</th><th>평균</th>
<th>중앙값</th><th>승률</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<ul class="hon-l">
<li>'볼 만함' 승률 {vb.get('hit', 0):.0f}%는 과거 {vb.get('n', 0)}번의 통계다 —
보장이 아니고, 표본도 작다.</li>
<li>낮은 판정은 "떨어진다"가 아니라 <strong>"여기서부터는 확률이 당신 편이
아니다"</strong>라는 뜻이다. '이미 반영'도 평균은 올랐다.</li>
<li><strong>놓친 전력:</strong> {_e(miss_txt) if miss_txt else '없음'} —
촉매 측정이 실제보다 2~3개월 늦는 테마의 랠리를 이 도구는 놓친다.</li>
<li>각 테마 카드의 '과거 같은 판정 …' 줄이 그 판정의 전적·예외·지금 조건의
조건부 승률이다.</li>
</ul>
</div></div>"""


def priority(r: ThemeResult) -> tuple[int, float]:
    """(판정 등급, -점수). 등급이 우선, 같은 등급 안에서 점수순."""
    tag, _, _ = _verdict(r)
    return (VERDICT_ORDER.get(tag, 9), -rank_score(r))


def rank_score(r: ThemeResult) -> float:
    """테마 정렬 기준 — 촉매와 미반영의 기하평균.

    산술평균을 쓰면 한쪽만 높아도 상위로 온다. 실제로 원자력이 촉매 27 에
    미반영 90 으로 1위였는데, 그건 '왜 오르는지 모르는데 싸다'는 뜻이고
    이 도구의 전제(둘의 교집합)에 어긋난다. 싼 데는 이유가 있을 수 있다.

    기하평균은 **한쪽이 0이면 총점이 0**이다. 촉매가 죽은 테마는 아무리 눌려
    있어도 후보가 아니다.

    커버리지를 곱해 신뢰도를 반영한다 — 축 3개로 낸 점수와 축 9개로 낸 점수를
    같은 저울에 올릴 수 없다. 할인은 0.5~1.0 으로 제한한다.
    """
    cat = max(r.catalyst_score or 0.0, 0.0)
    unp = max(r.unpriced_score or 0.0, 0.0)
    conf = 0.5 + 0.5 * (r.coverage / 100.0)
    gate = 1.15 if r.gate_passed >= 2 else 1.0
    return (cat * unp) ** 0.5 * conf * gate


# 축을 사람 말로. 점수 대신 이걸 읽고 판단할 수 있어야 한다.
AXIS_PLAIN = {
    "A1": "전방 산업이 살아나 주문이 넘어오고 있습니다",
    "A2": "증산 여력이 없어 공급이 빡빡합니다",
    "A3": "이 기술을 쓰는 회사가 빠르게 늘고 있습니다",
    "A4": "고객 설비가 늙어 교체 시기가 왔습니다",
    "A5": "예산·규제가 수요를 밀어주고 있습니다",
    "A6": "수년간 투자를 안 해 공급이 줄었습니다",
    "A7": "판가는 버티는데 원가가 내려 마진이 벌어지고 있습니다",
    "A8": "재고가 말라 재입고가 오면 크게 튑니다",
    "A9": "수주가 밀려 값을 올려 받을 수 있습니다",
    "A10": "수입에 뺏겼던 몫을 되찾고 있습니다",
}

# '이유 약함'을 설명할 때 쓰는 짧은 명사구
AXIS_NOUN = {
    "A1": "전방 수요 전이", "A2": "공급 부족", "A3": "기술 확산",
    "A4": "교체 수요", "A5": "예산·규제", "A6": "공급 축소",
    "A7": "마진 확대", "A8": "재고 바닥", "A9": "수주 병목",
    "A10": "수입 대체",
}


def _verdict(r: ThemeResult) -> tuple[str, str, str]:
    """한 줄 결론. (판정어, 색상클래스, 문장)

    숫자 두 개와 10개 축을 한 번에 읽으라는 건 무리다. 사람이 실제로 알고 싶은
    건 '이걸 봐야 하나, 왜'다. 그 한 문장을 데이터에서 만든다.
    """
    cat = r.catalyst_score
    unp = r.unpriced_score or 0.0
    tops = r.top_axes

    if cat is None or not tops:
        return ("판정 불가", "v-na",
                "주장한 촉매를 측정할 데이터가 없습니다. 테마 정의를 고쳐야 합니다.")

    why = AXIS_PLAIN.get(tops[0].key, tops[0].label)
    strong = cat >= 40
    cheap = unp >= 50

    # 가격 상태를 구체적으로
    px = next((s for s in r.unpriced if s.key == "U3"), None)
    rel = px.raw if px and px.raw is not None else None
    if rel is None:
        price = "주가 반응은 확인 불가"
    elif rel < -10:
        price = f"주가는 시장보다 {abs(rel):.0f}%p 뒤처져 아직 안 움직였습니다"
    elif rel < 5:
        price = "주가는 아직 시장 수준에 머물러 있습니다"
    else:
        price = f"주가는 이미 시장보다 {rel:.0f}%p 앞서 올랐습니다"

    noun = AXIS_NOUN.get(tops[0].key, "촉매")

    # 주장 축 중 신호가 사실상 죽은 것이 있으면 결론에 밝힌다.
    # 축 하나가 점수 전부를 만들면서 '볼 만함'으로 깨끗하게 표시되면 과대포장이다.
    live_axes = [s for s in r.claimed_axes if s.effective is not None]
    dead_axes = [s for s in live_axes if (s.effective or 0) < 10]
    partial = ""
    if dead_axes and len(live_axes) > 1:
        names = "·".join(AXIS_NOUN.get(s.key, s.label) for s in dead_axes)
        partial = f" 단, 주장 축 {len(live_axes)}개 중 {names}은(는) 신호가 없습니다."

    # 되돌림은 별도로 경고한다. 드로다운이 크다는 것만으로 '싸다'고 하면
    # 올랐다 빠지는 것을 저평가로 착각한다.
    if r.rebound:
        u4 = next((x for x in r.unpriced if x.key == "U4"), None)
        r3 = u4.raw if u4 and u4.raw is not None else None
        extra = f"3년간 시장을 {r3:+.0f}%p 앞선 뒤 고점에서 내려오는 중" if r3 is not None             else "이미 크게 오른 뒤 되돌리는 중"
        return ("되돌림", "v-bad",
                f"{extra}입니다. 눌려 보이지만 미반영이 아니라 과열 조정입니다.")

    if strong and cheap:
        if tops[0].key in STABLE_AXES:
            return ("볼 만함", "v-good", f"{why}. 그런데 {price}.{partial}")
        return ("지켜볼 만", "v-warn",
                f"{why}. 그런데 {price}. 다만 주도 근거({noun})는 백테스트에서 "
                f"시기에 따라 예측력이 뒤집힌 축이라 확신을 한 단계 낮춥니다."
                f"{partial}")
    if strong and not cheap:
        return ("이미 반영", "v-warn", f"{why}. 다만 {price}.{partial}")
    if not strong and cheap:
        return ("이유 약함", "v-warn",
                f"많이 눌려 있지만 오를 이유가 약합니다. "
                f"{noun} 근거가 충분히 확인되지 않았습니다.")
    return ("지금은 아님", "v-na",
            f"{noun} 근거가 약하고, {price}.")


def _stock_table(r: ThemeResult) -> str:
    """종목별 내역 — 수혜 × 상승여력 순.

    '미반영 순'은 수혜 없는 종목을(MOS 실측), '수혜 순'은 이미 다 오른 종목을
    맨 위에 올렸다. 원하는 답은 '가장 좋은 기업 중 아직 여력이 남은 것' —
    테마 순위와 같은 기하평균으로 두 조건을 동시에 요구한다.
    """
    rows = []
    for s in r.stocks:
        def num(k, fmt="{:+.1f}", suffix=""):
            v = s.get(k)
            return f"{fmt.format(v)}{suffix}" if v is not None else "—"

        rel = s.get("rel_12m")
        cls = "cool" if rel is not None and rel < -5 else ("hot" if rel is not None and rel > 20 else "")
        conm = NAMES.get(s["ticker"].upper(), "")
        if s.get("annual_basis"):
            conm = (conm + " · 연간재무 기준").strip(" ·")
        rows.append(
            f'<tr class="{cls}"><th scope="row">{_e(s["ticker"])}'
            f'<span class="coname">{_e(conm)}</span></th>'
            f'<td class="num"><strong>{num("total", "{:.0f}", "")}</strong></td>'
            f'<td class="num">{num("benefit", "{:.0f}", "")}</td>'
            f'<td class="num">{num("upside", "{:.0f}", "")}</td>'
            f'<td class="num">{num("rev_yoy", "{:+.1f}", "%")}</td>'
            f'<td class="num">{num("opm_delta", "{:+.1f}", "%p")}</td>'
            f'<td class="num">{num("ret_1m", "{:+.1f}", "%")}</td>'
            f'<td class="num">{num("ret_3m", "{:+.1f}", "%")}</td>'
            f'<td class="num">{num("abs_12m", "{:+.1f}", "%")}</td>'
            f'<td class="num" title="{_e(s.get("earn_date") or "")}'
            + (f' · EPS 서프라이즈 {s["eps_surprise"]:+.1f}%'
               if s.get("eps_surprise") is not None else "")
            + f'">{num("earn_react", "{:+.1f}", "%p")}</td></tr>')
    if not rows:
        return ""
    return (
        '<details class="stocks"><summary>종목별 내역 '
        f'({len(r.stocks)}개 · 수혜 × 상승여력 순)</summary>'
        '<table class="stk"><thead><tr><th>티커 · 회사명</th>'
        '<th class="num">종합</th><th class="num">수혜</th>'
        '<th class="num">여력</th>'
        '<th class="num">매출YoY</th><th class="num">이익개선</th>'
        '<th class="num">1M</th><th class="num">3M</th>'
        '<th class="num">12M</th>'
        '<th class="num" title="최근 실적발표(8-K) 전후 시장 대비 반응">'
        '실적반응</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
        '<p class="stknote"><strong>종합 = √(수혜 × 상승여력)</strong> — 실적으로 '
        '수혜가 확인되면서(매출 성장·가속·이익률 개선) 아직 가격에 덜 들어간 '
        '종목이 위. 수혜·여력은 <strong>테마 내 상대 백분위</strong>다 — 수혜 '
        '100은 ‘이 테마 종목 중 실적 1등’이지 절대평가가 아니다. 수혜가 테마 '
        '중앙(50) 미달이면 종합을 절반으로 깎는다 — ‘좋은 기업 중에서’가 먼저고, '
        '많이 빠졌다는 것만으로는 위로 못 온다. 재무 미확보(—)는 근거가 없어 '
        '맨 아래. 1M/3M/12M 은 절대 주가 상승률. 종목을 고르는 모델이 아니라 '
        '같은 테마 안의 우선순위다.</p></details>')


def why_flat(theme_rel: float | None, s: dict) -> list[str]:
    """'왜 아직 안 올랐나' — 데이터로 판별 가능한 원인만 말한다.

    실적이 좋은데 주가가 눌린 데는 이유가 있다. 판별 가능한 것:
    ①섹터 동반 눌림(테마 상대수익 음수) ②디레이팅(이익↑인데 멀티플↓ —
    시장이 이익 지속성을 불신) ③실적 가속이 갓 시작(시장 미인지)
    ④최근 반등 시동. 어느 것도 아니면 '데이터 밖 요인'으로 정직하게.
    """
    outs = []
    if theme_rel is not None and theme_rel < -5:
        outs.append(f"테마 전체가 시장 대비 {abs(theme_rel):.0f}%p 눌려 있어 "
                    "종목보다 섹터 센티먼트 문제")
    d = s.get("derate")
    if d is not None and d < -15:
        outs.append(f"이익이 느는 동안 멀티플이 {abs(d):.0f}% 압축 — "
                    "시장이 이익의 지속성을 아직 불신")
    if (s.get("rev_accel") or 0) > 3:
        outs.append("실적 가속이 최근 분기에 막 시작돼 시장이 추세로 "
                    "인정하기 전")
    er = s.get("earn_react")
    if er is not None and er < -3:
        outs.append(f"직전 실적 발표에 시장 반응이 차가웠음({er:+.1f}%p) — "
                    "다음 분기 숫자로 증명해야 하는 구간")
    if (s.get("ret_3m") or 0) > 5 and (s.get("abs_12m") or 99) < 10:
        outs.append(f"단, 최근 3개월 {s['ret_3m']:+.0f}% — 인식이 붙기 시작")
    if not outs:
        outs.append("데이터로는 설명되지 않음 — 종목 고유 요인"
                    "(가이던스·일회성 이슈) 확인 필요")
    return outs[:2]


def week_changes(hist: list[dict]) -> dict | None:
    """최신 항목 vs 약 일주일 전 항목의 차이 — '지난주와 달라진 것'의 재료.

    사용자 피드백 "별로 달라진 게 없네?" — 거시·재무는 월간·분기 주기라
    화면이 느리게 변하는 게 정상이지만, 그 미세 변화가 안 보이는 건 결함이다.
    매일 점수 이력(score_history.jsonl)을 쌓고 5~10일 전과 비교한다.
    """
    if len(hist) < 2:
        return None
    from datetime import date as _d
    cur = hist[-1]
    d1 = _d.fromisoformat(cur["date"])
    cands = [h for h in hist[:-1]
             if 5 <= (d1 - _d.fromisoformat(h["date"])).days <= 10]
    if not cands:
        return None
    base = cands[-1]
    out = {"days": (d1 - _d.fromisoformat(base["date"])).days,
           "themes": [], "picks_from": base.get("picks", []),
           "picks_to": cur.get("picks", [])}
    for name, c in cur.get("themes", {}).items():
        b = base.get("themes", {}).get(name)
        if not b:
            continue
        dc = (c.get("cat") or 0) - (b.get("cat") or 0)
        du = (c.get("unp") or 0) - (b.get("unp") or 0)
        if abs(dc) >= 3 or abs(du) >= 3 or b.get("verdict") != c.get("verdict"):
            out["themes"].append({"name": name, "dcat": dc, "dunp": du,
                                  "v_from": b.get("verdict"),
                                  "v_to": c.get("verdict")})
    out["themes"].sort(key=lambda x: -(abs(x["dcat"]) + abs(x["dunp"])))
    return out


def _changes_html(hist: list[dict]) -> str:
    ch = week_changes(hist)
    if ch is None:
        n = len(hist)
        return ('<div class="wkch"><h2 class="wkch-h">지난주와 달라진 것</h2>'
                f'<p class="wkch-note">이력 축적 중({n}일째) — 일주일치가 쌓이면 '
                '점수·판정·추천의 변화가 여기 표시됩니다. 거시·재무 지표는 '
                '월간·분기 주기라 화면이 느리게 변하는 게 정상입니다.</p></div>')
    items = []
    pf, pt = ch["picks_from"], ch["picks_to"]
    if pf and pt:
        if pf == pt:
            items.append(f"추천 3종목 유지({' · '.join(pt)}) — 논지가 바뀌지 않았다는 뜻")
        else:
            items.append(f"추천 교체: {' · '.join(pf)} → <strong>{' · '.join(pt)}</strong>")
    for t in ch["themes"][:6]:
        parts = []
        if t["v_from"] != t["v_to"]:
            parts.append(f"판정 <strong>{_e(t['v_from'])} → {_e(t['v_to'])}</strong>")
        if abs(t["dcat"]) >= 3:
            parts.append(f"촉매 {t['dcat']:+.0f}")
        if abs(t["dunp"]) >= 3:
            parts.append(f"미반영 {t['dunp']:+.0f}")
        items.append(f"{_e(t['name'])}: " + ", ".join(parts))
    if len(items) <= 1:
        items.append("테마 점수·판정 모두 ±3 이내 — 조용한 한 주")
    lis = "".join(f"<li>{x}</li>" for x in items)
    return ('<div class="wkch"><h2 class="wkch-h">지난주와 달라진 것 '
            f'<span class="wkch-d">({ch["days"]}일 전 대비)</span></h2>'
            f'<ul class="wkch-l">{lis}</ul></div>')


def load_history() -> list[dict]:
    p = Path(__file__).resolve().parent.parent / "reports" / "score_history.jsonl"
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
    except Exception:
        return []
    out.sort(key=lambda h: h.get("date", ""))
    return out


def top_pick_rows(ranked: list[ThemeResult]) -> list:
    """추천 후보 상위 3 — (판정등급, -점수, 테마, 종목행, 판정어).

    선정 = 도구의 두 층위를 그대로 곱한 것: 촉매가 확인된 테마(판정 순서)
    안에서, 수혜가 확인되고(benefit≥50) 여력이 남은 종목을
    √(테마 종합 × 종목 종합)으로 뽑는다. 테마당 1종목(한 테마 몰빵 방지).
    """
    cands = []
    for r in ranked:
        tag, _cls, _txt = _verdict(r)
        for s in r.stocks:
            if s.get("total") is None or (s.get("benefit") or 0) < 50:
                continue
            pick = (max(rank_score(r), 1.0) * s["total"]) ** 0.5
            cands.append((VERDICT_ORDER.get(tag, 9), -pick, r, s, tag))
            break                                  # 테마 내 1위만 후보
    cands.sort(key=lambda x: (x[0], x[1]))
    return cands[:3]


def _top_picks(ranked: list[ThemeResult]) -> str:
    """맨 위 '지금 가장 추천하는 3종목' 카드 렌더."""
    top = top_pick_rows(ranked)
    if not top:
        return ""

    items = []
    for i, (_, negp, r, s, tag) in enumerate(top, 1):
        t = s["ticker"]
        name = NAMES.get(t.upper(), "")
        tops = r.top_axes
        why_theme = AXIS_PLAIN.get(tops[0].key, tops[0].label) if tops else ""

        def v(k, fmt, suf=""):
            x = s.get(k)
            return f"{fmt.format(x)}{suf}" if x is not None else "—"

        up = s.get("upside") or 0
        a12 = s.get("abs_12m")
        # 여력은 '테마 내 상대값'이다 — +116% 오른 종목에 "덜 올랐다"고 쓰면
        # 거짓말이 된다(DINO 실측). 절대 상승률에 따라 문장을 가른다.
        if up >= 50 and (a12 is None or a12 < 30):
            px_part = (f"주가는 12개월 {v('abs_12m', '{:+.0f}', '%')}로 "
                       "아직 덜 올라 여력이 남았습니다")
        elif up >= 50:
            px_part = (f"주가가 12개월 {v('abs_12m', '{:+.0f}', '%')} 올랐지만 "
                       "테마 안에서는 실적 대비 상대적으로 여력이 남은 편입니다")
        else:
            px_part = (f"주가는 12개월 {v('abs_12m', '{:+.0f}', '%')} — 반영이 "
                       "진행돼 실적 개선 속도가 관건입니다")
        u3 = next((x for x in r.unpriced if x.key == "U3"), None)
        trel = u3.raw if u3 and u3.raw is not None else None
        flat = ""
        if (s.get("upside") or 0) >= 50 and (s.get("abs_12m") is None
                                             or s["abs_12m"] < 15):
            flat = (' <span class="pick-flat">왜 아직 안 올랐나: '
                    + _e(" / ".join(why_flat(trel, s))) + '.</span>')
        reason = (f"<strong>{_e(r.name)}</strong>(판정 {_e(tag)}) — {_e(why_theme)} "
                  f"이 테마 수혜 1위: 매출 {v('rev_yoy', '{:+.1f}', '%')}"
                  + (f", 이익률 개선 {v('opm_delta', '{:+.1f}', '%p')}"
                     if s.get("opm_delta") is not None else "")
                  + f". {px_part} (수혜 {v('benefit', '{:.0f}')}"
                  f"·여력 {v('upside', '{:.0f}')}).{flat}")
        items.append(
            f'<li class="pick"><span class="pick-n">{i}</span>'
            f'<div class="pick-b"><span class="pick-t">{_e(t)}</span>'
            f'<span class="pick-co">{_e(name)}</span>'
            f'<p class="pick-why">{reason}</p></div></li>')

    return ('<div class="picks"><h2 class="picks-h">지금 가장 추천하는 3종목</h2>'
            '<ol class="picks-l">' + "".join(items) + '</ol>'
            '<p class="picks-note">촉매가 확인된 테마 안에서 수혜(실적)와 '
            '상승여력을 함께 요구한 자동 선별이다 — 데이터 기준 우선순위이지 '
            '리서치 판단을 대체하지 않는다. 근거는 아래 테마 카드에서 축별로 '
            '확인할 것.</p></div>')


def _priority_list(ranked: list[ThemeResult]) -> str:
    """추천 순서 — 스크롤 안 하고 한눈에.

    등급별로 묶어 보여준다. 점수 순서만으로는 '무엇부터 봐야 하나'가 안 읽힌다.
    """
    groups: dict[str, list] = {}
    for r in ranked:
        tag, cls, text = _verdict(r)
        groups.setdefault(tag, []).append((r, cls, text))

    out = ['<div class="prio"><h2 class="prio-h">무엇부터 볼까</h2>']
    n = 0
    for tag in VERDICT_ORDER:
        items = groups.get(tag)
        if not items:
            continue
        cls = items[0][1]
        note = {
            "볼 만함": "촉매가 확인되고 가격도 아직 — 먼저 볼 것",
            "지켜볼 만": "조건은 갖췄지만 주도 축의 예측력이 시기 따라 뒤집힘",
            "이미 반영": "촉매는 맞지만 주가가 앞서갔다",
            "이유 약함": "눌려 있으나 오를 근거가 부족하다",
            "지금은 아님": "근거도 약하고 가격도 유리하지 않다",
            "되돌림": "과열 조정 — 눌림을 저평가로 착각하기 쉬운 구간",
            "판정 불가": "측정 데이터가 없다",
        }.get(tag, "")
        out.append(f'<div class="prio-g"><div class="prio-t">'
                   f'<span class="vd {cls}">{_e(tag)}</span>'
                   f'<span class="prio-n">{_e(note)}</span>'
                   f'{_vstat_span(tag)}</div><ol class="prio-l">')
        for r, _c, text in items:
            n += 1
            cs = "—" if r.catalyst_score is None else f"{r.catalyst_score:.0f}"
            us = "—" if r.unpriced_score is None else f"{r.unpriced_score:.0f}"
            out.append(f'<li><a href="#t{n}"><strong>{_e(r.name)}</strong></a>'
                       f'<span class="prio-s">촉매 {cs} · 미반영 {us}</span>'
                       f'<span class="prio-w">{_e(text)}</span></li>')
        out.append("</ol></div>")
    out.append("</div>")
    return "".join(out)


def _summary_table(results: list[ThemeResult]) -> str:
    rows = []
    for i, r in enumerate(results, 1):
        cs = "—" if r.catalyst_score is None else f"{r.catalyst_score:.0f}"
        us = "—" if r.unpriced_score is None else f"{r.unpriced_score:.0f}"
        rows.append(f"<tr><td class='num'>{i}</td><th scope='row'>{_e(r.name)}</th>"
                    f"<td>{_e(r.lead_time)}</td><td class='num'>{cs}</td>"
                    f"<td class='num'>{us}</td><td class='num'>{r.gate_passed}</td>"
                    f"<td class='num'>{r.coverage:.0f}%</td>"
                    f"<td class='num'>{rank_score(r):.0f}</td></tr>")
    return ("<table class='summary'><thead><tr><th>#</th><th>테마</th><th>리드타임</th>"
            "<th>촉매</th><th>미반영</th><th>게이트</th><th>커버리지</th>"
            "<th>순위점수</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


CSS = """
.viz-root{color-scheme:light;--surface-1:#fbfbfd;--plane:#f3f4fa;--text-primary:#12132e;
--text-secondary:#45476a;--muted:#8a8ca6;--grid:#e3e4ef;--axis:#c6c8db;
--border:rgba(26,26,88,.13);--series-1:#2d2c92;--series-2:#00aeef;--series-3:#1baf7a;
--good:#0e9e54;--warning:#e8a714;--critical:#d03b3b;--seq-200:#b9c2f0;--seq-450:#2d2c92;
--navy:#1a1a58;--cyan:#00aeef}
[hidden]{display:none!important}
@media (min-width:1500px){
 .wrap{max-width:min(97vw,3200px)}
 /* 좌우 배치는 높이를 맞추고(뷰포트 기준) 각 열이 따로 스크롤된다 —
    페이지 전체를 내리는 대신 창 안에서 내리는 대시보드 방식(사용자 지정) */
 .glance-grid{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(0,1fr);
  grid-template-rows:auto minmax(0,1fr);gap:0 32px;align-items:stretch;
  height:calc(100vh - 150px);min-height:560px}
 .g-a{grid-column:1;grid-row:1}
 .g-b{grid-column:1;grid-row:2;overflow-y:auto;padding-right:6px}
 .g-side{grid-column:2;grid-row:1 / span 2;overflow-y:auto;padding-right:6px}
 .glance-grid .prio{margin-top:0}
 .honesty .hon-t{flex:0 0 380px}
 .cardcols{columns:2;column-gap:28px}
 .cardcols .card{break-inside:avoid;margin-top:0;margin-bottom:18px}
}
@media (min-width:2100px){
 .glance-grid{grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr) minmax(0,1.05fr);
  grid-template-rows:minmax(0,1fr);gap:0 36px}
 .g-a{grid-column:1;grid-row:1;overflow-y:auto;padding-right:6px}
 .g-b{grid-column:2;grid-row:1}
 .g-side{grid-column:3;grid-row:1}
 .cardcols{columns:3;column-gap:30px}
 .hon-l{column-count:2;column-gap:40px}
}
.tabbar{position:sticky;top:0;z-index:30;display:flex;gap:6px;padding:10px 0 8px;
 background:var(--surface-1);border-bottom:1px solid var(--border);margin:14px 0 18px}
.tabbtn{font:inherit;font-weight:700;font-size:14.5px;padding:8px 16px;border-radius:9px;
 border:1px solid var(--border);background:var(--plane);color:var(--text-secondary);cursor:pointer}
.tabbtn.on{background:linear-gradient(135deg,#1a1a58,#2d2c92);
 border-color:var(--seq-450);color:#fff}
.viz-root h1,.viz-root h2{color:var(--navy)}
.tabbtn.tablink{margin-left:auto;text-decoration:none;color:var(--text-secondary)}
.chiprow{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 14px;
 position:sticky;top:50px;z-index:25;background:var(--surface-1);
 padding:9px 0 10px;border-bottom:1px solid var(--border)}
.card{scroll-margin-top:128px}
.chip{font-size:12.5px;padding:4px 10px;border-radius:999px;border:1px solid var(--border);
 background:var(--plane);color:var(--text-primary);text-decoration:none}
.chip.v-good{border-color:var(--good)}.chip.v-bad{border-color:var(--critical)}
.card.flash{outline:3px solid var(--seq-450);transition:outline .2s}
.track{margin:2px 0 8px;font-size:13px;line-height:1.55;color:var(--text-secondary);
 border-left:3px solid var(--cyan);padding-left:10px}
.prio-stat{margin-left:auto;font-size:12.5px;color:var(--text-secondary);white-space:nowrap}
.honesty{border:1px solid var(--border);border-left:4px solid var(--cyan);
 border-radius:10px;padding:14px 18px;margin:6px 0 20px;background:var(--plane)}
.honesty h2{margin:0 0 10px;font-size:17px}
.hon-cols{display:flex;gap:22px;flex-wrap:wrap;align-items:flex-start}
.hon-t{flex:0 0 330px;font-size:13px}
.hon-l{flex:1;min-width:280px;margin:0;padding-left:18px;font-size:13.5px;line-height:1.65}
.hon-l li{margin-bottom:6px}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{
color-scheme:dark;--surface-1:#121430;--plane:#0b0c1c;--text-primary:#f2f3ff;
--text-secondary:#b9bcd8;--muted:#7e81a3;--grid:#23264a;--axis:#333863;
--border:rgba(255,255,255,.12);--series-1:#6f7df0;--series-2:#00aeef;--series-3:#2bbf8a;
--seq-200:#28306b;--seq-450:#5a68e8;--navy:#aab4ff;--cyan:#00aeef}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;--surface-1:#121430;--plane:#0b0c1c;
--text-primary:#f2f3ff;--text-secondary:#b9bcd8;--muted:#7e81a3;--grid:#23264a;--axis:#333863;
--border:rgba(255,255,255,.12);--series-1:#6f7df0;--series-2:#00aeef;--series-3:#2bbf8a;
--seq-200:#28306b;--seq-450:#5a68e8;--navy:#aab4ff;--cyan:#00aeef}
*{box-sizing:border-box}
body{margin:0;background:var(--plane)}
.viz-root{font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;
background:var(--plane);color:var(--text-primary);padding:28px 20px 60px}
.wrap{max-width:1180px;margin:0 auto}
h1{font-size:23px;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:16px;margin:38px 0 12px;letter-spacing:-.005em}
h3{font-size:16px;margin:0;display:inline}
h4{font-size:12px;margin:0 0 7px;color:var(--text-secondary);font-weight:600;
text-transform:uppercase;letter-spacing:.05em}
.sub{color:var(--text-secondary);margin:0 0 6px}
.meta{color:var(--muted);font-size:12px;margin:0}
.panel{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;
padding:18px 20px;margin-top:14px}
.scatter{width:100%;height:auto;display:block}
.grid{stroke:var(--grid);stroke-width:1}
.mid{stroke:var(--axis);stroke-width:1;stroke-dasharray:3 3}
.target-quad{fill:var(--seq-450);opacity:.055}
.tick{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.axlab{fill:var(--text-secondary);font-size:12px}
.quadlab{fill:var(--text-secondary);font-size:11px;font-weight:600;letter-spacing:.04em}
.quadlab.dim{fill:var(--muted);font-weight:400}
.pt{stroke:var(--surface-1);stroke-width:2}
.pt.gated{stroke-width:2.5}
.ptlab{fill:var(--text-primary);font-size:11.5px}
.legend{display:flex;gap:18px;flex-wrap:wrap;margin-top:10px;font-size:12px;
color:var(--text-secondary)}
.lg{display:inline-flex;align-items:center;gap:6px}
.lg i{width:10px;height:10px;border-radius:50%;display:inline-block}
.lg em{color:var(--muted);font-style:normal}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;
padding:18px 20px;margin-bottom:14px}
.chead{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;
flex-wrap:wrap}
.rank{display:inline-block;min-width:22px;color:var(--muted);font-variant-numeric:tabular-nums;
font-size:13px}
.pill{display:inline-block;margin-left:9px;font-size:11px;padding:2px 8px;border-radius:99px;
border:1px solid var(--pc);color:var(--pc);vertical-align:2px}
.scores{display:flex;gap:8px}
.sbox{text-align:right;min-width:62px;padding:4px 10px;border-radius:8px;
background:var(--plane);border:1px solid var(--border)}
.sbox span{display:block;font-size:10.5px;color:var(--muted);letter-spacing:.03em}
.sbox strong{font-size:19px;font-weight:600;letter-spacing:-.02em}
.sbox.gate strong{font-size:13px}
.sbox.gate.good strong{color:var(--good)}
.sbox.gate.warn strong{color:var(--text-secondary)}
.sbox.gate.bad strong{color:var(--critical)}
.thesis{margin:10px 0 4px;color:var(--text-secondary)}
.tick-list{margin:0 0 12px;font-size:11.5px;color:var(--muted);
font-variant-numeric:tabular-nums}
.tick-list em{font-style:normal}
.sparks{display:flex;gap:22px;flex-wrap:wrap;padding:10px 0 14px;
border-top:1px solid var(--grid);border-bottom:1px solid var(--grid);margin-bottom:14px}
.sp{display:flex;flex-direction:column;gap:1px}
.splab{font-size:10.5px;color:var(--muted)}
.spval{font-size:12px;color:var(--text-secondary);font-variant-numeric:tabular-nums}
.spark{display:block}
.nodata{color:var(--muted)}
.tables{display:grid;grid-template-columns:1fr 1fr;gap:22px}
table{border-collapse:collapse;width:100%}
.sig th[scope=row]{text-align:left;font-weight:500;white-space:nowrap;padding:3px 10px 3px 0;
vertical-align:top;font-size:12.5px}
.sig td{padding:3px 0;vertical-align:top}
.sig .bcell{width:74px;padding-right:9px}
.sig .num{width:30px;text-align:right;padding-right:11px;font-variant-numeric:tabular-nums;
font-size:12.5px}
.sig .det{color:var(--text-secondary);font-size:12px;line-height:1.45}
.sig tr.na{opacity:.42}
.sig tr.rej th[scope=row]{color:var(--muted);text-decoration:line-through}
.why{color:var(--muted);font-size:11.5px;margin-top:2px;padding-left:8px;
border-left:2px solid var(--grid)}
.sig tr.rej .why{border-left-color:var(--critical)}
.sig tr.warn .why{border-left-color:var(--warning)}
.tag{display:inline-block;margin-left:6px;font-size:9.5px;padding:1px 5px;border-radius:99px;
border:1px solid currentColor;vertical-align:1px;letter-spacing:.02em}
.st-ok{color:var(--good)}
.st-warn{color:var(--text-secondary)}
.st-rej{color:var(--critical)}
.st-na{color:var(--muted)}
.picks{margin:18px 0 0;padding:16px 20px;border-radius:14px;
background:var(--surface-1);border:1px solid var(--border)}
.picks-h{margin:0 0 10px;font-size:15px}
.picks-l{list-style:none;margin:0;padding:0}
.pick{display:flex;gap:12px;padding:9px 0;border-top:1px solid var(--grid)}
.pick:first-child{border-top:0}
.pick-n{flex:0 0 22px;height:22px;border-radius:50%;background:var(--series-1);
color:#fff;font-size:12px;font-weight:700;display:flex;align-items:center;
justify-content:center;margin-top:2px}
.pick-t{font-weight:700;font-size:14px;margin-right:8px}
.pick-co{color:var(--muted);font-size:12px}
.pick-why{margin:3px 0 0;font-size:12.5px;color:var(--text-secondary);line-height:1.55}
.picks-note{margin:10px 0 0;font-size:11.5px;color:var(--muted)}
.pick-flat{display:block;margin-top:3px;color:var(--muted)}
.wkch{margin:14px 0 0;padding:14px 20px;border-radius:14px;
background:var(--surface-1);border:1px solid var(--border)}
.wkch-h{margin:0 0 8px;font-size:14px}
.wkch-d{font-weight:400;font-size:12px;color:var(--muted)}
.wkch-l{margin:0 0 0 18px;padding:0;font-size:12.5px;
color:var(--text-secondary)}
.wkch-l li{margin-bottom:4px}
.wkch-note{margin:0;font-size:12px;color:var(--muted)}
.ic-ok{color:var(--good);border:1px solid var(--good);background:transparent}
.ic-bad{color:var(--critical);border:1px solid var(--critical);background:transparent}
.ic-na{color:var(--muted);border:1px solid var(--border);background:transparent}
.healthwarn{margin:16px 0 0;padding:14px 18px;border-radius:12px;
background:var(--surface-1);border:1px solid var(--critical);
border-left:4px solid var(--critical)}
.healthwarn h3{margin:0 0 8px;font-size:13px;color:var(--critical);letter-spacing:.01em}
.healthwarn ul{margin:0 0 8px 18px;padding:0;font-size:12.5px;color:var(--text-secondary)}
.healthwarn li{margin-bottom:4px}
.healthwarn p{margin:0;font-size:12px;color:var(--muted)}
.drivers{margin:0 0 6px;font-size:12px;color:var(--text-secondary)}
.drivers strong{color:var(--text-primary);font-weight:600}
.verdict-line{margin:10px 0 8px;font-size:13.5px;line-height:1.6;
color:var(--text-primary)}
.vd{display:inline-block;font-size:11.5px;font-weight:600;padding:2px 9px;
border-radius:6px;border:1px solid currentColor;margin-right:9px;vertical-align:1px}
.v-good{color:var(--good)}
.v-warn{color:var(--warning)}
.v-na{color:var(--muted)}
.v-bad{color:var(--critical)}
.star{color:var(--series-2);margin-right:3px}
.detail{margin-top:10px}
.detail>summary{cursor:pointer;font-size:12px;color:var(--text-secondary);
padding:4px 0}
.detail[open]>summary{margin-bottom:8px;border-bottom:1px solid var(--grid)}
.claim{margin:0 0 6px;font-size:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.verdict{font-size:11.5px;font-weight:600;padding:2px 9px;border-radius:6px;
border:1px solid currentColor}
.v-good{color:var(--good)}
.v-warn{color:var(--warning)}
.v-bad{color:var(--critical)}
.v-na{color:var(--muted)}
.v-bad{color:var(--critical)}
.claim-list{color:var(--text-secondary)}
.incidental{margin:0 0 10px;font-size:11.5px;color:var(--muted)}
.incidental em{font-style:normal}
h4 em{font-style:normal;text-transform:none;letter-spacing:0;color:var(--muted);
font-weight:400}
.bar{height:6px;background:var(--grid);border-radius:99px;overflow:hidden;margin-top:5px}
.barfill{height:100%;background:var(--seq-450);border-radius:99px}
.barfill.na{width:0}
.ev{color:var(--series-1);text-decoration:none;white-space:nowrap;font-size:11px}
.ev:hover{text-decoration:underline}
.notes{margin-top:12px;font-size:12px;color:var(--muted)}
.notes summary{cursor:pointer}
.notes ul{margin:6px 0 0 18px;padding:0}
.summary{background:var(--surface-1);font-size:13px}
.summary th,.summary td{border-bottom:1px solid var(--grid);padding:7px 10px;text-align:left}
.summary thead th{color:var(--text-secondary);font-size:11px;text-transform:uppercase;
letter-spacing:.05em;font-weight:600}
.summary .num{text-align:right;font-variant-numeric:tabular-nums}
.prio{margin:18px 0 0;padding:18px 20px;background:var(--surface-1);
border:1px solid var(--border);border-radius:12px}
.prio-h{font-size:15px;margin:0 0 14px}
.prio-g{margin-bottom:16px}
.prio-g:last-child{margin-bottom:0}
.prio-t{display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap}
.prio-n{font-size:11.5px;color:var(--muted)}
.prio-l{margin:0;padding-left:24px;font-size:13px}
.prio-l li{margin-bottom:7px;line-height:1.5}
.prio-l a{color:var(--text-primary);text-decoration:none;border-bottom:1px solid var(--grid)}
.prio-l a:hover{border-bottom-color:var(--series-1)}
.prio-s{display:inline-block;margin-left:9px;font-size:11px;color:var(--muted);
font-variant-numeric:tabular-nums}
.prio-w{display:block;font-size:12px;color:var(--text-secondary)}
.rankrule{margin:6px 0 0;font-size:12px;color:var(--muted)}
.rankrule code{background:var(--surface-1);padding:1px 5px;border-radius:4px;
border:1px solid var(--border);font-size:11.5px}
.stocks{margin-top:12px;font-size:12px}
.stocks summary{cursor:pointer;color:var(--text-secondary)}
.stk{margin-top:8px;font-size:12px;width:auto;max-width:100%}
.stk th,.stk td{border-bottom:1px solid var(--grid);padding:4px 6px;text-align:left}
.stk thead th{color:var(--muted);font-size:10.5px;text-transform:uppercase;
letter-spacing:.04em;font-weight:600;white-space:nowrap}
.stk th[scope=row]{font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}
.coname{display:block;font-weight:400;font-size:10.5px;color:var(--muted);
letter-spacing:0;max-width:210px;overflow:hidden;text-overflow:ellipsis}
.stk .num{text-align:right;font-variant-numeric:tabular-nums}
.stk tr.cool th[scope=row]{color:var(--series-1)}
.stk tr.hot th[scope=row]{color:var(--muted)}
.stknote{margin:8px 0 0;font-size:11.5px;color:var(--muted)}
.foot{margin-top:34px;padding-top:16px;border-top:1px solid var(--grid);
color:var(--muted);font-size:12px}
.foot code{background:var(--surface-1);padding:1px 5px;border-radius:4px;
border:1px solid var(--border)}
.toggle{position:fixed;top:14px;right:16px;background:var(--surface-1);
border:1px solid var(--border);color:var(--text-secondary);border-radius:8px;
padding:6px 11px;cursor:pointer;font:inherit;font-size:12px}
@media (max-width:820px){.tables{grid-template-columns:1fr}
.chead{flex-direction:column}}
"""


# 탭 전환 스크립트 — 외부 의존 없음. 한 페이지 스크롤이 30개 테마에서
# 읽기 불가능해져("스크롤로 내려가면서 보기 불편") 화면을 셋으로 나눈다.
# f-string 밖 상수로 둔다: JS 중괄호를 f-string 이 삼키는 사고 방지.
TAB_JS = """
(function(){
  var panes=['pane-glance','pane-cards','pane-table'];
  function show(id){
    panes.forEach(function(p){
      var el=document.getElementById(p);
      if(el) el.hidden=(p!==id);
    });
    document.querySelectorAll('.tabbtn[data-pane]').forEach(function(b){
      b.classList.toggle('on', b.dataset.pane===id);
    });
  }
  document.querySelectorAll('.tabbtn[data-pane]').forEach(function(b){
    b.addEventListener('click', function(){ show(b.dataset.pane); window.scrollTo(0,0); });
  });
  // '무엇부터 볼까'·칩의 #tN 링크 → 상세 탭으로 전환 후 그 카드로 이동
  document.addEventListener('click', function(e){
    var a=e.target.closest&&e.target.closest('a[href^="#t"]');
    if(!a) return;
    var id=a.getAttribute('href').slice(1);
    if(!/^t\\d+$/.test(id)) return;
    e.preventDefault();
    show('pane-cards');
    var el=document.getElementById(id);
    if(el){
      el.scrollIntoView({block:'start'});
      el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
    }
  });
  show('pane-glance');
})();
"""


def _theme_chips(ranked: list[ThemeResult]) -> str:
    """상세 탭 머리의 테마 점프 칩 — 30개를 스크롤로 찾지 않게."""
    chips = []
    for i, r in enumerate(ranked, 1):
        tag, cls, _t = _verdict(r)
        chips.append(f'<a class="chip {cls}" href="#t{i}" title="{_e(tag)}">{_e(r.name)}</a>')
    return '<div class="chiprow">' + "".join(chips) + "</div>"


def build_html(results: list[ThemeResult], *, benchmark: str = "SPY") -> str:
    ranked = sorted(results, key=priority)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    n_target = sum(1 for r in ranked
                   if (r.catalyst_score or 0) >= 50 and (r.unpriced_score or 0) >= 50)

    cards = "".join(_card(r, i) for i, r in enumerate(ranked, 1))

    # 판독 건강도 — 데이터가 통째로 안 들어온 것을 조용히 넘기지 않는다.
    # 주가가 죽으면 미반영 축 4개 중 2개가 사라지는데, 점수만 보면 눈치채기 어렵다.
    # 조회 실패(U3 죽음)와 이력 부족(U4 만 죽음 — 신규 상장 테마)은 원인이 달라
    # 나눠 알린다. 합쳐 놨더니 GEV 상장 이력 부족을 'Yahoo 차단'으로 오진했다.
    dead_px = sum(1 for r in ranked
                  if any(s.key == "U3" and s.score is None for s in r.unpriced))
    short3 = sum(1 for r in ranked
                 if any(s.key == "U4" and s.score is None for s in r.unpriced)
                 and not any(s.key == "U3" and s.score is None for s in r.unpriced))
    dead_fin = sum(1 for r in ranked if not r.series.get("n_companies"))
    from .sources import PRICES_FROM_SNAPSHOT as _snap_used
    warn = ""
    if dead_px or short3 or dead_fin or _snap_used:
        items = []
        if dead_px:
            items.append(f"<li><strong>주가 미확보 {dead_px}/{len(ranked)}개 테마</strong> — "
                         "‘주가 미반응’·‘고점 대비 눌림’ 두 축이 빠졌습니다. "
                         "Yahoo·Stooq·동봉 스냅샷 3단 폴백이 전부 실패한 상태로, "
                         "보통 다음 날 실행에서 자동 복구됩니다.</li>")
        if short3:
            items.append(f"<li><strong>3년 축 미측정 {short3}개 테마</strong> — "
                         "상장 3년 이상 종목이 없어 장기 미반영(U4)을 잴 수 없습니다. "
                         "조회 실패가 아니라 이력 부족입니다.</li>")
        from .sources import PRICES_FROM_SNAPSHOT
        if PRICES_FROM_SNAPSHOT:
            from .sources import _price_snapshot
            gen = _price_snapshot().get("generated", "?")
            items.append(f"<li><strong>주가 스냅샷 폴백 {len(PRICES_FROM_SNAPSHOT)}종목</strong> "
                         f"({gen} 기준) — 실시간 조회가 막혀 동봉 스냅샷을 썼습니다. "
                         "낡은 만큼 최근 주가 축의 정밀도가 낮습니다.</li>")
        if dead_fin:
            items.append(f"<li><strong>SEC 재무 미확보 {dead_fin}개 테마</strong> — "
                         "실적·밸류에이션 축이 빠졌습니다. User-Agent 미설정 시 SEC 가 "
                         "403 을 냅니다.</li>")
        warn = ('<div class="healthwarn"><h3>데이터 결손 경고</h3><ul>'
                + "".join(items) +
                "</ul><p>아래 순위는 빠진 축을 제외하고 계산됐습니다. "
                "축이 적을수록 점수의 신뢰도가 낮습니다.</p></div>")

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>미국 섹터 스크리너 — 촉매 × 미반영</title>
<style>{CSS}</style></head>
<body><div class="viz-root"><div class="wrap">
<button class="toggle" onclick="var r=document.documentElement;
r.dataset.theme=r.dataset.theme==='dark'?'light':'dark'">라이트/다크</button>

<h1>미국 섹터 스크리너</h1>
<p class="sub">촉매(왜 오르나) × 미반영(왜 아직 안 올랐나)의 교집합으로 테마를 고른다.
목표는 오른쪽 위 사분면 — 이유는 쌓였는데 가격은 아직 안 움직인 곳.</p>
<p class="meta">{now} 기준 · 테마 {len(ranked)}개 · 목표 사분면 {n_target}개 ·
벤치마크 {_e(benchmark)} · 전 지표 무료 공공데이터(FRED·SEC·Federal Register·Yahoo) ·
<a href="backtest.html">백테스트 검증 결과</a></p>

{warn}

<nav class="tabbar">
<button class="tabbtn on" data-pane="pane-glance">한눈에</button>
<button class="tabbtn" data-pane="pane-cards">테마 상세</button>
<button class="tabbtn" data-pane="pane-table">전체 표</button>
<a class="tabbtn tablink" href="backtest.html">백테스트 ↗</a>
</nav>

<section id="pane-glance">
{_honesty_html()}
<div class="glance-grid">
<div class="g-a">
<h2>사분면 — 촉매 대비 미반영</h2>
<div class="panel">{_scatter(ranked)}</div>
</div>
<div class="g-b">
{_top_picks(ranked)}
{_changes_html(load_history())}
</div>
<div class="g-side">
{_priority_list(ranked)}
</div>
</div>
</section>

<section id="pane-cards" hidden>
{_theme_chips(ranked)}
<div class="cardcols">
{cards}
</div>
</section>

<section id="pane-table" hidden>
<p class="rankrule">정렬 기준: <code>√(촉매 × 미반영) × 신뢰도 × 게이트</code>
 — <strong>기하평균이라 한쪽이 0이면 총점도 0</strong>이다. 촉매가 죽은 테마는 아무리
 눌려 있어도 후보가 아니다(싼 데는 이유가 있을 수 있다). 신뢰도는 살아있는 촉매 축의
 비율로, 축 3개로 낸 점수와 축 9개로 낸 점수를 같은 저울에 올리지 않기 위한 할인이다.</p>
<div class="panel">{_summary_table(ranked)}</div>
</section>

<script>{TAB_JS}</script>

<div class="foot">
<p><strong>읽는 법.</strong> 촉매 점수는 9개 축(낙수·공급여력·신기술·설비노후·정책·캐펙스·스프레드·재고·병목)의
평균, 미반영 점수는 4개 축(실적변곡·밸류에이션·주가미반응·눌림)의 평균이다. 모든 점수는
<em>자기 자신의 과거 대비 분위</em>로 환산한 0~100이며, 데이터가 없는 축은 0점이 아니라
평균에서 제외된다(커버리지로 표시). 게이트는 미반영 축 4개 중 60점 이상이 몇 개인지를 뜻한다.</p>
<p><strong>한계.</strong> 컨센서스 추정치 리비전은 무료로 구할 수 없어 SEC XBRL 기반
TTM 매출 증가율의 가속도로 대신했다. 실제 리비전보다 2~3개월 늦다. 재무 집계는 해당
분기를 보고한 기업이 그룹의 60% 이상일 때만 채택해 구성 변화로 인한 급변을 배제했다.
이 도구는 <em>후보를 좁히는 장치</em>이지 매수 판단이 아니다 — 각 축의 '근거↗'를 눌러
원본을 확인하고 판단하라.</p>
<p>테마 추가·수정은 <code>themes.yaml</code>. 재실행 <code>python run.py</code>.</p>
</div>
</div></div></body></html>"""
