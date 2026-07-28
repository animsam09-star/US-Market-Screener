"""촉매 축 판별식 — 설계_촉매판별.md 의 구현.

각 축은 지표 하나가 아니라 세 요소로 판정한다.

    주장(claim)   관측 가능한 명제
    확증(confirm) 독립된 두 번째 데이터가 같은 말을 하는가
    기각(reject)  같은 숫자를 만드는 '나쁜 이유'를 배제했는가

기각에 걸리면 점수 0이 아니라 status="rejected" + 사유를 남긴다.
조용한 0점은 '신호가 약함'과 '논리가 틀림'을 구별하지 못하게 만든다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .stats import best_lag, freq_periods, last, pct_rank, scale, slope, yoy

FRED_URL = "https://fred.stlouisfed.org/series/{}"


@dataclass
class Signal:
    key: str
    label: str
    score: float | None = None
    status: str = "nodata"        # ok | unconfirmed | rejected | nodata
    detail: str = ""
    reason: str = ""              # 기각·미확증 사유
    evidence: str = ""
    raw: float | None = None

    @property
    def effective(self) -> float | None:
        """합산에 실제로 쓰이는 점수."""
        if self.score is None or self.status in ("rejected", "nodata"):
            return None
        return self.score * (0.5 if self.status == "unconfirmed" else 1.0)


def _nodata(key, label, why) -> Signal:
    return Signal(key, label, None, "nodata", "", why)


def _reject(key, label, why, detail="") -> Signal:
    return Signal(key, label, 0.0, "rejected", detail, why)


# ---------------------------------------------------------------- ① 낙수

def a1_downstream(cust: dict, group: dict, cfg: dict, fred) -> Signal:
    """고객 지표가 올랐고, 전이 관계가 실증되며, 아직 전이가 안 끝났는가."""
    K = ("A1", "① 낙수(전방 전이)")
    sid = (cust or {}).get("series")
    rev = group.get("rev_yoy_series") or []
    if not sid:
        return _nodata(*K, "고객군 미지정 — themes.yaml 의 customers.series 필요")
    if len(rev) < 10:
        return _nodata(*K, "그룹 TTM 매출 이력 부족(10분기 미만)")
    try:
        s = fred(sid)
    except Exception as e:
        return _nodata(*K, f"고객 지표 조회 실패: {e}")

    # 고객 지표를 분기로 맞춘 뒤 YoY 로 변환 (명목 아닌 실질 지수를 쓴다는 전제)
    cg = yoy(s, freq_periods(s))
    if len(cg) < 12:
        return _nodata(*K, "고객 지표 이력 부족")
    cq = _to_quarterly(cg)
    driver = [v for _, v in cq]
    follower = [v for _, v in rev]

    bl = best_lag(driver, follower, max_lag=8)
    if bl is None:
        return _nodata(*K, "시차상관 계산 불가")
    k, c = bl
    if k < 1 or c < 0.25:
        return _reject(*K,
                       f"전이 관계 미실증 (최적시차 {k}분기, 상관 {c:.2f} < 0.25). "
                       "고객 지표와 그룹 매출이 선행-후행 관계로 움직인 적이 없다",
                       f"시차 {k}분기 / 상관 {c:.2f}")

    cur = driver[-1]
    rank = pct_rank(cur, driver[-40:])
    if rank is None:
        return _nodata(*K, "고객 지표 분위 계산 불가")

    # 아직 안 넘어온 몫: 고객은 올랐는데 그룹 매출은 얼마나 따라왔나
    cust_up = sum(driver[-k:]) / k if k else cur
    grp_up = follower[-1]
    residual = max(0.0, 1.0 - (grp_up / cust_up if cust_up > 0 else 1.0))
    residual = min(residual, 1.0)

    sc = rank * min(c / 0.6, 1.0) * (0.35 + 0.65 * residual)
    detail = (f"고객 지표 YoY {cur:+.1f}% (5년 {rank:.0f}분위), 전이 시차 {k}분기·상관 {c:.2f}, "
              f"미전이 잔여 {residual * 100:.0f}%")

    # 확증: 그룹 재고나 수주가 늘고 있어야 '주문이 실제로 들어오는 중'
    inv = group.get("inv_yoy")
    if inv is None:
        return Signal(*K, sc, "unconfirmed", detail,
                      "확증 실패: 그룹 재고 증감 미확인", FRED_URL.format(sid), cur)
    if inv <= -5:
        return Signal(*K, sc, "unconfirmed", detail,
                      f"확증 실패: 그룹 재고 YoY {inv:+.1f}% — 주문 유입 증거 없음",
                      FRED_URL.format(sid), cur)
    return Signal(*K, sc, "ok", detail + f", 그룹 재고 YoY {inv:+.1f}%",
                  "", FRED_URL.format(sid), cur)


def _to_quarterly(monthly: list[tuple[date, float]]) -> list[tuple[tuple[int, int], float]]:
    buck: dict[tuple[int, int], list[float]] = {}
    for d, v in monthly:
        buck.setdefault((d.year, (d.month - 1) // 3 + 1), []).append(v)
    return [(k, sum(v) / len(v)) for k, v in sorted(buck.items())]


# ---------------------------------------------------------------- ② 공급

def a2_supply(cfg: dict, fred) -> Signal:
    """가동률만 보면 사양산업을 shortage 로 오독한다. 능력·생산·가동률을 같이 본다."""
    K = ("A2", "② 공급 비탄력")
    u_id, cap_id, ip_id = (cfg.get("capacity_utilization"),
                           cfg.get("capacity_index"),
                           cfg.get("industrial_production"))
    if not u_id:
        return _nodata(*K, "가동률 시리즈 미지정")
    try:
        u = fred(u_id)
    except Exception as e:
        return _nodata(*K, f"가동률 조회 실패: {e}")

    cur_u = last(u)
    rank_u = pct_rank(cur_u, [v for d, v in u if d.year >= date.today().year - 10])
    if rank_u is None:
        return _nodata(*K, "가동률 이력 부족")

    a = p = None
    if cap_id:
        try:
            cs = fred(cap_id)
            a = yoy(cs, freq_periods(cs))[-1][1]
        except Exception:
            pass
    if ip_id:
        try:
            ps = fred(ip_id)
            p = yoy(ps, freq_periods(ps))[-1][1]
        except Exception:
            pass

    base = f"가동률 {cur_u:.1f}% (10년 {rank_u:.0f}분위)"
    if a is not None:
        base += f", 생산능력 YoY {a:+.1f}%"
    if p is not None:
        base += f", 생산 YoY {p:+.1f}%"

    # 기각 ①: 설비를 닫아서 가동률만 오른 사양산업
    if a is not None and p is not None and a < 0 and p < 0:
        return _reject(*K, "사양산업 — 생산능력과 생산이 동시에 감소. "
                           "수요가 늘어 가동률이 오른 게 아니라 설비를 닫아서 오른 것", base)
    # 기각 ②: 증설이 이미 오는 중
    if a is not None and a > 3.0:
        return _reject(*K, f"증설 진행 중 — 생산능력 YoY {a:+.1f}% (>+3%). "
                           "공급이 이미 늘고 있어 부족이 해소된다", base)

    sc = rank_u
    if a is not None:
        sc = rank_u * (1.0 if a <= 1.0 else max(0.3, 1.0 - (a - 1.0) / 2.0))

    if a is None or p is None:
        return Signal(*K, sc, "unconfirmed", base,
                      "확증 실패: 생산능력·생산 지수 미지정 — 사양산업 여부를 가릴 수 없음",
                      FRED_URL.format(u_id), cur_u)
    if p <= 0:
        return Signal(*K, sc, "unconfirmed", base,
                      f"확증 실패: 생산 YoY {p:+.1f}% — 수요 증가 증거 없음",
                      FRED_URL.format(u_id), cur_u)
    return Signal(*K, sc, "ok", base, "", FRED_URL.format(u_id), cur_u)


# ---------------------------------------------------------------- ③ 신기술

def a3_newtech(theme: dict, group: dict, fts) -> Signal:
    """언급 건수가 아니라 언급 '기업 수'와 SIC 집중도로 본다."""
    K = ("A3", "③ 신기술 확산")
    kws = theme.get("edgar_keywords") or []
    if not kws:
        return _nodata(*K, "edgar_keywords 미지정")

    today = date.today()
    cur, pre = {"h": 0, "e": set(), "sic": {}}, {"h": 0, "e": set()}
    censored = False
    for kw in kws:
        c = fts(kw, _shift(today, -12).isoformat(), today.isoformat())
        p = fts(kw, _shift(today, -24).isoformat(), _shift(today, -12).isoformat())
        cur["h"] += c["hits"]
        cur["e"] |= set(c["entities"])
        for s, n in c["sic"]:
            cur["sic"][s] = cur["sic"].get(s, 0) + n
        censored |= c["censored"]
        pre["h"] += p["hits"]
        pre["e"] |= set(p["entities"])

    nb, pb = len(cur["e"]), len(pre["e"])
    if cur["h"] + pre["h"] < 10:
        return _nodata(*K, f"언급량 부족 (최근12M {cur['h']}건 / 직전 {pre['h']}건) — 키워드 재검토")

    tot = sum(cur["sic"].values()) or 1
    top3 = sum(sorted(cur["sic"].values(), reverse=True)[:3]) / tot
    new_entrants = len(cur["e"] - pre["e"]) / max(nb, 1)

    detail = (f"언급 기업 {pb}개사 → {nb}개사{'(30 상한)' if censored else ''}, "
              f"건수 {pre['h']}→{cur['h']}, 신규진입 {new_entrants * 100:.0f}%, "
              f"상위3 SIC 집중도 {top3 * 100:.0f}%")

    # 기각: 언급이 무관한 산업에 산발 = 버즈워드
    if top3 < 0.25:
        return _reject(*K, f"버즈워드 — 상위3 SIC 집중도 {top3 * 100:.0f}% (<25%). "
                           "특정 산업에 뿌리내리지 않고 산발적으로 언급되는 단어", detail)

    growth = 100.0 * (nb / pb - 1.0) if pb else 100.0
    sc = (scale(growth, -10, 90) or 0) * 0.6 + (scale(new_entrants * 100, 5, 45) or 0) * 0.4
    if top3 < 0.40:
        sc *= 0.75

    # 확증: 언급이 늘었으면 실물(매출·capex)이 붙어야 한다
    rev = group.get("rev_yoy_series") or []
    rev_now = rev[-1][1] if rev else None
    if rev_now is None:
        return Signal(*K, sc, "unconfirmed", detail, "확증 실패: 그룹 매출 확인 불가")
    if rev_now < 2:
        return Signal(*K, sc, "unconfirmed", detail,
                      f"테마 단계 — 언급은 늘었으나 그룹 매출 YoY {rev_now:+.1f}%로 실물 미확인")
    return Signal(*K, sc, "ok", detail + f", 그룹 매출 YoY {rev_now:+.1f}%")


def _shift(d: date, months: int) -> date:
    y, m = d.year, d.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return date(y, m, min(d.day, 28))


# ---------------------------------------------------------------- ④ 교체주기

def a4_replacement(cust_fin: dict) -> Signal:
    """고객의 설비가 늙었고, 교체를 미뤄왔는가. 대상은 테마가 아니라 고객이다."""
    K = ("A4", "④ 교체주기(고객 설비)")
    if not cust_fin:
        return _nodata(*K, "고객군 미지정 — customers.tickers 필요")
    age = cust_fin.get("ppe_age")
    if age is None:
        return _nodata(*K, "고객 PP&E 총액/감가상각누계 미공시")

    rank = pct_rank(age, cust_fin.get("ppe_age_hist") or [])
    ratios = cust_fin.get("capex_dep_series") or []
    suppressed = 0
    for _, r in reversed(ratios):
        if r < 1.0:
            suppressed += 1
        else:
            break
    years = suppressed / 4.0

    base = rank if rank is not None else (scale(age, 0.35, 0.75) or 0)
    sc = base * min(0.4 + years / 4.0, 1.0)
    detail = (f"고객 설비 소진율 {age * 100:.0f}%"
              + (f" (자체 이력 {rank:.0f}분위)" if rank is not None else "")
              + f", capex<감가상각 지속 {years:.1f}년")

    # 기각: 쇠퇴 산업은 늙은 설비를 교체하지 않고 폐기한다
    crev = cust_fin.get("rev_yoy_series") or []
    if crev:
        cur = crev[-1][1]
        if cur < -3:
            return _reject(*K, f"고객 산업 축소 — 고객 매출 YoY {cur:+.1f}%. "
                               "쇠퇴 산업은 늙은 설비를 교체하지 않고 폐기한다", detail)
    else:
        return Signal(*K, sc, "unconfirmed", detail, "확증 실패: 고객 매출 추이 확인 불가")

    # 확증: 교체가 실제로 시작됐는가 (capex/D&A 가 1.0 을 상향 돌파)
    if ratios and ratios[-1][1] >= 1.0 and len(ratios) > 4 and ratios[-5][1] < 1.0:
        return Signal(*K, min(100.0, sc * 1.15), "ok",
                      detail + f", 고객 capex/감가상각 {ratios[-1][1]:.2f} — 교체 시작됨")
    return Signal(*K, sc, "unconfirmed", detail,
                  "확증 실패: 고객 capex/감가상각이 아직 1.0을 넘지 못함 — 교체 개시 전")


# ---------------------------------------------------------------- ⑤ 정책

def a5_policy(theme: dict, fr: dict) -> Signal:
    """이미 시행된 규제는 이미 반영됐다. 앞으로 올 것만 신호다.

    선행 신호는 최종규칙이 아니라 입안예고에 있다(최종규칙은 공표 30~60일이면
    발효돼 선행 구간이 없다). 그리고 경제영향 1억달러 이상(significant)만 센다 —
    그러지 않으면 정기 감항성 지침 같은 일상 행정문서가 신호를 덮는다.
    """
    K = ("A5", "⑤ 정책 강제수요")
    if not (theme.get("fedreg_terms") or []):
        return _nodata(*K, "fedreg_terms 미지정")
    if not fr:
        return _nodata(*K, "Federal Register 조회 실패")

    n_rule, n_pro = fr.get("n_rule", 0), fr.get("n_proposed", 0)
    total = n_rule + n_pro
    if total == 0:
        return Signal(*K, 0.0, "ok",
                      "최근 12개월 중요 입안예고 0건, 시행 예정 중요 최종규칙 0건 — "
                      "이 테마를 밀어줄 규제 움직임이 관측되지 않음")

    # 입안예고가 선행 신호의 본체다. 최종규칙은 이미 늦은 쪽이라 절반만 친다.
    weighted = n_pro + 0.5 * n_rule
    sc = scale(weighted, 0, 8) or 0

    items = fr.get("items") or []
    match = fr.get("n_agency_match", 0)
    if match:
        sc = min(100.0, sc * 1.25)      # 소관기관 일치는 게이트가 아니라 가중치
    top = items[0] if items else None
    detail = (f"중요 입안예고 {n_pro}건(최근 12M), 시행 예정 중요 최종규칙 {n_rule}건, "
              f"소관기관 일치 {match}건"
              + (f" — {top['title'][:80]}" if top else ""))

    if not match:
        return Signal(*K, sc * 0.6, "unconfirmed", detail,
                      "확증 실패: 지정한 소관기관과 일치하는 규칙이 없음 — "
                      "검색어가 다른 분야의 규칙을 잡았을 수 있다",
                      top["url"] if top else "", float(total))
    return Signal(*K, sc, "ok", detail, "", top["url"] if top else "", float(total))


# ---------------------------------------------------------------- ⑥ 캐펙스

def a6_capex(group: dict, cfg: dict, fred) -> Signal:
    """D&A 는 역사적 원가라 대체투자 필요액을 과소평가한다. 임계는 1.2."""
    K = ("A6", "⑥ 캐펙스 고갈")
    r = group.get("capex_dep_3y")
    if r is None:
        return _nodata(*K, "capex/감가상각 산출 불가")
    sc = scale(1.2 - r, 0.0, 0.9) or 0
    cur = group.get("capex_dep_now")
    detail = f"capex/감가상각 3년평균 {r:.2f}배" + (f", 최근 {cur:.2f}배" if cur else "")

    # 기각: 자산경량화면 공급 축소가 아니다
    ppe_rev = group.get("ppe_to_rev_series") or []
    if len(ppe_rev) >= 8:
        tr = slope(ppe_rev, 8)
        if tr is not None and tr < -0.004:
            return _reject(*K, "자산경량화 — PP&E/매출 비중이 추세적으로 하락 중. "
                               "설비 투자가 적은 게 공급 축소가 아니라 사업 구조 변화다", detail)

    # 확증: 산업 능력지수가 실제로 안 늘어야 한다
    cap_id = cfg.get("capacity_index")
    if not cap_id:
        return Signal(*K, sc, "unconfirmed", detail, "확증 실패: 산업 생산능력 지수 미지정")
    try:
        cs = fred(cap_id)
        a = yoy(cs, freq_periods(cs))[-1][1]
    except Exception:
        return Signal(*K, sc, "unconfirmed", detail, "확증 실패: 생산능력 지수 조회 실패")
    if a > 0.5:
        return Signal(*K, sc, "unconfirmed", detail + f", 산업 생산능력 YoY {a:+.1f}%",
                      f"확증 실패: 기업 재무는 투자 부족을 말하는데 산업 능력은 {a:+.1f}% 증가")
    return Signal(*K, sc, "ok", detail + f", 산업 생산능력 YoY {a:+.1f}%",
                  "", FRED_URL.format(cap_id), r)


# ---------------------------------------------------------------- ⑦ 스프레드

def a7_spread(cfg: dict, group: dict, fred) -> Signal:
    """스프레드는 벌어졌는데 마진이 아직 안 따라온 상태가 최적이다."""
    K = ("A7", "⑦ 판가-원가 스프레드")
    out_id, in_id = cfg.get("ppi_output"), cfg.get("ppi_input")
    if not (out_id and in_id):
        return _nodata(*K, "PPI 산출/투입 미지정")
    try:
        so, si = fred(out_id), fred(in_id)
    except Exception as e:
        return _nodata(*K, f"PPI 조회 실패: {e}")

    go, gi = dict(yoy(so, freq_periods(so))), dict(yoy(si, freq_periods(si)))
    common = sorted(set(go) & set(gi))
    if len(common) < 24:
        return _nodata(*K, "공통 이력 부족")
    sp = [(d, go[d] - gi[d]) for d in common]
    cur = sp[-1][1]
    out_now = go[common[-1]]
    rank = pct_rank(cur, [v for _, v in sp[-60:]])
    if rank is None:
        return _nodata(*K, "스프레드 분위 계산 불가")

    detail = f"산출−투입 PPI YoY 스프레드 {cur:+.1f}%p (5년 {rank:.0f}분위), 산출 PPI YoY {out_now:+.1f}%"

    # 기각: 판가가 원가보다 더 빠지는 중이면 수요 붕괴다
    if out_now < -5:
        return _reject(*K, f"수요 붕괴 — 산출 PPI YoY {out_now:+.1f}% (<-5%). "
                           "스프레드 수치가 좋아 보여도 판가 자체가 무너지는 중", detail)

    sc = rank
    # 확증: 실제 마진이 아직 안 따라왔을 것 (따라왔으면 이미 소진)
    m = group.get("op_margin_series") or []
    if len(m) < 6:
        return Signal(*K, sc, "unconfirmed", detail, "확증 실패: 그룹 영업이익률 확인 불가",
                      FRED_URL.format(out_id), cur)
    d_margin = m[-1][1] - m[-5][1]
    if d_margin > 1.5:
        return Signal(*K, sc * 0.6, "unconfirmed",
                      detail + f", 영업이익률 1년간 {d_margin:+.1f}%p",
                      f"이미 소진 — 마진이 이미 {d_margin:+.1f}%p 올라 스프레드가 실적에 반영됨",
                      FRED_URL.format(out_id), cur)
    return Signal(*K, sc, "ok", detail + f", 영업이익률 1년간 {d_margin:+.1f}%p (미반영분 잔존)",
                  "", FRED_URL.format(out_id), cur)


# ---------------------------------------------------------------- ⑧ 재고

def a8_inventory(cfg: dict, fred) -> Signal:
    """재고 바닥과 수요 붕괴는 지표상 똑같이 생겼고 방향은 정반대다."""
    K = ("A8", "⑧ 재고 바닥")
    # 전 제조업 총계로 폴백하면 모든 테마가 같은 점수를 받아 스크리너가 무의미해진다.
    # 산업별 시리즈가 없으면 축을 비활성한다 — 틀린 기본값보다 '없음'이 낫다.
    inv_id, sh_id = cfg.get("inventories"), cfg.get("shipments")
    if not (inv_id and sh_id):
        return _nodata(*K, "산업별 재고·출하 시리즈 미지정 — 전 제조업 총계 폴백은 "
                           "모든 테마에 같은 점수를 주므로 사용하지 않는다")
    try:
        ratio = _ratio(fred(inv_id), fred(sh_id))
    except Exception as e:
        return _nodata(*K, f"재고/출하 조회 실패: {e}")
    if len(ratio) < 36:
        return _nodata(*K, "재고/출하 이력 부족")

    cur = ratio[-1][1]
    rank = pct_rank(cur, [v for d, v in ratio if d.year >= date.today().year - 10])
    if rank is None:
        return _nodata(*K, "재고율 이력 부족")
    sc = 100.0 - rank
    detail = f"재고/출하 {cur:.2f}개월분 (10년 {rank:.0f}분위)"

    # 확증: 수요가 살아 있어야 '재입고 여지'다. 내구재는 신규수주, 비내구재는
    # 신규수주 자체가 조사되지 않으므로 출하로 대신한다.
    dg, dlab = _demand_yoy(cfg, fred)
    if dg is None:
        return Signal(*K, sc, "unconfirmed", detail, "확증 실패: 수요 지표 조회 실패")

    detail += f", {dlab} YoY {dg:+.1f}%"
    if dg <= 0:
        return _reject(*K, f"수요 붕괴 — 재고는 낮지만 {dlab}가 {dg:+.1f}%. "
                           "재입고 여지가 아니라 주문 자체가 줄어 재고가 마른 것", detail)
    return Signal(*K, sc, "ok", detail, "", FRED_URL.format(inv_id), cur)


def _ratio(num: list, den: list) -> list:
    dn = dict(den)
    return [(d, v / dn[d]) for d, v in num if dn.get(d)]


def _demand_yoy(cfg: dict, fred) -> tuple[float | None, str]:
    """수요 확증 지표. 내구재는 신규수주, 비내구재(석유·화학 등)는 출하."""
    for key, label in (("new_orders", "신규수주"), ("shipments", "출하")):
        sid = cfg.get(key)
        if not sid:
            continue
        try:
            s = fred(sid)
            return yoy(s, freq_periods(s))[-1][1], label
        except Exception:
            continue
    return None, ""


# ---------------------------------------------------------------- ⑨ 병목

def a9_bottleneck(cfg: dict, fred) -> Signal:
    """잔고가 쌓이는 이유는 둘인데 가치가 완전히 다르다."""
    K = ("A9", "⑨ 병목(수주잔고)")
    bl, sh, no_id = (cfg.get("unfilled_orders"), cfg.get("shipments"),
                     cfg.get("new_orders"))
    if not (bl and sh):
        # 비내구재(석유·화학 등)는 수주잔고 자체를 조사하지 않는다 — 축이 성립 안 함
        return _nodata(*K, "산업별 수주잔고/출하 시리즈 미지정. 비내구재 산업은 "
                           "수주잔고가 조사되지 않아 이 축이 성립하지 않는다")
    if not no_id:
        return _nodata(*K, "산업별 신규수주 시리즈 미지정 — 수요초과형과 생산차질형을 "
                           "가릴 수 없어 축을 비활성한다")
    try:
        ratio = _ratio(fred(bl), fred(sh))
    except Exception as e:
        return _nodata(*K, f"수주잔고/출하 조회 실패: {e}")
    if len(ratio) < 36:
        return _nodata(*K, "공통 이력 부족")

    cur = ratio[-1][1]
    rank = pct_rank(cur, [v for d, v in ratio if d.year >= date.today().year - 10])
    if rank is None:
        return _nodata(*K, "잔고배수 이력 부족")
    detail = f"수주잔고/출하 {cur:.2f}개월분 (10년 {rank:.0f}분위)"

    try:
        ns = fred(no_id)
        ng = yoy(ns, freq_periods(ns))[-1][1]
    except Exception:
        return Signal(*K, rank, "unconfirmed", detail, "확증 실패: 신규수주 조회 실패")

    detail += f", 신규수주 YoY {ng:+.1f}%"
    if ng > 1.0:
        return Signal(*K, rank, "ok", detail + " — 수요 초과형 병목", "", FRED_URL.format(bl), cur)
    return Signal(*K, rank * 0.5, "unconfirmed", detail,
                  "생산 차질형 — 신규수주는 늘지 않는데 잔고만 쌓이는 중. "
                  "공급망이 풀리면 해소된다", FRED_URL.format(bl), cur)


# ---------------------------------------------------------------- ⑩ 대체

def a10_substitution() -> Signal:
    return _nodata("A10", "⑩ 대체·점유율 이전",
                   "v1 미구현 — 세부 품목별 출하 믹스가 필요. "
                   "Census Trade(무료 키) 기반으로 v2 예정")
