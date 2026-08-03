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

def _ident(sid: str) -> tuple[str, str]:
    """'eia:X' -> ('eia','X'),  'A35STI' -> ('fred','A35STI')"""
    raw = str(sid or "").strip()
    if ":" in raw:
        a, b = raw.split(":", 1)
        return a.strip().lower(), b.strip()
    return "fred", raw


def _series_url(sid: str) -> str:
    """근거 링크. 소스가 FRED 가 아닐 수도 있다."""
    src, ident = _ident(sid)
    if src == "eia":
        from .eia import series_url
        return series_url(ident)
    return f"https://fred.stlouisfed.org/series/{ident}"


class _FredUrl:
    """기존 FRED_URL.format(x) 호출을 소스 인식형으로 유지하기 위한 어댑터."""

    @staticmethod
    def format(sid: str) -> str:
        return _series_url(sid)


FRED_URL = _FredUrl()


def _fred_pair(a: str, b: str) -> str:
    """두 계열을 한 그래프에. 비율을 주장할 때 분자만 링크하면 오해를 부른다.

    두 계열이 같은 소스일 때만 합쳐 그릴 수 있다. 소스가 다르면 분자 쪽만
    링크하되 라벨에서 비율임을 밝힌다(라벨은 호출부가 붙인다).
    """
    sa, ia = _ident(a)
    sb, ib = _ident(b)
    if sa == "fred" and sb == "fred":
        return f"https://fred.stlouisfed.org/graph/?id={ia},{ib}"
    return _series_url(a)

# 테마가 themes.yaml 에서 선언하는 촉매 이름 -> 축 키
# 테마는 '왜 오르는지'를 먼저 말해야 하고, 점수는 그 주장 안에서만 나온다.
# 선언하지 않은 축이 우연히 높다고 순위를 만들면 그건 연관성이지 논리가 아니다.
CATALYST_KEYS = {
    "낙수": "A1", "전방": "A1", "derived": "A1",
    "공급": "A2", "shortage": "A2", "공급부족": "A2",
    "신기술": "A3", "기술": "A3",
    "교체": "A4", "교체주기": "A4",
    "정책": "A5", "규제": "A5", "예산": "A5",
    "캐펙스": "A6", "capex": "A6",
    "스프레드": "A7", "마진": "A7",
    "재고": "A8",
    "병목": "A9",
    "대체": "A10", "점유율": "A10",
}


def resolve_catalysts(names: list[str]) -> tuple[set[str], list[str]]:
    """선언된 촉매 이름을 축 키로 바꾼다. 못 알아본 이름은 따로 돌려준다."""
    keys, unknown = set(), []
    for n in names or []:
        k = CATALYST_KEYS.get(str(n).strip().lower()) or CATALYST_KEYS.get(str(n).strip())
        if k:
            keys.add(k)
        else:
            unknown.append(str(n))
    return keys, unknown


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
    # 링크가 실제로 무엇을 보여주는지. 비율을 주장하면서 분자만 링크하면
    # 읽는 사람이 정반대로 이해한다(재고 금액은 늘 최고치 근처다).
    evidence_label: str = "근거"

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
    """공급 비탄력의 증명은 세 가지가 함께 서야 한다.

      ① 능력이 **장기간** 안 늘었다 (10년 CAGR — 1년 YoY 만 보면 놓친다)
      ② 가동률이 이미 높다
      ③ 수요가 오면 물량 대신 **가격**이 반응한다 (비탄력의 정의)

    실측으로 잡은 결함: 전력기기는 능력이 10년간 연 -1.0% 씩 줄었고 가동률
    92분위, 3년 가격 +10.2% vs 물량 +2.6%(4배)로 교과서적 비탄력인데,
    1년 능력 +2.0% 하나 때문에 점수가 절반으로 깎이고 있었다. 10년 수축 뒤의
    +2% 는 '증설'이 아니라 바닥에서의 미동이다.
    """
    K = ("A2", "② 공급 비탄력")
    u_id, cap_id, ip_id = (cfg.get("capacity_utilization"),
                           cfg.get("capacity_index"),
                           cfg.get("industrial_production"))
    ppi_id = cfg.get("ppi_output")
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

    # 능력: 1년 YoY + 장기(10년, 없으면 5년) CAGR
    a1 = cap10 = None
    if cap_id:
        try:
            cs = fred(cap_id)
            g = yoy(cs, freq_periods(cs))
            a1 = g[-1][1] if g else None
            cap10 = _cagr(cs, 10) or _cagr(cs, 5)
        except Exception:
            pass
    p = None
    if ip_id:
        try:
            ps = fred(ip_id)
            p = yoy(ps, freq_periods(ps))[-1][1]
        except Exception:
            pass

    base = f"가동률 {cur_u:.1f}% (10년 {rank_u:.0f}분위)"
    if cap10 is not None:
        base += f", 생산능력 10년 연 {cap10:+.1f}%"
    if a1 is not None:
        base += f" (최근 1년 {a1:+.1f}%)"
    if p is not None:
        base += f", 생산 YoY {p:+.1f}%"

    # 기각 ①: 설비를 닫아서 가동률만 오른 사양산업 (제지가 이 경우)
    if a1 is not None and p is not None and a1 < 0 and p < 0:
        return _reject(*K, "사양산업 — 생산능력과 생산이 동시에 감소. "
                           "수요가 늘어 가동률이 오른 게 아니라 설비를 닫아서 오른 것", base)
    # 기각 ②: 증설이 실제로 밀려오는 중 (반도체 +17.7% 가 이 경우)
    if a1 is not None and a1 > 3.0:
        return _reject(*K, f"증설 진행 중 — 생산능력 YoY {a1:+.1f}% (>+3%). "
                           "공급이 이미 늘고 있어 부족이 해소된다", base)

    # 점수: 가동률 분위 × 장기 정체 계수.
    # 장기 CAGR ≤ 0%/년이면 온전히, +2.5%/년 이상이면 크게 할인.
    ev = _fred_pair(cap_id, u_id) if cap_id else FRED_URL.format(u_id)
    lab = "생산능력·가동률 원계열↗" if cap_id else "근거"
    if cap10 is not None:
        factor = 1.0 - 0.65 * min(max(cap10 / 2.5, 0.0), 1.0)
        sc = rank_u * factor
    else:
        sc = rank_u * 0.7          # 장기 능력을 모르면 그만큼 할인

    # ③ 가격 반응: 3년 산출가격 vs 물량. 가격이 물량의 3배 이상 움직였고
    # 절대로도 올랐다면, 물량이 못 늘어나 가격이 대신 반응한 것이다.
    pq_note = ""
    pq_ok = False
    if ppi_id and ip_id:
        try:
            pp, qq = fred(ppi_id), fred(ip_id)
            if len(pp) > 37 and len(qq) > 37:
                dp = 100.0 * (pp[-1][1] / pp[-37][1] - 1.0)
                dq = 100.0 * (qq[-1][1] / qq[-37][1] - 1.0)
                pq_note = f", 3년 가격 {dp:+.1f}% vs 물량 {dq:+.1f}%"
                if dp >= 5.0 and (dq <= 0.5 or dp / max(dq, 0.5) >= 3.0):
                    pq_ok = True
                    pq_note += " — 물량 대신 가격이 반응(비탄력의 정의)"
        except Exception:
            pass
    base += pq_note

    if a1 is None or p is None:
        return Signal(*K, sc, "unconfirmed", base,
                      "확증 실패: 생산능력·생산 지수 미지정 — 사양산업 여부를 가릴 수 없음",
                      ev, cur_u, evidence_label=lab)
    if p <= 0 and not pq_ok:
        return Signal(*K, sc, "unconfirmed", base,
                      f"확증 실패: 생산 YoY {p:+.1f}% — 수요 증가 증거 없음",
                      ev, cur_u, evidence_label=lab)
    return Signal(*K, sc, "ok", base, "", ev, cur_u, evidence_label=lab)


def _cagr(series, years: int) -> float | None:
    n = years * 12
    if len(series) < n + 1 or series[-n - 1][1] <= 0:
        return None
    return 100.0 * ((series[-1][1] / series[-n - 1][1]) ** (1.0 / years) - 1.0)


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
    # 표본이 작으면 확산이 아니라 잡음이다. 5개사가 6개사가 된 걸 '+20% 확산'으로
    # 읽으면 노이즈에 점수를 준다(방산 '탄약 생산' 4→5개사가 56점을 받던 문제).
    if nb < 8:
        return _nodata(*K, f"표본 부족 — 최근 12개월 언급 기업 {nb}개사(최소 8). "
                           f"확산을 논할 모수가 안 됨. 키워드를 더 일반적인 표현으로 바꿀 것")
    if cur["h"] + pre["h"] < 20:
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
    """고객의 설비가 늙었고, **교체가 실제로 시작됐는가**. 대상은 고객이다.

    백테스트 실측(IC −0.34)이 초판을 반박했다: '늙음 + 캐펙스 억제'만으로
    점수를 줬더니 고득점 그룹(제지·트럭 — 고객 설비 노후)의 이후 12개월
    수익률이 −2.2%p, 저득점 그룹은 +26.6%p 였다. 늙음은 교체 수요가 아니라
    정체 산업의 특징일 수 있다 — 교체는 미룰 수 있는 수요고, 오래 미뤘다고
    반드시 오는 게 아니다. 그래서 늙음은 '잠재력'으로만 두고, 고객 capex 가
    실제로 상승 전환(트리거)했을 때만 촉매로 친다.
    """
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
    potential = base * min(0.4 + years / 4.0, 1.0)
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
        return Signal(*K, potential * 0.25, "unconfirmed", detail,
                      "확증 실패: 고객 매출 추이 확인 불가")

    # 트리거: 고객 capex/감가상각의 상승 전환 또는 1.0 상향 돌파.
    # 이게 없으면 '늙음'은 켜진 촉매가 아니라 잠재력이다 — 강하게 깎는다.
    if len(ratios) >= 5:
        recent = [v for _, v in ratios[-5:]]
        crossed = recent[-1] >= 1.0 and min(recent[:-1]) < 1.0
        rising = recent[-1] > recent[0] + 0.05
        if crossed:
            return Signal(*K, min(100.0, potential * 1.15), "ok",
                          detail + f", 고객 capex/감가상각 {recent[-1]:.2f} — "
                                   "1.0 상향 돌파, 교체 시작됨")
        if rising:
            return Signal(*K, potential, "unconfirmed",
                          detail + f", capex/감가상각 {recent[0]:.2f}→{recent[-1]:.2f} 상승 중",
                          "1.0 미달이나 상승 전환 — 교체 개시 초기일 수 있음")
    return Signal(*K, potential * 0.25, "unconfirmed", detail,
                  "교체 개시 증거 없음(고객 capex 정체) — 늙음만으로는 촉매가 "
                  "아니다(백테스트: 이 상태의 고득점은 이후 수익률이 낮았다)")


# ---------------------------------------------------------------- ⑤ 정책

def a5_budget(theme: dict, group: dict) -> Signal | None:
    """예산이 실제로 집행되고 있는가 — 연방 계약 의무액.

    Federal Register 는 '규제가 온다'를 말하고, 계약 데이터는 '돈이 실제로
    움직였다'를 말한다. 방산처럼 규제가 아니라 예산이 수요를 만드는 테마에서는
    이쪽이 주장이고 규제 검색은 애초에 맞지 않는 도구다.

    설정이 없으면 None 을 돌려준다(호출부가 Federal Register 로 넘어간다).
    """
    cfg = theme.get("usaspending") or {}
    agency = cfg.get("agency")
    if not agency:
        return None

    K = ("A5", "⑤ 정책·예산(연방 계약)")
    from .usaspending import UsaError, contract_obligations
    from .usaspending import ttm as usa_ttm
    try:
        q = contract_obligations(agency, naics=cfg.get("naics"), psc=cfg.get("psc"))
    except UsaError as e:
        return _nodata(*K, f"계약 데이터 조회 실패: {e}")

    t = usa_ttm(q)
    g = yoy(t, 4)
    if len(g) < 8:
        return _nodata(*K, "TTM 이력 부족")

    cur = g[-1][1]
    rank = pct_rank(t[-1][1], [v for _, v in t])
    tr = slope(g, 4)
    detail = (f"{agency} 계약 TTM {t[-1][1] / 1e9:,.0f}십억$ "
              f"(자체 이력 {rank:.0f}분위), YoY {cur:+.1f}%")
    if tr is not None:
        detail += f", 증가율 추세 {tr:+.1f}%p/분기"
    ev = "https://www.usaspending.gov/search"

    # 기각: 계약이 줄고 있으면 '예산 확정 다년 계약' 논지가 성립하지 않는다
    if cur < -5:
        return _reject(*K, f"계약 감소 — TTM 의무액 YoY {cur:+.1f}%. "
                           "예산이 밀어주는 중이라는 근거가 없다", detail)

    sc = mean_of([scale(cur, -5, 25), rank])

    # 확증: 계약 증가가 아직 그룹 매출로 안 넘어왔으면 그게 기회다
    rev = (group.get("rev_yoy_series") or [])
    if rev:
        rg = rev[-1][1]
        detail += f", 그룹 매출 YoY {rg:+.1f}%"
        if cur - rg > 5:
            return Signal(*K, sc, "ok",
                          detail + " — 계약이 매출보다 앞서 있다(미전이 여지)",
                          "", ev, cur)
        if rg - cur > 10:
            return Signal(*K, sc * 0.6, "unconfirmed", detail,
                          "이미 반영 — 매출이 계약 증가율을 앞질렀다", ev, cur)
    return Signal(*K, sc, "ok", detail, "", ev, cur)


def mean_of(xs) -> float:
    vals = [x for x in xs if x is not None]
    return sum(vals) / len(vals) if vals else 0.0


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
    # 이미 비율로 나오는 지표가 있는 산업도 있다(주택 MSACSR = 재고 개월수).
    # 그럴 땐 나눗셈 없이 그대로 쓴다. 이건 테마가 명시적으로 고른 것이지,
    # 예전처럼 미지정 시 전 제조업 총계로 몰래 폴백하는 것과 다르다.
    ratio_id = cfg.get("inventory_ratio")
    if ratio_id:
        try:
            ratio = fred(ratio_id)
        except Exception as e:
            return _nodata(*K, f"재고율 조회 실패: {e}")
        inv_id = sh_id = ratio_id
    elif inv_id and sh_id:
        try:
            ratio = _ratio(fred(inv_id), fred(sh_id))
        except Exception as e:
            return _nodata(*K, f"재고/출하 조회 실패: {e}")
    else:
        return _nodata(*K, "산업별 재고·출하 시리즈 미지정 — 전 제조업 총계 폴백은 "
                           "모든 테마에 같은 점수를 주므로 사용하지 않는다")
    if len(ratio) < 36:
        return _nodata(*K, "재고/출하 이력 부족")

    cur = ratio[-1][1]
    yr = date.today().year
    rank = pct_rank(cur, [v for d, v in ratio if d.year >= yr - 10])
    if rank is None:
        return _nodata(*K, "재고율 이력 부족")
    # 10년 창은 2020~22 재고 급증을 품고 있어 현재를 과도하게 낮게 보이게 한다.
    # 전기장비는 10년 기준 0분위지만 전체 이력으로는 중앙값(47분위)이다.
    # 그래서 긴 창을 함께 보고, 동의할 때만 확증으로 인정한다.
    rank_all = pct_rank(cur, [v for _, v in ratio])
    sc = 100.0 - rank
    detail = (f"재고/출하 {cur:.2f}개월분 (10년 {rank:.0f}분위"
              + (f", 전체 이력 {rank_all:.0f}분위)" if rank_all is not None else ")"))

    # 확증 ①: 수요가 살아 있어야 '재입고 여지'다. 내구재는 신규수주, 비내구재는
    # 신규수주 자체가 조사되지 않으므로 출하로 대신한다.
    dg, dlab = _demand_yoy(cfg, fred)
    if dg is None:
        return Signal(*K, sc, "unconfirmed", detail, "확증 실패: 수요 지표 조회 실패")

    detail += f", {dlab} YoY {dg:+.1f}%"
    if dg <= 0:
        return _reject(*K, f"수요 붕괴 — 재고는 낮지만 {dlab}가 {dg:+.1f}%. "
                           "재입고 여지가 아니라 주문 자체가 줄어 재고가 마른 것", detail)

    # 근거 링크는 '비율'을 보여줘야 한다. 재고 금액만 걸면 오해를 부른다 —
    # 재고 금액은 물가와 성장 때문에 늘 최고치 근처인데, 비율은 낮을 수 있다.
    # FRED 에 산업별 비율 시리즈가 없으므로 두 원계열을 함께 띄운다.
    ev = _fred_pair(inv_id, sh_id)
    lab = "재고·출하 원계열↗ (비율은 두 계열의 나눗셈)"

    # 확증 ②: 긴 창도 낮다고 말해야 진짜 재고 고갈이다
    if rank_all is not None and rank_all >= 50:
        return Signal(*K, sc * 0.5, "unconfirmed", detail,
                      f"코로나 왜곡 의심 — 10년 창으로는 {rank:.0f}분위지만 전체 이력으로는 "
                      f"{rank_all:.0f}분위(중앙값 수준). 2020~22 재고 급증이 기준 분포를 "
                      "부풀려 현재가 낮아 보이는 것일 수 있다",
                      ev, cur, evidence_label=lab)
    return Signal(*K, sc, "ok", detail, "", ev, cur, evidence_label=lab)


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
    ev = _fred_pair(bl, sh)
    lab = "수주잔고·출하 원계열↗ (배수는 두 계열의 나눗셈)"
    if ng > 1.0:
        return Signal(*K, rank, "ok", detail + " — 수요 초과형 병목", "", ev, cur, evidence_label=lab)
    return Signal(*K, rank * 0.5, "unconfirmed", detail,
                  "생산 차질형 — 신규수주는 늘지 않는데 잔고만 쌓이는 중. "
                  "공급망이 풀리면 해소된다", ev, cur, evidence_label=lab)


# ---------------------------------------------------------------- ⑩ 대체

M3_UNIT = 1e6   # M3 국내 출하는 '백만 달러', Census 수입은 '달러'


def _penetration(imp: list, dom: list) -> list:
    """월별 수입침투율(%) = 수입 / (국내출하 + 수입). 같은 달끼리만 짝짓는다.

    단위를 맞추지 않으면 분모에서 국내 출하가 사실상 사라져 침투율이 100%로
    붙는다(실측: 철강·반도체·화학·전력기기 전부 100.0%).
    """
    dm = {(d.year, d.month): v * M3_UNIT for d, v in dom}
    out: list[tuple[date, float]] = []
    for d, v in imp:
        base = dm.get((d.year, d.month))
        if base and (base + v) > 0:
            out.append((d, 100.0 * v / (base + v)))
    return out


def a10_substitution(cfg: dict, fred) -> Signal:
    """산업 전체가 안 커도 한쪽이 다른 쪽을 먹으면 그 안에서 승자가 난다.

    가장 측정 가능한 형태가 **수입 대 국내 생산**이다. 국내 생산자 관점이므로
    침투율이 **내려갈 때** 유리하다(리쇼어링·관세가 먹히는 중).
    """
    K = ("A10", "⑩ 대체(수입침투율)")
    naics = cfg.get("trade_naics")
    sh_id = cfg.get("shipments")
    if not naics:
        return _nodata(*K, "trade_naics 미지정 — themes.yaml 에 NAICS 를 적으면 "
                           "Census 수입통계로 국내 생산 대체 여부를 본다")
    if not sh_id:
        return _nodata(*K, "국내 출하 시리즈(shipments) 미지정 — 침투율의 분모가 없다")

    from .census import CensusError, trade_monthly
    try:
        imp = trade_monthly(naics, "imports")
    except CensusError as e:
        return _nodata(*K, f"수입 통계 조회 실패: {e}")
    try:
        dom = fred(sh_id)
    except Exception as e:
        return _nodata(*K, f"국내 출하 조회 실패: {e}")

    pen = _penetration(imp, dom)
    if len(pen) < 24:
        return _nodata(*K, f"공통 이력 부족({len(pen)}개월) — 수입과 출하의 단위·주기 확인 필요")

    cur = pen[-1][1]
    # 단위가 어긋나면 침투율이 100% 근처로 붙는다(분모 실종). 실측: M3 를 달러로
    # 안 맞춰 4개 테마 전부 100.0%가 나왔다. 그런 값으로 점수를 내느니 보류가 낫다.
    if cur > 95:
        return _nodata(*K, f"침투율 {cur:.1f}% — 비현실적 값, 수입·출하 단위 불일치 의심")
    rank = pct_rank(cur, [v for _, v in pen])
    tr = slope(pen, 12)          # 최근 1년 추세(%p/월)
    if rank is None or tr is None:
        return _nodata(*K, "침투율 분위·추세 계산 불가")

    detail = (f"수입침투율 {cur:.1f}% (자체 이력 {rank:.0f}분위), "
              f"최근 12개월 추세 {tr * 12:+.1f}%p/년")
    # 침투율이 내려갈수록 국내 생산자에 유리 → 점수는 반대 방향
    sc = scale(-tr * 12, -3.0, 3.0) or 0.0

    # 기각: 침투율이 내려가도 국내 출하까지 줄면 시장 자체가 쪼그라든 것이다
    dg = None
    try:
        dg = yoy(dom, freq_periods(dom))[-1][1]
    except Exception:
        pass
    if dg is not None:
        detail += f", 국내 출하 YoY {dg:+.1f}%"
        if tr < 0 and dg < -2:
            return _reject(*K, f"시장 축소 — 수입침투율은 내려가지만 국내 출하도 "
                               f"{dg:+.1f}%. 국내가 수입을 되찾은 게 아니라 "
                               "시장 자체가 줄어든 것", detail)
    else:
        return Signal(*K, sc, "unconfirmed", detail,
                      "확증 실패: 국내 출하 증감 확인 불가")

    if tr >= 0:
        return Signal(*K, sc, "unconfirmed", detail,
                      f"수입이 오히려 침투 중({tr * 12:+.1f}%p/년) — "
                      "국내 생산자에게는 역풍")
    return Signal(*K, sc, "ok", detail)
