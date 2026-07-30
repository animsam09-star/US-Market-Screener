"""러너 산출물 진단 — 실행 기록에 덧붙일 마크다운을 출력한다.

    python diagnose_output.py >> reports/run_status.md

왜 스크립트인가: 워크플로 안 인라인 python -c 는 YAML→bash→python 3중
이스케이프를 지나며 깨졌고(run 38 에서 배포 기록 스텝이 통째로 죽음),
로컬에서 검증할 방법도 없었다. 스크립트면 로컬에서 그대로 돌려볼 수 있다.

러너와 로컬의 계산이 다른 원인을 좁히는 게 목적이다:
run 37 실측 — 같은 커밋인데 러너 산출물에는 신형 공급축 표시가 0곳.
"""
from __future__ import annotations

import io
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")


def main() -> int:
    try:
        h = io.open("out/screener.html", encoding="utf-8").read()
    except OSError as e:
        print(f"- 진단: 산출물 없음 ({e})")
        return 0

    print(f"- 산출물 진단: 신형공급축 {h.count('10년 연')}곳 / "
          f"조회실패 {h.count('조회 실패')}곳 / "
          f"차단판정 {h.count('접근 불가로 판정')}곳 / "
          f"EIA키없음 {h.count('EIA 키 없음')}곳")

    for nm in ("전력기기", "정유"):
        i = h.find(nm)
        seg = h[i:i + 14000] if i >= 0 else ""
        m = re.search(r'② 공급 비탄력.{0,900}?(?:det">|why">)([^<]{0,160})', seg, re.S)
        print(f"- {nm} ② 실제: {m.group(1).strip() if m else '추출 실패'}")

    # FRED 가 이 환경에서 실시간으로 닿는지 — 캐시 우회(ttl 0)
    try:
        from screener.net import fetch
        b = fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=CAPG335S",
                  ttl_hours=0, timeout=20)
        lines = b.decode("utf-8", "replace").strip().split("\n")
        print(f"- FRED 실시간: OK ({len(lines) - 1}행, 머리={lines[0][:36]!r})")
    except Exception as e:
        print(f"- FRED 실시간: 실패 — {str(e)[:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
