"""주가 스냅샷 반출 — 러너에서 Yahoo·Stooq 가 동시에 막히는 날의 폴백.

    python export_prices.py     # data/price_snapshot.json.gz 생성 후 커밋

실측: 러너에서 하루 Yahoo(클라우드 IP 차단)+Stooq 동시 실패로 한 테마의
주가 축(U3~U5)이 통째로 죽은 날이 있었다(다음 날 자연 복구). FRED 스냅샷과
같은 원리 — 몇 주 낡은 주가라도 12개월 상대수익률·고점 경과 축은 대체로
유효하며, 폴백 사용 사실은 대시보드 경고에 표시된다. 월 1회 갱신 권장.
"""
from __future__ import annotations

import gzip
import json
import sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml

from screener.sources import yahoo_prices

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "price_snapshot.json.gz"


def main() -> int:
    cfg = yaml.safe_load((ROOT / "themes.yaml").read_text(encoding="utf-8"))
    tickers = sorted({t.upper() for th in cfg.get("themes", [])
                      for t in th["tickers"]}
                     | {t.upper() for th in cfg.get("themes", [])
                        for t in (th.get("customers", {}) or {}).get("tickers", [])}
                     | {cfg.get("benchmark", "SPY")})
    prices: dict[str, list] = {}
    fail = []
    for t in tickers:
        try:
            prices[t] = [[d.isoformat(), round(v, 4)]
                         for d, v in yahoo_prices(t)]
        except Exception as e:
            fail.append(t)
            print(f"  [실패] {t}: {e}")
    payload = {"generated": date.today().isoformat(), "prices": prices}
    OUT.parent.mkdir(exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    with gzip.open(OUT, "wb") as f:
        f.write(raw)
    kb = OUT.stat().st_size // 1024
    print(f"저장: {OUT} ({kb} KB, {len(prices)}종목"
          + (f", 실패 {len(fail)}: {', '.join(fail)}" if fail else "") + ")")
    print("커밋하면 러너가 주가 조회 전멸 시 이 스냅샷으로 폴백합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
