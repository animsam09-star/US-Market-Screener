"""미국 섹터 스크리너 — 실행 진입점.  # build-marker: fred-snapshot

    python run.py                # 전체 테마 실행 후 대시보드 열기
    python run.py --no-open      # 브라우저 열지 않음
    python run.py --theme 정유   # 이름에 '정유'가 들어간 테마만
    python run.py --refresh      # 캐시 무시하고 새로 받기
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
import webbrowser
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml

from screener.dashboard import build_html
from screener.net import CACHE_DIR, TRUSTSTORE_OK
from screener.signals import evaluate_theme
from screener.sources import sec_ticker_map, yahoo_prices

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)



# Cloudflare Pages 앞단에서 비밀번호를 확인하는 코드.
# Cloudflare Access 는 본인 소유 도메인(zone)에만 걸 수 있어 *.pages.dev 는
# 보호하지 못한다. 대신 Pages 의 _worker.js(고급 모드)로 직접 막는다 —
# 도메인도 유료 플랜도 필요 없다.
# 비밀번호는 코드에 넣지 않고 Pages 환경변수(SCREENER_PASSWORD)에서 읽는다.
# 값이 없으면 통과시킨다(로컬 열람·설정 전 상태에서 막히지 않도록).
_WORKER_JS = """\
export default {
  async fetch(request, env) {
    const pw = env.SCREENER_PASSWORD;
    if (pw) {
      const got = request.headers.get("Authorization") || "";
      const want = "Basic " + btoa("screener:" + pw);
      let ok = got.length === want.length;
      for (let i = 0; i < want.length; i++) {
        if (got.charCodeAt(i) !== want.charCodeAt(i)) ok = false;
      }
      if (!ok) {
        return new Response("인증이 필요합니다.", {
          status: 401,
          headers: {
            "WWW-Authenticate": 'Basic realm="screener", charset="UTF-8"',
            "Content-Type": "text/plain; charset=utf-8",
          },
        });
      }
    }
    return env.ASSETS.fetch(request);
  },
};
"""


def _install_gate() -> None:
    (OUT / "_worker.js").write_text(_WORKER_JS, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "themes.yaml"))
    ap.add_argument("--theme", default=None, help="이름 부분일치로 테마 선택")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="디스크 캐시 삭제 후 실행")
    args = ap.parse_args()

    if not TRUSTSTORE_OK:
        print("[경고] truststore 미설치 — 사내 SSL 프록시 환경에서는 전부 실패합니다.")
        print("       python -m pip install truststore --trusted-host pypi.org "
              "--trusted-host files.pythonhosted.org")
        return 2

    if args.refresh and CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
        CACHE_DIR.mkdir(exist_ok=True)
        print("캐시 삭제됨")

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    themes = cfg.get("themes", [])
    if args.theme:
        themes = [t for t in themes if args.theme in t["name"]]
        if not themes:
            print(f"'{args.theme}' 에 맞는 테마 없음")
            return 1
    bench_tkr = cfg.get("benchmark", "SPY")

    t0 = time.time()
    print(f"티커→CIK 매핑 로드…", flush=True)
    tmap = sec_ticker_map()
    print(f"  {len(tmap):,}건")

    try:
        bench = yahoo_prices(bench_tkr)
    except Exception as e:
        print(f"[경고] 벤치마크 {bench_tkr} 실패 ({e}) — 상대수익률 축 비활성")
        bench = []

    series_cache: dict = {}
    results = []
    for i, th in enumerate(themes, 1):
        print(f"[{i}/{len(themes)}] {th['name']} …", end="", flush=True)
        try:
            r = evaluate_theme(th, tmap, bench, series_cache)
            results.append(r)
            cs = f"{r.catalyst_score:.0f}" if r.catalyst_score is not None else "—"
            us = f"{r.unpriced_score:.0f}" if r.unpriced_score is not None else "—"
            print(f" 촉매 {cs} / 미반영 {us} / 게이트 {r.gate_passed} "
                  f"/ 커버리지 {r.coverage:.0f}%")
        except Exception as e:
            print(f" 실패: {type(e).__name__}: {e}")

    if not results:
        print("결과 없음")
        return 1

    html = build_html(results, benchmark=bench_tkr)
    out = OUT / "screener.html"
    out.write_text(html, encoding="utf-8")
    # 배포 시 루트(/)로 열려야 한다. index.html 이 없으면 404 가 난다.
    (OUT / "index.html").write_text(html, encoding="utf-8")
    _install_gate()
    print(f"\n완료 ({time.time() - t0:.0f}초) → {out}")

    if not args.no_open:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
