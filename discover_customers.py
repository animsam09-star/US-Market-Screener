"""고객군 자동 지정 — BEA 산업연관표로 '누가 이 테마의 산출물을 사는가'를 찾는다.

    python discover_customers.py            # 리포트만 생성
    python discover_customers.py --apply    # themes.yaml 의 customers 도 갱신

이 스크립트는 GitHub Actions 에서 BEA_API_KEY 시크릿으로 돌린다. 결과를
out/customers_report.md 에 남기고 저장소에 커밋해, 다음 수정의 근거로 삼는다.

설계 메모: 고객군을 왜 자동으로 찾아야 하나 — ①낙수와 ④교체주기는 테마 자신이
아니라 테마의 '고객'을 재야 하는 축이다. 전력기기가 오르는 이유는 전력기기
산업생산이 아니라 유틸리티의 변압기가 늙어서다. 그 고객이 누구인지를 손으로
찍으면 편향이 들어가므로, 산업연관표의 금액 비중으로 정한다.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml

from screener import bea
from screener.keys import bea_key

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

# BEA 산업코드 -> 그 산업의 실질 활동을 나타내는 FRED 시리즈.
# ①낙수 축은 '명목 금액'이 아니라 '실질 물량'을 봐야 한다 — 물가 상승을 성장으로
# 오독하지 않기 위해서다. 그래서 산업생산 지수를 쓴다.
BEA_TO_FRED = {
    "221": "IPUTIL", "22": "IPUTIL",
    "324": "IPG324S", "325": "IPG325S", "326": "IPG326S",
    "331": "IPG331S", "332": "IPG332S", "333": "IPG333S",
    "334": "IPG334S", "3344": "IPG3344S", "3341": "IPG3341S",
    "335": "IPG335S", "336": "IPG336S", "3361MV": "IPG3361T3S",
    "3364OT": "IPG3364T9S", "3364": "IPG3364T9S",
    "211": "IPMINE", "212": "IPMINE", "213": "IPMINE",
    "23": "IPCONGD", "42": "IPBUSEQ",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="themes.yaml 의 customers 갱신")
    ap.add_argument("--year", default=str(date.today().year - 2),
                    help="산업연관표 연도 (기본: 재작년 — BEA 공표가 2년 지연)")
    args = ap.parse_args()

    lines: list[str] = ["# 고객군 자동 지정 리포트", ""]
    lines.append(f"생성: {date.today().isoformat()} · 대상 연도: {args.year}")
    lines.append("")

    if not bea_key():
        lines.append("## 실패: BEA 키 없음")
        lines.append("")
        lines.append("환경변수 `BEA_API_KEY` 또는 `bea_key.txt` 가 필요하다. "
                     "GitHub Actions 에서는 저장소 시크릿으로 주입된다.")
        _write(lines)
        print("[실패] BEA 키 없음 — 리포트만 기록")
        return 1

    # --- 1) 표 목록. 하드코딩하지 않고 런타임에 고른다
    try:
        tables = bea.list_tables()
    except bea.BeaError as e:
        lines += ["## 실패: 표 목록 조회", "", f"```\n{e}\n```"]
        _write(lines)
        print(f"[실패] {e}")
        return 2

    lines += ["## 1. 사용 가능한 산업연관표", "", "<details><summary>전체 목록</summary>", ""]
    for t in tables:
        lines.append(f"- `{t.get('Key')}` {str(t.get('Desc') or t.get('Description'))[:110]}")
    lines += ["", "</details>", ""]

    try:
        tid, tdesc = bea.pick_use_table(tables)
    except bea.BeaError as e:
        lines += ["## 실패: Use 표 선택", "", f"```\n{e}\n```"]
        _write(lines)
        print(f"[실패] {e}")
        return 3
    lines += [f"선택한 표: **TableID {tid}** — {tdesc}", ""]
    print(f"[표] TableID {tid}: {tdesc}")

    # --- 2) 데이터. 연도가 없으면 몇 해 뒤로 물러나며 시도
    data, used_year, err = None, None, None
    for back in range(0, 5):
        y = str(int(args.year) - back)
        try:
            data = bea.fetch_use_table(tid, y)
            used_year = y
            break
        except bea.BeaError as e:
            err = e
    if data is None:
        lines += ["## 실패: 데이터 조회", "", f"```\n{err}\n```"]
        _write(lines)
        print(f"[실패] {err}")
        return 4
    lines += [f"데이터: {used_year}년, {len(data):,}행", ""]
    print(f"[데이터] {used_year}년 {len(data):,}행")

    codes = bea.available_row_codes(data)
    lines += ["## 2. 행 코드(공급 산업) 목록", "",
              "<details><summary>전체</summary>", ""]
    for c, n in codes:
        lines.append(f"- `{c}` {n[:90]}")
    lines += ["", "</details>", ""]

    # --- 3) 테마별 고객 추출
    cfg_path = ROOT / "themes.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    lines += ["## 3. 테마별 고객 산업", ""]

    updates: dict[str, dict] = {}
    for th in cfg.get("themes", []):
        name = th["name"]
        fred_cfg = th.get("fred", {}) or {}
        src = (fred_cfg.get("industrial_production") or fred_cfg.get("capacity_index")
               or fred_cfg.get("capacity_utilization") or "")
        naics = bea.naics_from_fred(src)
        lines += [f"### {name}", ""]
        if not naics:
            lines += [f"- 산업 식별 실패: FRED 시리즈 `{src}` 에서 NAICS 를 못 뽑음", ""]
            continue

        hit = bea.match_row_code(codes, naics)
        if not hit:
            lines += [f"- NAICS `{naics}` 에 맞는 BEA 행 코드 없음", ""]
            continue
        rc, rname = hit
        tops = bea.downstream_of(data, rc)
        if not tops:
            lines += [f"- 행 `{rc}` ({rname}) 의 고객 분포가 비어 있음", ""]
            continue

        lines += [f"공급 산업: `{rc}` {rname}  (NAICS {naics} ← `{src}`)", "",
                  "| 고객 산업 | 코드 | 비중 | FRED 지표 |", "|---|---|---|---|"]
        best_series = None
        for c, n, share in tops:
            fr = BEA_TO_FRED.get(c, "")
            if fr and not best_series:
                best_series = fr
            lines.append(f"| {n[:52]} | `{c}` | {share * 100:.1f}% | {fr or '—'} |")
        lines.append("")

        cur = (th.get("customers") or {}).get("series")
        if best_series:
            mark = "그대로" if cur == best_series else f"{cur or '없음'} → {best_series}"
            lines += [f"제안 `customers.series`: **{best_series}** ({mark})", ""]
            updates[name] = {"series": best_series,
                             "top": [(c, n, share) for c, n, share in tops[:3]]}
        else:
            lines += ["상위 고객 산업이 FRED 지표에 매핑되지 않음 — "
                      "`BEA_TO_FRED` 에 항목 추가 필요", ""]

    # --- 4) 한계 명시
    lines += ["## 4. 이 리포트가 못 하는 것", "",
              "- **고객 티커는 자동으로 못 정한다.** 산업연관표는 산업 단위이고 "
              "상장사 매핑이 없다. ④교체주기 축이 쓰는 `customers.tickers` 는 "
              "여전히 수동이다.",
              "- 비중은 미국 국내 산업 간 거래 기준이다. 수출 비중이 큰 테마는 "
              "실제 고객이 표에 안 잡힌다.",
              f"- 산업연관표는 공표가 늦다(현재 {used_year}년). 최근 구조 변화는 안 잡힌다.",
              ""]

    _write(lines)
    print(f"[완료] 테마 {len(updates)}개에 고객 지표 제안 → out/customers_report.md")

    if args.apply and updates:
        _apply(cfg_path, updates)
        print(f"[적용] themes.yaml 의 customers.series 갱신 {len(updates)}건")
    return 0


def _write(lines: list[str]) -> None:
    (OUT / "customers_report.md").write_text("\n".join(lines), encoding="utf-8")


def _apply(path: Path, updates: dict) -> None:
    """customers.series 만 갱신한다. 티커는 손대지 않는다(자동 판정 불가)."""
    text = path.read_text(encoding="utf-8")
    for name, up in updates.items():
        i = text.index(f"- name: {name}")
        j = text.find("\n  - name:", i)
        j = len(text) if j == -1 else j
        seg = text[i:j]
        if "series:" in seg:
            import re as _re
            seg = _re.sub(r"(\n      series: )\S+", rf"\g<1>{up['series']}", seg, count=1)
        else:
            # customers 블록 자체가 없으면 만들지 않는다 — 티커 없이는 ④축이 못 돈다
            continue
        text = text[:i] + seg + text[j:]
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
