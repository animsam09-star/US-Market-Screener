"""공통 HTTP 계층.

사내망 특성 두 가지를 여기서 흡수한다.
  1) SSL 검사 프록시가 인증서를 갈아끼운다 -> certifi 번들은 실패, Windows 저장소는 성공.
     truststore 로 OS 네이티브 검증을 파이썬에 주입한다.
  2) 외부 호출이 느리고 불안정하다 -> 모든 응답을 디스크에 캐시한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

try:
    import truststore

    truststore.inject_into_ssl()
    TRUSTSTORE_OK = True
except Exception:  # pragma: no cover - 설치 안 된 환경
    TRUSTSTORE_OK = False

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# SEC 는 연락처가 담긴 User-Agent 를 요구한다. 없으면 403.
# 미설정 시크릿은 환경변수를 '없음'이 아니라 '빈 문자열'로 만든다 —
# os.environ.get 의 기본값이 안 먹으므로 빈 값도 폴백으로 넘긴다.
UA = os.environ.get("SCREENER_UA", "").strip() or "DaolResearch RA animsam09@gmail.com"
HEADERS = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}

_last_call: dict[str, float] = {}
# 호스트별 최소 호출 간격(초). SEC 는 10 req/s 제한이 있다.
_MIN_INTERVAL = {"data.sec.gov": 0.12, "www.sec.gov": 0.12, "efts.sec.gov": 0.15}


class FetchError(RuntimeError):
    pass


class NotFound(FetchError):
    """리소스가 없다(404). 호스트 장애가 아니므로 차단 판정에 세지 않는다."""


def _throttle(host: str) -> None:
    gap = _MIN_INTERVAL.get(host, 0.0)
    if not gap:
        return
    prev = _last_call.get(host, 0.0)
    wait = gap - (time.time() - prev)
    if wait > 0:
        time.sleep(wait)
    _last_call[host] = time.time()


def cache_path(url: str, json_body: object | None = None) -> Path:
    """이 URL 의 캐시 파일 경로. 오류 응답을 걷어내야 할 때 쓴다."""
    return _cache_path(url, json_body)


def purge(url: str, json_body: object | None = None) -> bool:
    """캐시된 응답을 지운다.

    HTTP 200 에 오류를 담아 보내는 API 가 있다(BEA 가 그렇다). 그런 응답을
    캐시하면 원인이 해소된 뒤에도 계속 옛 오류를 읽는다.
    """
    p = _cache_path(url, json_body)
    if p.exists():
        p.unlink()
        return True
    return False


def _cache_path(url: str, body: object | None) -> Path:
    key = hashlib.sha256((url + json.dumps(body, sort_keys=True) if body else url).encode()).hexdigest()[:24]
    return CACHE_DIR / f"{key}.bin"


# 호스트별 연속 실패 횟수. 차단된 호스트에 계속 타임아웃을 먹으면
# 실행이 몇 시간짜리가 된다(URL 하나에 40초×3회 = 2분, 티커 85개면 몇 시간).
_fail_streak: dict[str, int] = {}
_DEAD_AFTER = 4          # 연속 4회 실패하면 그 호스트는 죽은 것으로 본다
_dead: set[str] = set()


def host_status() -> dict[str, str]:
    """어느 호스트가 죽었는지. 실행 끝에 요약하기 위함."""
    return {h: "차단됨" for h in sorted(_dead)}


def fetch(url: str, *, ttl_hours: float = 24.0, json_body: object | None = None,
          timeout: int = 20, retries: int = 2) -> bytes:
    """URL 을 가져온다. ttl_hours 안이면 디스크 캐시를 쓴다."""
    cp = _cache_path(url, json_body)
    if cp.exists() and (time.time() - cp.stat().st_mtime) < ttl_hours * 3600:
        return cp.read_bytes()

    host = url.split("/")[2]

    # 회로차단: 이미 죽은 호스트는 네트워크를 건드리지 않고 즉시 실패시킨다.
    # 캐시가 있으면 낡았더라도 그걸 쓴다.
    if host in _dead:
        if cp.exists():
            return cp.read_bytes()
        raise FetchError(f"{host} 접근 불가로 판정됨(연속 {_DEAD_AFTER}회 실패) — 호출 생략")

    last = None
    for attempt in range(retries):
        try:
            _throttle(host)
            if json_body is not None:
                r = requests.post(url, json=json_body,
                                  headers={**HEADERS, "Content-Type": "application/json"},
                                  timeout=timeout)
            else:
                r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 404:
                # 없는 리소스지 서버 장애가 아니다. 차단 판정에 세지 않는다 —
                # 존재하지 않는 시리즈를 몇 개 조회했다고 FRED 전체를 죽은 것으로
                # 판정하면 그 뒤 모든 조회가 막힌다(실제로 그랬다).
                raise NotFound(f"404 {url}")
            if r.status_code in (403, 451):
                # 정책 차단이지 일시 오류가 아니다. 재시도해도 안 열린다.
                # SEC 는 데이터센터 IP(클라우드 러너)에 403 을 내는 일이 있다.
                raise FetchError(f"{r.status_code} 접근 거부 {url} "
                                 f"(UA={UA[:40]!r}) — 재시도 생략")
            r.raise_for_status()
            cp.write_bytes(r.content)
            _fail_streak[host] = 0
            return r.content
        except NotFound as e:
            raise                      # 없는 리소스 — 재시도도 차단 판정도 무의미
        except FetchError as e:
            last = e
            break                      # 403 은 재시도해도 소용없다
        except Exception as e:         # 네트워크 흔들림은 재시도
            last = e
            time.sleep(1.0 * (attempt + 1))

    _fail_streak[host] = _fail_streak.get(host, 0) + 1
    if _fail_streak[host] >= _DEAD_AFTER and host not in _dead:
        _dead.add(host)
        print(f"[차단 판정] {host} — 연속 {_fail_streak[host]}회 실패. "
              f"이후 호출은 생략하고 캐시/폴백으로 진행합니다.")

    # 신선하진 않아도 캐시가 있으면 그걸 쓴다 (오프라인 저하 동작)
    if cp.exists():
        return cp.read_bytes()
    if isinstance(last, FetchError):
        raise last
    raise FetchError(f"{url} 실패: {type(last).__name__}: {last}")


def fetch_json(url: str, **kw) -> dict:
    raw = fetch(url, **kw)
    return json.loads(raw.decode("utf-8", "replace"))


def fetch_text(url: str, **kw) -> str:
    return fetch(url, **kw).decode("utf-8", "replace")
