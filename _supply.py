import sys; sys.path.insert(0,".")
from screener.sources import fred_series
from screener.stats import pct_rank, yoy, freq_periods
from datetime import date

# 공급을 주장하는 테마들의 지표
T={
 "전력기기(335)": dict(cap="CAPG335S", util="CAPUTLG335S", ip="IPG335S", ppi="PCU335311335311"),
 "정유(324)":    dict(cap="CAPG324S", util="CAPUTLG324S", ip="IPG324S", ppi="WPU057303"),
 "비료(화학325)": dict(cap="CAPG325S", util="CAPUTLG325S", ip="IPG325S", ppi="PCU325311325311"),
 "유전(광업21)":  dict(cap=None,       util="CAPUTLG21S",  ip="IPN213111N", ppi=None),
 "제지(322)":    dict(cap="CAPG322S", util="CAPUTLG322S", ip="IPG322S", ppi="PCU322322"),
 "주택(목재321)": dict(cap="CAPG321S", util="CAPUTLG321S", ip="IPG321S", ppi=None),
 "철강(3311)":   dict(cap="CAPG3311A2S", util="CAPUTLG3311A2S", ip="IPG3311A2S", ppi="WPU1017"),
}
def cagr(s, years):
    n=years*12
    if len(s)<n+1: return None
    a,b=s[-n-1][1], s[-1][1]
    if a<=0: return None
    return 100*((b/a)**(1/years)-1)

print(f"{'테마':14s} {'능력10년':>8s} {'능력5년':>7s} {'능력1년':>7s} {'가동률':>6s} {'분위':>4s} | {'3년 P':>7s} {'3년 Q':>7s} {'P/Q':>5s}")
print("-"*86)
for nm,c in T.items():
    cap10=cap5=cap1=None
    if c["cap"]:
        s=fred_series(c["cap"])
        cap10,cap5=cagr(s,10),cagr(s,5)
        g=yoy(s,12); cap1=g[-1][1] if g else None
    u=fred_series(c["util"]); util=u[-1][1]
    rank=pct_rank(util,[v for d,v in u if d.year>=date.today().year-10])
    # 가격 대 물량: 최근 3년 누적 변화
    dp=dq=None
    if c["ppi"]:
        p=fred_series(c["ppi"])
        if len(p)>37: dp=100*(p[-1][1]/p[-37][1]-1)
    q=fred_series(c["ip"])
    if len(q)>37: dq=100*(q[-1][1]/q[-37][1]-1)
    ratio = (dp/dq) if (dp is not None and dq not in (None,0) and abs(dq)>0.5) else None
    f=lambda x,d=1: f"{x:+.{d}f}" if x is not None else "   —"
    r=f"{ratio:4.1f}" if ratio is not None else "  —"
    print(f"{nm:14s} {f(cap10):>8s} {f(cap5):>7s} {f(cap1):>7s} {util:5.1f}% {rank:3.0f} | {f(dp):>7s} {f(dq):>7s} {r:>5s}")
print()
print("읽는 법: 능력 CAGR(%/년)이 0 근처 + 가동률 분위 높음 + 3년 P(가격)≫Q(물량) = 비탄력 증거")
