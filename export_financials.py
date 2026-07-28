"""SEC 재무 스냅샷 생성 — 사내 PC에서 돌려 저장소에 넣는다.

    python export_financials.py

왜 필요한가: SEC 는 데이터센터 IP(GitHub Actions 러너)에 403 을 낸다. 그런데
SEC 재무는 **분기에 한 번** 바뀌는 데이터다. 매일 원격에서 받을 이유가 없다.
사내망 PC 에서 한 번 뽑아 data/financials.json 에 넣어두면, Actions 는 주가·거시만
매일 갱신하면 된다. 바뀌는 주기가 다른 데이터를 같은 주기로 받으려 한 게
애초에 잘못이었다.

분기 실적 발표 후(2·5·8·11월경) 한 번씩 다시 돌려 커밋하면 된다.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml

from screener.net import FetchError
from screener.sources import CONCEPTS, sec_company_facts, sec_ticker_map, xbrl_quarterly

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "data" / "financials.json"


def main() -> int:
    cfg = yaml.safe_load((ROOT / "themes.yaml").read_text(encoding="utf-8"))

    tickers: set[str] = set()
    for th in cfg.get("themes", []):
        tickers |= {t.upper() for t in th.get("tickers", [])}
        tickers |= {t.upper() for t in ((th.get("customers") or {}).get("tickers") or [])}
    print(f"대상 티커 {len(tickers)}개 (테마 종목 + 고객군)")

    tmap = sec_ticker_map()
    snap: dict[str, dict] = {}
    missing: list[str] = []

    for i, t in enumerate(sorted(tickers), 1):
        cik = tmap.get(t)
        if not cik:
            missing.append(t)
            continue
        try:
            facts = sec_company_facts(cik)
        except FetchError as e:
            missing.append(f"{t}({str(e)[:30]})")
            continue
        per = {}
        for c in CONCEPTS:
            q = xbrl_quarterly(facts, c)
            if q:
                # 키를 문자열로 (JSON 은 튜플 키를 못 쓴다)
                per[c] = {f"{y}Q{qq}": v for (y, qq), v in q.items()}
        snap[t] = per
        n = sum(len(v) for v in per.values())
        print(f"  [{i}/{len(tickers)}] {t:6s} 개념 {len(per):2d}종 · 값 {n:4d}개")

    DEST.parent.mkdir(exist_ok=True)
    DEST.write_text(json.dumps(
        {"generated": date.today().isoformat(), "companies": snap},
        separators=(",", ":"), sort_keys=True), encoding="utf-8")

    size = DEST.stat().st_size
    print(f"\n저장: {DEST} ({size / 1024:.0f} KB, {len(snap)}개사)")
    if missing:
        print(f"미확보: {', '.join(missing)}")
    print("\n이 파일을 커밋하면 GitHub Actions 가 SEC 없이도 재무 축을 계산합니다.")
    print("분기 실적 발표 후(2·5·8·11월경) 다시 돌려 갱신하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
