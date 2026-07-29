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


def load_key(name: str, filename: str, *aliases: str) -> str | None:
    """환경변수 name(또는 별칭), 없으면 filename 에서 키를 읽는다.

    시크릿 이름은 사람이 붙인다. 내가 안내한 이름과 실제로 등록한 이름이
    다를 수 있으므로(_KEY 접미사 유무 등) 몇 가지 변형을 함께 본다.
    이름이 안 맞아 키를 못 찾는 건 조용한 실패 중에서도 가장 허무한 종류다.
    """
    cands = [name, *aliases]
    if name.endswith("_KEY"):
        cands.append(name[:-4])          # CENSUS_API_KEY -> CENSUS_API
    else:
        cands.append(name + "_KEY")
    for n in cands:
        env = os.environ.get(n, "").strip()
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
    return load_key("BEA_API_KEY", "bea_key.txt", "BEA_API")


def census_key() -> str | None:
    return load_key("CENSUS_API_KEY", "census_key.txt", "CENSUS_API", "CENSUS_KEY")


def data_gov_key() -> str | None:
    """api.data.gov 키 하나로 EPA CAMPD·Regulations.gov 등을 함께 쓴다."""
    return load_key("DATA_GOV_API_KEY", "data_gov_key.txt",
                    "DATA_GOV_API", "DATAGOV_API_KEY")
