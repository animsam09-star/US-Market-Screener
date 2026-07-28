"""신호 계산에 쓰는 통계 헬퍼.

원칙: 서로 다른 단위의 지표를 한 점수판에 올려야 하므로, 모든 신호는
'자기 자신의 과거 대비 몇 분위인가'(0~100)로 환산한다. 절대 수준이 아니라
정상 대비 이례성을 본다.
"""
from __future__ import annotations

from datetime import date


def pct_rank(value: float | None, history: list[float]) -> float | None:
    """value 가 history 안에서 몇 백분위인가 (0~100)."""
    if value is None:
        return None
    h = [x for x in history if x is not None]
    if len(h) < 8:
        return None
    below = sum(1 for x in h if x < value)
    ties = sum(1 for x in h if x == value)
    return 100.0 * (below + 0.5 * ties) / len(h)


def yoy(series: list[tuple[date, float]], periods: int) -> list[tuple[date, float]]:
    """전년동기 대비 증가율(%) 시계열."""
    out = []
    for i in range(periods, len(series)):
        prev = series[i - periods][1]
        if prev and prev != 0:
            out.append((series[i][0], 100.0 * (series[i][1] / prev - 1.0)))
    return out


def freq_periods(series: list[tuple[date, float]]) -> int:
    """월간이면 12, 분기면 4를 돌려준다."""
    if len(series) < 3:
        return 12
    gaps = [(series[i][0] - series[i - 1][0]).days for i in range(1, min(len(series), 13))]
    med = sorted(gaps)[len(gaps) // 2]
    return 4 if med > 45 else 12


def last(series: list[tuple[date, float]]) -> float | None:
    return series[-1][1] if series else None


def slope(series: list[tuple[date, float]], n: int) -> float | None:
    """최근 n개 관측치의 단순 추세(기간당 변화량)."""
    pts = series[-n:]
    if len(pts) < 3:
        return None
    xs = list(range(len(pts)))
    ys = [p[1] for p in pts]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def ttm(quarterly: dict[tuple[int, int], float]) -> list[tuple[tuple[int, int], float]]:
    """분기 유량 -> 최근 4분기 합(TTM) 시계열. 4분기가 연속으로 있을 때만."""
    keys = sorted(quarterly)
    out = []
    for i in range(3, len(keys)):
        window = keys[i - 3:i + 1]
        # 연속성 확인: 분기가 정확히 4개 연달아 있어야 한다
        expected = []
        y, q = window[0]
        for _ in range(4):
            expected.append((y, q))
            q += 1
            if q == 5:
                q, y = 1, y + 1
        if window != expected:
            continue
        out.append((keys[i], sum(quarterly[k] for k in window)))
    return out


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def scale(value: float | None, lo: float, hi: float) -> float | None:
    """value 를 [lo, hi] 구간 기준으로 0~100 선형 환산."""
    if value is None:
        return None
    if hi == lo:
        return None
    return clamp(100.0 * (value - lo) / (hi - lo))


def mean(xs: list[float | None]) -> float | None:
    vals = [x for x in xs if x is not None]
    return sum(vals) / len(vals) if vals else None


def top_n_mean(xs: list[float | None], n: int = 2) -> float | None:
    """상위 n개의 평균.

    테마는 보통 1~2개 축으로 오른다. 9개를 단순평균하면 강한 신호가 무관한
    축들에 희석돼, 어느 축도 강하지 않은 '다면적으로 무난한' 테마가 상위로 온다.
    """
    vals = sorted((x for x in xs if x is not None), reverse=True)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0] * 0.7      # 단일 축만 살아있으면 신뢰도 할인
    return sum(vals[:n]) / min(n, len(vals))


def corr(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 8:
        return None
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return None
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / (va ** 0.5 * vb ** 0.5)


def best_lag(driver: list[float], follower: list[float],
             max_lag: int = 8) -> tuple[int, float] | None:
    """follower_t 를 가장 잘 설명하는 driver 의 선행 시차를 찾는다.

    driver 를 k기 뒤로 밀었을 때 상관이 최대인 k 를 돌려준다. k ≥ 1 이어야
    '선행'이고, 그래야 낙수 관계라고 부를 수 있다. 동행(k=0)은 같은 경기를
    같이 타는 것일 뿐 전이의 증거가 아니다.
    """
    best = None
    for k in range(0, max_lag + 1):
        if len(driver) - k < 8 or len(follower) < 8:
            continue
        d = driver[: len(driver) - k] if k else driver
        n = min(len(d), len(follower))
        c = corr(d[-n:], follower[-n:])
        if c is None:
            continue
        if best is None or c > best[1]:
            best = (k, c)
    return best
