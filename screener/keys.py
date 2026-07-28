"""API 키 로딩.

키는 코드에 박지 않는다. 찾는 순서는 환경변수 → 프로젝트 루트의 키 파일이다.
키 파일은 안내문이 섞여 있어도 되도록, '키처럼 생긴 줄'만 골라낸다.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 영문/숫자/하이픈으로만 이루어진 20자 이상 토큰 = 키
_KEY_RE = re.compile(r"^[A-Za-z0-9\-]{20,}$")


def load_key(name: str, filename: str) -> str | None:
    """환경변수 name, 없으면 filename 에서 키를 읽는다. 없으면 None."""
    env = os.environ.get(name, "").strip()
    if env:
        return env

    path = ROOT / filename
    if not path.exists():
        return None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _KEY_RE.match(line):
            return line
    return None


def bea_key() -> str | None:
    return load_key("BEA_API_KEY", "bea_key.txt")
