"""HTML 대시보드 생성 — 외부 의존 없는 단일 파일."""
from __future__ import annotations

import html
import json
from datetime import datetime

from .signals import ThemeResult

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


def _signal_rows(sigs, *, show_status: bool = True) -> str:
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
        ev = (f' <a class="ev" href="{_e(s.evidence)}" target="_blank" rel="noopener">근거↗</a>'
              if s.evidence else "")
        reason = getattr(s, "reason", "")
        why = f'<div class="why">{_e(reason)}</div>' if reason else ""
        body = _e(s.detail) if s.detail else ""
        rows.append(
            f'<tr class="{cls}"><th scope="row">{_e(s.label)}{tag}</th>'
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
                 f'목표 구역</text>')
    parts.append(f'<text x="{sx(98):.0f}" y="{sy(3):.0f}" class="quadlab dim" text-anchor="end">'
                 f'이미 반영됨</text>')

    for r in pts:
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
        parts.append(f'<text x="{x + dx:.1f}" y="{y + 4:.1f}" class="ptlab" '
                     f'text-anchor="{anchor}">{_e(r.name)}</text>')

    parts.append("</svg>")

    legend = "".join(
        f'<span class="lg"><i style="background:{c}"></i>{_e(n)} <em>{_e(rng)}</em></span>'
        for n, rng, c in BUCKETS)
    return "".join(parts) + f'<div class="legend">{legend}</div>'


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

    nc = sp.get("n_customers", 0)
    cust_txt = f" · 고객군 {nc}개사" if nc else " · 고객군 미지정"
    tops = r.top_axes
    drivers = ("점수를 만든 축: "
               + " / ".join(f"<strong>{_e(s.label)}</strong> {s.effective:.0f}" for s in tops)
               ) if tops else "주장한 촉매 축이 전부 죽어 있음"

    # 논지 성립 여부 — 이 도구의 가장 중요한 출력.
    # "무엇이 마침 높나"가 아니라 "내가 말한 이유가 데이터로 서나"를 답한다.
    TH = {"성립": ("good", "논지 성립"), "미확증": ("warn", "논지 미확증"),
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
<article class="card">
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
  <p class="tick-list">{_e(" · ".join(r.tickers))}
     <em>· SEC 재무 {sp.get('n_companies', 0)}개사{cust_txt} · 살아있는 축 {r.coverage:.0f}%
     · 기각 {r.n_rejected}개</em></p>
  {thesis_line}
  <p class="drivers">{drivers}</p>
  {inc_line}
  <div class="sparks">{''.join(sparks)}</div>
  <div class="tables">
    <div>
      <h4>촉매 축 — 왜 오를 이유가 있나 <em>(점수는 최강 2개 축의 평균)</em></h4>
      <table class="sig"><tbody>{_signal_rows(r.catalyst)}</tbody></table>
    </div>
    <div>
      <h4>미반영 축 — 왜 아직 안 올랐나</h4>
      <table class="sig"><tbody>{_signal_rows(r.unpriced, show_status=False)}</tbody></table>
    </div>
  </div>
  {notes}
</article>"""


def _summary_table(results: list[ThemeResult]) -> str:
    rows = []
    for i, r in enumerate(results, 1):
        cs = "—" if r.catalyst_score is None else f"{r.catalyst_score:.0f}"
        us = "—" if r.unpriced_score is None else f"{r.unpriced_score:.0f}"
        rows.append(f"<tr><td class='num'>{i}</td><th scope='row'>{_e(r.name)}</th>"
                    f"<td>{_e(r.lead_time)}</td><td class='num'>{cs}</td>"
                    f"<td class='num'>{us}</td><td class='num'>{r.gate_passed}</td>"
                    f"<td class='num'>{r.coverage:.0f}%</td></tr>")
    return ("<table class='summary'><thead><tr><th>#</th><th>테마</th><th>리드타임</th>"
            "<th>촉매</th><th>미반영</th><th>게이트</th><th>커버리지</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


CSS = """
.viz-root{color-scheme:light;--surface-1:#fcfcfb;--plane:#f9f9f7;--text-primary:#0b0b0b;
--text-secondary:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--border:rgba(11,11,11,.10);--series-1:#2a78d6;--series-2:#eb6834;--series-3:#1baf7a;
--good:#0ca30c;--warning:#fab219;--critical:#d03b3b;--seq-200:#9ec5f4;--seq-450:#2a78d6}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{
color-scheme:dark;--surface-1:#1a1a19;--plane:#0d0d0d;--text-primary:#fff;
--text-secondary:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
--border:rgba(255,255,255,.10);--series-1:#3987e5;--series-2:#d95926;--series-3:#199e70;
--seq-200:#184f95;--seq-450:#3987e5}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;--surface-1:#1a1a19;--plane:#0d0d0d;
--text-primary:#fff;--text-secondary:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
--border:rgba(255,255,255,.10);--series-1:#3987e5;--series-2:#d95926;--series-3:#199e70;
--seq-200:#184f95;--seq-450:#3987e5}
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
.healthwarn{margin:16px 0 0;padding:14px 18px;border-radius:12px;
background:var(--surface-1);border:1px solid var(--critical);
border-left:4px solid var(--critical)}
.healthwarn h3{margin:0 0 8px;font-size:13px;color:var(--critical);letter-spacing:.01em}
.healthwarn ul{margin:0 0 8px 18px;padding:0;font-size:12.5px;color:var(--text-secondary)}
.healthwarn li{margin-bottom:4px}
.healthwarn p{margin:0;font-size:12px;color:var(--muted)}
.drivers{margin:0 0 6px;font-size:12px;color:var(--text-secondary)}
.drivers strong{color:var(--text-primary);font-weight:600}
.claim{margin:0 0 6px;font-size:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.verdict{font-size:11.5px;font-weight:600;padding:2px 9px;border-radius:6px;
border:1px solid currentColor}
.v-good{color:var(--good)}
.v-warn{color:var(--warning)}
.v-bad{color:var(--critical)}
.v-na{color:var(--muted)}
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


def build_html(results: list[ThemeResult], *, benchmark: str = "SPY") -> str:
    ranked = sorted(
        results,
        key=lambda r: -((r.catalyst_score or 0) * 0.5 + (r.unpriced_score or 0) * 0.5
                        + (12 if r.gate_passed >= 2 else 0)),
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    n_target = sum(1 for r in ranked
                   if (r.catalyst_score or 0) >= 50 and (r.unpriced_score or 0) >= 50)

    cards = "".join(_card(r, i) for i, r in enumerate(ranked, 1))

    # 판독 건강도 — 데이터가 통째로 안 들어온 것을 조용히 넘기지 않는다.
    # 주가가 죽으면 미반영 축 4개 중 2개가 사라지는데, 점수만 보면 눈치채기 어렵다.
    dead_px = sum(1 for r in ranked
                  if any(s.key in ("U3", "U4") and s.score is None for s in r.unpriced))
    dead_fin = sum(1 for r in ranked if not r.series.get("n_companies"))
    warn = ""
    if dead_px or dead_fin:
        items = []
        if dead_px:
            items.append(f"<li><strong>주가 미확보 {dead_px}/{len(ranked)}개 테마</strong> — "
                         "‘주가 미반응’·‘고점 대비 눌림’ 두 축이 빠졌습니다. "
                         "Yahoo 가 클라우드 IP 를 차단했을 수 있습니다(Stooq 폴백도 실패).</li>")
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
벤치마크 {_e(benchmark)} · 전 지표 무료 공공데이터(FRED·SEC·Federal Register·Yahoo)</p>

{warn}
<h2>사분면 — 촉매 대비 미반영</h2>
<div class="panel">{_scatter(ranked)}</div>

<h2>테마별 상세</h2>
{cards}

<h2>전체 표</h2>
<div class="panel">{_summary_table(ranked)}</div>

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
