"""FRED 스냅샷 생성 — 사내 PC에서 돌려 저장소에 동봉한다.

    python export_fred.py

왜 필요한가: GitHub 러너는 캐시가 안 쌓여 매 실행 100여 시리즈를 버스트로
받다가 FRED 에 일시 차단당한다(run 39~43 실측: 조회실패 67곳, 재시도 정책도
소용없음). FRED 는 월간 데이터라 며칠 낡아도 신호가 안 바뀐다 — SEC 재무
스냅샷과 같은 논리다. 러너는 실시간을 먼저 시도하고, 실패하면 이걸 쓴다.

themes.yaml 에 등장하는 모든 FRED 시리즈를 수집한다. 월 1회 갱신이면 충분하다.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml

from screener.net import FetchError
from screener.sources import fred_series

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "data" / "fred_snapshot.json"


def collect_ids() -> list[str]:
    cfg = yaml.safe_load((ROOT / "themes.yaml").read_text(encoding="utf-8"))
    ids: set[str] = set()
    for th in cfg.get("themes", []):
        for k, v in (th.get("fred") or {}).items():
            if k == "trade_naics":       # NAICS 코드지 FRED 시리즈가 아니다
                continue
            v = str(v)
            if v and not v.lower().startswith("eia:"):
                ids.add(v.split(":", 1)[-1] if ":" in v else v)
        cs = (th.get("customers") or {}).get("series")
        if cs and not str(cs).lower().startswith("eia:"):
            ids.add(str(cs))
    return sorted(ids)


def main() -> int:
    ids = collect_ids()
    print(f"수집 대상 {len(ids)}개 시리즈")
    snap: dict[str, list] = {}
    fail: list[str] = []
    for i, sid in enumerate(ids, 1):
        try:
            s = fred_series(sid)
            snap[sid] = [[d.isoformat(), v] for d, v in s]
            print(f"  [{i}/{len(ids)}] {sid:16s} {len(s):5d}행 ~{s[-1][0]}")
        except FetchError as e:
            fail.append(sid)
            print(f"  [{i}/{len(ids)}] {sid:16s} 실패: {str(e)[:50]}")

    DEST.parent.mkdir(exist_ok=True)
    DEST.write_text(json.dumps(
        {"generated": date.today().isoformat(), "series": snap},
        separators=(",", ":")), encoding="utf-8")
    print(f"\n저장: {DEST} ({DEST.stat().st_size / 1024:.0f} KB, {len(snap)}개)")
    if fail:
        print(f"실패: {', '.join(fail)}")
    print("커밋하면 러너가 FRED 차단 시 이 스냅샷으로 폴백합니다. 월 1회 갱신 권장.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
