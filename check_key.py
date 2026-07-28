"""BEA 키가 제대로 읽히고 실제로 통하는지 확인한다.

    python check_key.py
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from screener.keys import bea_key
from screener.net import fetch_json

BASE = "https://apps.bea.gov/api/data"


def main() -> int:
    k = bea_key()
    if not k:
        print("[실패] 키를 못 찾았습니다.")
        print("       bea_key.txt 에 키만 한 줄로 넣었는지 확인하세요.")
        print("       (영문·숫자·하이픈 20자 이상인 줄만 키로 인식합니다)")
        return 1
    print(f"[확인] 키를 읽었습니다: {k[:4]}…{k[-4:]} ({len(k)}자)")

    try:
        d = fetch_json(f"{BASE}?&UserID={k}&method=GetParameterValues"
                       "&datasetname=InputOutput&ParameterName=TableID&ResultFormat=JSON",
                       ttl_hours=0.01)
    except Exception as e:
        print(f"[실패] BEA 호출 자체가 안 됩니다: {type(e).__name__}: {e}")
        return 2

    res = d.get("BEAAPI", {}).get("Results", {})
    if "Error" in res:
        err = res["Error"]
        print(f"[실패] BEA 가 키를 거부했습니다: {err.get('APIErrorDescription', err)}")
        return 3

    vals = res.get("ParamValue", []) or []
    print(f"[성공] 산업연관표 {len(vals)}종에 접근 가능합니다.\n")

    # '누가 이 산업의 산출물을 사는가' = Use 표. 요약(Summary) 수준을 쓴다.
    hits = [v for v in vals
            if "use" in str(v.get("Description", "")).lower()
            and "summary" in str(v.get("Description", "")).lower()]
    print("고객군 추정에 쓸 후보 표:")
    for v in hits[:12]:
        print(f"   TableID {v.get('Key'):>4}  {v.get('Description', '')[:95]}")
    if not hits:
        print("   (Use/Summary 표를 못 찾음 — 전체 목록 앞 10개)")
        for v in vals[:10]:
            print(f"   TableID {v.get('Key'):>4}  {v.get('Description', '')[:95]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
