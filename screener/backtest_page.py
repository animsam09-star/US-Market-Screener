# -*- coding: utf-8 -*-
"""백테스트 결과를 '읽는 사람 말'로 보여주는 페이지(/backtest.html).

종전 페이지는 마크다운 원문을 <pre> 로 찍어 표 기호와 전문 용어(IC·중앙값·
스냅샷)가 그대로 노출됐다 — "내가 이해하기 쉽게 알려줘야 해". 결론을 맨 위에
한 문장으로, 그다음 '어떻게 검사했나 → 판정별 성적 → 믿을 만한 근거 →
틀렸던 때 → 시기별 차이 → 주의할 점' 순서로 풀고, 숫자 원문은 맨 아래 접기로
남긴다(전문 용어는 거기서만).

입력은 backtest.analyze() 결과와 관측 원장(records) — 계산은 새로 하지 않고
같은 숫자를 다른 말로 옮긴다(판정별 성적은 ana['by_verdict'] 그대로).
"""
from __future__ import annotations

import html as _html
import re

_e = _html.escape

ORDER = ["볼 만함", "지켜볼 만", "이미 반영", "되돌림", "이유 약함", "지금은 아님"]

MEANING = {
    "볼 만함": "오를 이유가 확인됐고 주가는 아직 덜 오름 — 믿을 만한 근거가 이끄는 경우",
    "지켜볼 만": "조건은 같지만 이끄는 근거가 시기에 따라 맞다 틀렸다 한 종류",
    "이미 반영": "오를 이유는 있는데 주가가 이미 앞서 오름",
    "되돌림": "크게 오른 뒤 꺾여 내려오는 중 — 싸 보여도 과열의 되돌림",
    "이유 약함": "많이 눌려 있지만 오를 근거가 데이터로 확인 안 됨",
    "지금은 아님": "근거도 약하고 가격도 유리하지 않음",
}

AXIS_PLAIN = {
    "A1": ("전방 산업 회복", "고객 산업이 살아나 주문이 넘어오는가"),
    "A2": ("공급 부족", "증산 여력이 없어 공급이 빡빡한가"),
    "A4": ("설비 교체 시기", "고객 설비가 늙어 바꿀 때가 됐는가"),
    "A6": ("투자 부족", "수년간 투자를 안 해 공급이 줄었는가"),
    "A7": ("마진 확대", "판가는 버티는데 원가가 내리는가"),
    "A8": ("재고 바닥", "재고가 말라 다시 채울 때인가"),
    "A9": ("주문 밀림", "수주가 밀려 값을 올려 받을 수 있는가"),
}


def _n_win(d: dict) -> int:
    return int(round(d["hit"] * d["n"] / 100.0))


def _pct(v: float) -> str:
    return f"{v:+.0f}%p" if abs(v) >= 10 else f"{v:+.1f}%p"


def _stats(rs: list) -> dict | None:
    v = [r["fwd12"] for r in rs if r.get("fwd12") is not None]
    if not v:
        return None
    return {"n": len(v), "mean": sum(v) / len(v),
            "hit": 100.0 * sum(1 for x in v if x > 0) / len(v)}


def _md_tables_to_html(md: str) -> str:
    """기술 부록 — 마크다운 표·문단을 실제 HTML 로(기호 노출 방지)."""
    out, rows = [], []

    def flush():
        if not rows:
            return
        head, body = rows[0], [r for r in rows[2:]]
        out.append("<table class='raw'><thead><tr>"
                   + "".join(f"<th>{_e(c)}</th>" for c in head) + "</tr></thead><tbody>"
                   + "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in r) + "</tr>"
                             for r in body) + "</tbody></table>")
        rows.clear()

    for ln in md.splitlines():
        if ln.startswith("|"):
            rows.append([c.strip() for c in ln.strip().strip("|").split("|")])
            continue
        flush()
        if ln.startswith("# "):
            continue
        if ln.startswith("## ") or ln.startswith("### "):
            out.append(f"<h4>{_e(ln.lstrip('#').strip())}</h4>")
        elif ln.strip():
            t = _e(ln.lstrip("- ").strip())
            t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
            out.append(f"<p>{t}</p>")
    flush()
    return "\n".join(out)


def build(result: dict, ana: dict, md: str, stable: set | None = None) -> str:
    recs = result["records"]
    snaps = result["snapshots"]
    bench = result.get("benchmark", "SPY")
    bv = ana["by_verdict"]
    best, low = bv.get("볼 만함"), bv.get("지금은 아님")
    y0, y1 = snaps[0][:4], snaps[-1][:4]

    # ---- 1. 결론 -------------------------------------------------------
    if best:
        head = (f"‘볼 만함’ 판정대로 샀다면 과거 {best['n']}번 중 "
                f"<b>{_n_win(best)}번({best['hit']:.0f}%)</b> 1년 뒤 시장보다 더 올랐고, "
                f"평균 <b>{_pct(best['mean'])}</b> 더 벌었습니다.")
        rest = [bv[t] for t in ORDER if t in bv and t != "볼 만함"]
        lo_h = min(d["hit"] for d in rest) if rest else 0
        hi_h = max(d["hit"] for d in rest) if rest else 0
        sub = (f"나머지 판정들은 승률 {lo_h:.0f}~{hi_h:.0f}%로 동전 던지기와 큰 차이가 "
               "없었습니다 — 이 도구가 쓸모 있는 건 ‘볼 만함’을 골라낼 때입니다. "
               f"다만 ‘볼 만함’은 {y0}~{y1}년 동안 {best['n']}번뿐인 드문 신호라, "
               "없는 날이 대부분입니다.")
    else:
        head, sub = "‘볼 만함’ 판정이 나온 적이 없어 성적을 낼 수 없습니다.", ""
    if best and low:
        sub += (f" 비교: ‘지금은 아님’은 {low['n']}번 중 {_n_win(low)}번"
                f"({low['hit']:.0f}%)만 시장을 이겼습니다.")

    # ---- 3. 판정별 막대 --------------------------------------------------
    mx = max((abs(bv[t]["mean"]) for t in ORDER if t in bv), default=1) or 1
    bars = []
    for t in ORDER:
        d = bv.get(t)
        if not d:
            continue
        w = abs(d["mean"]) / mx * 100
        cls = "up" if d["mean"] >= 0 else "dn"
        med_note = ""
        if d["mean"] - d["median"] > 8:
            med_note = (f"<div class='vnote'>※ 평균은 몇 번의 큰 상승이 끌어올린 값 — "
                        f"보통의 경우(가운데 값)는 {_pct(d['median'])}</div>")
        bars.append(
            f"<div class='vrow'><div class='vname'><b>{_e(t)}</b>"
            f"<span>{_e(MEANING.get(t, ''))}</span></div>"
            f"<div class='vbar'><i class='{cls}' style='width:{w:.0f}%'></i>"
            f"<em class='{cls}'>{_pct(d['mean'])}</em></div>"
            f"<div class='vwin'><b>{_n_win(d)}</b> / {d['n']}번 이김"
            f"<span class='hit'><i style='width:{d['hit']:.0f}%'></i></span>"
            f"<small>{d['hit']:.0f}%</small></div>{med_note}</div>")

    # ---- 4. 근거별 믿을 만함 --------------------------------------------
    axrows = []
    for k, (nm, q) in AXIS_PLAIN.items():
        d = ana["axis_ic"].get(k)
        if not d or d.get("ic") is None:
            continue
        ic, e, l = d["ic"], d.get("ic_early"), d.get("ic_late")
        if d.get("stable") or (stable and k in stable):
            tag, cls = "믿을 만함 — 시기와 상관없이 통했다", "good"
        elif ic <= -0.05 and (e or 0) < 0 and (l or 0) < 0:
            tag, cls = "반대로 움직임 — 점수가 높을수록 덜 올랐다", "bad"
        elif (e or 0) * (l or 0) < 0 and max(abs(e or 0), abs(l or 0)) >= 0.1:
            tag, cls = "시기 따라 뒤집힘 — 어떤 해엔 맞고 어떤 해엔 틀렸다", "warn"
        else:
            tag, cls = "거의 영향 없음", "na"
        cond = ""
        if (d.get("cond_n") or 0) >= 5 and d.get("cond_hit") is not None:
            cond = (f"이 근거가 1순위였던 ‘살 만한 조건’ {d['cond_n']}번 중 "
                    f"{int(round(d['cond_hit'] * d['cond_n'] / 100))}번 시장을 이김 "
                    f"({d['cond_hit']:.0f}%)")
        axrows.append(f"<tr><td><b>{_e(nm)}</b><span>{_e(q)}</span></td>"
                      f"<td><span class='tag {cls}'>{_e(tag)}</span></td>"
                      f"<td>{_e(cond) or '—'}</td></tr>")

    # ---- 5. 틀렸던 때 ----------------------------------------------------
    good_t = {"볼 만함", "지켜볼 만"}
    bad_t = {"이유 약함", "지금은 아님", "되돌림"}
    fails = sorted((r for r in recs if r.get("verdict") == "볼 만함"
                    and r.get("fwd12") is not None and r["fwd12"] < 0),
                   key=lambda r: r["fwd12"])[:4]
    miss = sorted((r for r in recs if r.get("verdict") in bad_t
                   and r.get("fwd12") is not None and r["fwd12"] > 40),
                  key=lambda r: -r["fwd12"])[:4]

    def li(r):
        return (f"<li><b>{_e(r['date'][:7])} {_e(r['theme'])}</b> — "
                f"‘{_e(r['verdict'])}’ 판정 후 1년간 시장 대비 "
                f"<span class='{'up' if r['fwd12'] >= 0 else 'dn'}'>{_pct(r['fwd12'])}</span></li>")

    # ---- 6. 시기별 -------------------------------------------------------
    dates = sorted(r["date"] for r in recs if r.get("fwd12") is not None)
    mid = dates[len(dates) // 2] if dates else "9999"
    era = []
    for nm, f in (("앞쪽 절반", lambda d: d <= mid), ("뒤쪽 절반", lambda d: d > mid)):
        sub_r = [r for r in recs if r.get("verdict") == "볼 만함" and f(r["date"])]
        s = _stats(sub_r)
        ds = [r["date"] for r in recs if f(r["date"])]
        rng = f"{min(ds)[:7]} ~ {max(ds)[:7]}" if ds else ""
        if s:
            era.append(f"<li><b>{nm}</b>({_e(rng)}): ‘볼 만함’ {s['n']}번 중 "
                       f"{_n_win(s)}번 이김({s['hit']:.0f}%), 평균 {_pct(s['mean'])}</li>")
        else:
            era.append(f"<li><b>{nm}</b>({_e(rng)}): ‘볼 만함’이 한 번도 안 나옴</li>")

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>백테스트 결과 — 미국 섹터 스크리너</title>
<script>(function(){{var t='dark';try{{t=localStorage.getItem('scr-theme')||'dark'}}catch(e){{}}
document.documentElement.dataset.theme=t}})();</script>
<style>
:root{{--bg:#fff;--card:#fff;--line:#e0e3eb;--tx:#131722;--sub:#5d606b;--mut:#8b8e98;
 --up:#089981;--dn:#f23645;--link:#2962ff;--chip:#f0f3fa;--warn:#b8860b}}
:root[data-theme="dark"]{{--bg:#000;--card:#000;--line:#2a2e39;--tx:#d1d4dc;--sub:#9598a1;
 --mut:#787b86;--up:#22ab94;--dn:#f23645;--link:#3179f5;--chip:#2a2e39;--warn:#d4a017}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--tx);
 font:16px/1.7 "Pretendard Variable",Pretendard,-apple-system,"Segoe UI","Noto Sans KR",
 "Malgun Gothic",sans-serif;font-variant-numeric:tabular-nums}}
.wrap{{max-width:1080px;margin:0 auto;padding:28px 20px 60px}}
a{{color:var(--link);text-decoration:none}}
h1{{font-size:28px;margin:6px 0 2px}}
h2{{font-size:22px;margin:40px 0 12px}}
h2::after{{content:" ›"}}
.meta{{color:var(--mut);font-size:13.5px}}
.card{{border:1px solid var(--line);border-radius:14px;padding:18px 22px;background:var(--card)}}
.hero{{border-left:5px solid var(--up);font-size:20px;line-height:1.6;margin-top:22px}}
.hero b{{color:var(--up)}}
.hero p{{margin:10px 0 0;font-size:16px;color:var(--sub)}}
.steps{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.steps .card b{{display:block;font-size:30px;color:var(--link);line-height:1}}
.steps .card{{font-size:15.5px}}
@media (max-width:760px){{.steps{{grid-template-columns:1fr}}}}
.vrow{{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1.2fr) 220px;gap:16px;
 align-items:center;padding:14px 0;border-bottom:1px solid var(--line)}}
@media (max-width:860px){{.vrow{{grid-template-columns:1fr}}}}
.vname b{{font-size:17px}}.vname span{{display:block;font-size:13.5px;color:var(--sub)}}
.vbar{{position:relative;height:28px;background:var(--chip);border-radius:6px}}
.vbar i{{position:absolute;left:0;top:0;bottom:0;border-radius:6px;opacity:.85}}
.vbar i.up{{background:var(--up)}}.vbar i.dn{{background:var(--dn)}}
.vbar em{{position:absolute;right:8px;top:2px;font-style:normal;font-weight:800;color:var(--tx)!important}}
em.up,span.up{{color:var(--up)}}em.dn,span.dn{{color:var(--dn)}}
.vwin{{display:flex;align-items:center;gap:8px;font-size:15px}}
.vwin b{{font-size:20px}}
.hit{{flex:1;height:8px;border-radius:4px;background:var(--chip);position:relative;min-width:50px}}
.hit i{{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:var(--link)}}
.vwin small{{color:var(--mut);width:36px;text-align:right}}
.vnote{{grid-column:1/-1;font-size:13px;color:var(--mut);margin-top:-6px}}
table.ax{{width:100%;border-collapse:collapse}}
table.ax td{{padding:12px 8px;border-bottom:1px solid var(--line);vertical-align:top;font-size:15px}}
table.ax td span{{display:block;font-size:13px;color:var(--sub)}}
.tag{{display:inline-block!important;padding:3px 9px;border-radius:6px;font-weight:700;
 font-size:13.5px!important}}
.tag.good{{background:rgba(34,171,148,.16);color:var(--up)!important}}
.tag.bad{{background:rgba(242,54,69,.14);color:var(--dn)!important}}
.tag.warn{{background:rgba(212,160,23,.16);color:var(--warn)!important}}
.tag.na{{background:var(--chip);color:var(--sub)!important}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
@media (max-width:760px){{.two{{grid-template-columns:1fr}}}}
.two h3{{margin:0 0 8px;font-size:17px}}
ul{{margin:6px 0;padding-left:20px}}li{{margin:5px 0}}
details{{margin-top:40px}}summary{{cursor:pointer;color:var(--sub);font-weight:700}}
table.raw{{border-collapse:collapse;margin:8px 0 16px;font-size:13.5px}}
table.raw th,table.raw td{{border:1px solid var(--line);padding:5px 10px;text-align:right}}
table.raw th:first-child,table.raw td:first-child{{text-align:left}}
details h4{{margin:22px 0 6px}}details p{{margin:4px 0;font-size:14px;color:var(--sub)}}
</style></head><body><div class="wrap">
<p><a href="./">← 대시보드로</a></p>
<h1>백테스트 — 이 도구의 판정이 실제로 맞았나</h1>
<div class="meta">{len(snaps)}개 분기({_e(snaps[0][:7])} ~ {_e(snaps[-1][:7])}) ·
 테마별 판정 {ana['n_judged']:,}건 확인 · 비교 대상: 미국 시장 전체({_e(bench)})</div>

<div class="card hero">{head}<p>{sub}</p></div>

<h2>어떻게 검사했나</h2>
<div class="steps">
<div class="card"><b>1</b>2019년부터 매 분기말로 시간을 되돌렸습니다.</div>
<div class="card"><b>2</b>그때 이미 발표돼 있던 자료만으로 판정을 다시 냈습니다
 — 나중에 나온 숫자는 쓰지 않았습니다(미래를 커닝하지 않게).</div>
<div class="card"><b>3</b>그 뒤 1년 동안 그 테마 주식들이 시장보다
 얼마나 더(덜) 올랐는지 확인했습니다.</div>
</div>

<h2>판정별 성적 — 1년 뒤 시장보다 얼마나 더 올랐나</h2>
<div class="card">{''.join(bars)}
<p class="meta" style="margin:12px 0 0">막대 = 시장보다 평균 몇 %p 더 올랐나 ·
 오른쪽 = 시장을 이긴 횟수(1년 뒤 시장보다 더 오른 경우)</p></div>

<h2>어떤 ‘오를 이유’가 믿을 만했나</h2>
<div class="card"><table class="ax">{''.join(axrows)}</table>
<p class="meta" style="margin:10px 0 0">‘믿을 만함’인 근거가 이끌 때만 ‘볼 만함’을 줍니다.
 같은 조건이라도 ‘시기 따라 뒤집힘’ 근거가 이끌면 ‘지켜볼 만’으로 한 단계 낮춥니다.</p></div>

<h2>틀렸던 때</h2>
<div class="two">
<div class="card"><h3>‘볼 만함’이었는데 시장보다 못했던 경우</h3>
<ul>{''.join(li(r) for r in fails) or '<li>없음</li>'}</ul></div>
<div class="card"><h3>낮은 판정이었는데 크게 오른 경우(놓친 상승)</h3>
<ul>{''.join(li(r) for r in miss) or '<li>없음</li>'}</ul>
<p class="meta">오를 이유가 데이터에 늦게 잡히는 테마(2~3개월 지연)의 급등은 이 도구가 놓칩니다.</p></div>
</div>

<h2>시기마다 달랐나</h2>
<div class="card"><ul>{''.join(era)}</ul>
<p class="meta">최근 몇 년은 대형 기술주가 시장을 끌어서, 이 도구가 다루는 산업 테마가
 시장을 이기기 어려운 구간이었습니다. 최근 표본이 적어 아직 단정하기 이릅니다.</p></div>

<h2>주의할 점</h2>
<div class="card"><ul>
<li><b>지금 종목 목록을 과거에 그대로 적용했습니다.</b> 그 사이 사라진 회사가 빠져
 있어 성적이 실제보다 조금 좋게 나왔을 수 있습니다.</li>
<li><b>경제 통계는 나중에 고쳐진 숫자</b>를 썼습니다(처음 발표 숫자와 조금 다를 수 있음).</li>
<li><b>분기마다 1년 뒤를 보니 기간이 겹칩니다.</b> 같은 상승이 여러 번 세어질 수 있어,
 아래 숫자 원문에 겹치지 않게 1년에 한 번만 센 결과도 함께 실었습니다.</li>
<li><b>정책·신기술 같은 근거는 과거를 다시 만들 수 없어</b> 검사에서 뺐습니다.
 그런 근거가 핵심인 테마(방산 등)는 실전과 다르게 나올 수 있습니다.</li>
<li>과거 성적이 앞으로를 보장하지 않습니다 — 확률이 어느 쪽인지 알려주는 자료입니다.</li>
</ul></div>

<details><summary>숫자 원문 보기(전문가용 — 상관계수·중앙값·6개월 성적 등)</summary>
{_md_tables_to_html(md)}
</details>
</div></body></html>
"""


# ================================================================ 초기 신호 성적

_EARLY_TAG = {"잘 맞았음": "good", "조금 나음": "warn", "평소와 비슷": "na", "기록 적음": "na"}
EARLY_ANCHOR = "<h2>주의할 점</h2>"


def early_section(st: dict | None) -> str:
    """초기 신호(방향이 바뀌는 순간)별 과거 성적 — screener.early_backtest 결과.

    판정 백테스트(분기)와 따로 계산한다: 신호는 매달 다시 계산하고, 지난달 꺼져 있다가
    켜진 달만 '켜짐'으로 센다. 같은 신호가 12개월 안에 다시 켜지면 한 번만 센다.
    """
    if not st or not st.get("signals"):
        return ""
    base = (st.get("base") or {}).get("fwd12") or {}
    per = st.get("period") or ["", ""]
    rows = []
    items = sorted(st["signals"].items(),
                   key=lambda kv: -((kv[1].get("fwd12") or {}).get("hit") or -1))
    for name, d in items:
        f = d.get("fwd12") or {}
        if not f:
            continue
        g = d.get("grade", "기록 적음")
        e, l_ = d.get("early") or {}, d.get("late") or {}
        era = (f"{e.get('hit', 0):.0f}% / {l_.get('hit', 0):.0f}%"
               if e and l_ else "—")
        rows.append(
            f"<tr><td><b>{_e(name)}</b></td><td>{d['n_events']}번</td>"
            f"<td><b>{f['hit']:.0f}%</b></td><td>{f['mean']:+.1f}%p</td><td>{era}</td>"
            f"<td><span class=\"tag {_EARLY_TAG.get(g, 'na')}\">{_e(g)}</span></td></tr>")
    if not rows:
        return ""
    trows = []
    for t, d in (st.get("tiers") or {}).items():
        a, e, l_ = d.get("all"), d.get("early"), d.get("late")
        if a:
            trows.append(f"<tr><td><b>{_e(t)}</b></td><td>{a['n']}</td><td><b>{a['hit']:.0f}%</b></td>"
                         f"<td>{a['mean']:+.1f}%p</td><td>{(e or {}).get('hit', 0):.0f}% / "
                         f"{(l_ or {}).get('hit', 0):.0f}%</td></tr>")
    tier_html = ""
    if trows:
        tier_html = ('<h3 style="margin:22px 0 8px">더 잘 맞히는 조합 — 강도 단계</h3>'
                     '<p style="margin:0 0 8px">실물 신호(재고·수주·생산·가동률·매출·선행 지표)만 세고, '
                     "앞 기간(~2018)에서 찾은 규칙이 뒤 기간(2019~)에도 맞는지 확인한 것만 남겼습니다. "
                     "원가 급락·200일선 회복·내부자 매수는 평소 수준이라 ‘참고’로 내렸습니다.</p>"
                     '<table class="raw"><tr><th>단계</th><th>테마×달 관측</th><th>시장보다 더 오른 비율</th>'
                     "<th>평균(시장 대비)</th><th>2019년 전 / 후</th></tr>" + "".join(trows) + "</table>"
                     '<p class="meta">관측은 매달 세므로 같은 상승이 몇 달 겹쳐 세어집니다 — 단계끼리의 상대 비교로 보세요.</p>')
    return (f"<h2>초기 신호는 맞았나 — 방향이 바뀌는 순간</h2>"
            f"<div class=\"card\"><p style=\"margin:0 0 10px\">대시보드 위쪽 ‘먼저 보이는 가능성’에 뜨는 "
            f"신호들입니다. {_e((per[0] or '')[:4])}년부터 매달 그때 알 수 있던 자료로 다시 계산해, "
            f"신호가 <b>새로 켜진 달</b>부터 1년 동안 그 테마가 시장보다 더 올랐는지 셌습니다. "
            f"아무 때나 골랐을 때 더 오른 비율은 <b>{base.get('hit', 0):.0f}%</b>"
            f"(평균 {base.get('mean', 0):+.1f}%p) — 이보다 높아야 쓸모 있는 신호입니다.</p>"
            f"<table class=\"raw\"><tr><th>신호</th><th>켜진 횟수</th><th>시장보다 더 오른 비율</th>"
            f"<th>평균(시장 대비)</th><th>2019년 전 / 후</th><th>판단</th></tr>{''.join(rows)}</table>"
            f"<p class=\"meta\" style=\"margin:8px 0 0\">‘잘 맞았음’ = 평소보다 더 오른 비율이 8%p 이상 높고, "
            f"2019년 전·후 두 시기 모두 평소보다 나았던 것. 켜진 횟수 8번 미만은 ‘기록 적음’. "
            f"같은 신호가 12개월 안에 다시 켜지면 한 번만 셌습니다. 내부자 매수는 SEC 일괄 자료"
            f"(2009년~), 애널리스트 의견·EPS 추정치는 과거 자료가 없어 오늘부터 기록합니다.</p>"
            + tier_html + "</div>\n")


def inject_early(page: str, st: dict | None) -> str:
    sec = early_section(st)
    if not sec or EARLY_ANCHOR not in page or "초기 신호는 맞았나" in page:
        return page
    return page.replace(EARLY_ANCHOR, sec + EARLY_ANCHOR, 1)
