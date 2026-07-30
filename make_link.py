"""대시보드를 링크로 발행할 수 있는 형태로 변환한다.

    python make_link.py

out/screener.html 은 완결된 문서(doctype·html·head·body)다. 링크 발행 시에는
바깥 골격이 자동으로 씌워지므로 그 태그들을 벗기고 style + 본문만 남긴다.

왜 스크립트로 두나: 매번 손으로 자르면 <style> 을 빼먹거나 </body> 를 남기는
실수가 난다. 실제 결과를 검증까지 해서 out/screener_link.html 로 낸다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "out" / "screener.html"
DEST = ROOT / "out" / "screener_link.html"


def convert(html: str) -> str:
    style = re.search(r"<style>(.*?)</style>", html, re.S)
    body = re.search(r"<body>(.*?)</body>", html, re.S)
    if not (style and body):
        raise SystemExit("style 또는 body 를 찾지 못했습니다 — 대시보드 구조가 바뀌었나요?")
    return f"<style>{style.group(1)}</style>\n{body.group(1).strip()}\n"


def main() -> int:
    if not SRC.exists():
        raise SystemExit(f"{SRC} 가 없습니다. 먼저 python run.py 를 실행하세요.")

    out = convert(SRC.read_text(encoding="utf-8"))
    DEST.write_text(out, encoding="utf-8")

    # 벗겨야 할 태그가 남았는지, 남겨야 할 것이 사라졌는지 확인한다
    low = out.lower()
    for bad in ("<!doctype", "<html", "</html>", "<head", "<body", "</body>"):
        if bad in low:
            raise SystemExit(f"발행 불가 — 바깥 골격 태그가 남아 있습니다: {bad}")
    for need in ("class=\"viz-root\"", "class=\"prio\"", "class=\"card\"", "--surface-1"):
        if need not in out:
            raise SystemExit(f"발행 불가 — 필수 요소가 빠졌습니다: {need}")

    print(f"변환 완료 → {DEST}  ({len(out) / 1024:.0f} KB)")
    print("  카드", out.count('class="card"'), "· 결론", out.count('class="verdict-line"'),
          "· 종목표", out.count('class="stocks"'))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
