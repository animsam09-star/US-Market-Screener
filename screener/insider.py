"""내부자 장내 매수 — SEC Form 4.

왜: 임원·이사가 **자기 돈으로 장내에서 사는 것**(거래 코드 P)은 주가보다 먼저
나타나는 대표적 신호다. 매도(S)는 세금·분산 등 이유가 많아 신호가 약하고,
스톡옵션 행사(M)·보상 지급(A)은 의사결정이 아니라 제외한다.

두 경로:
  - 운영(매일): 회사별 submissions 목록에서 최근 Form 4 를 골라 원문 XML 을
    읽는다. Form 4 는 한 번 올라오면 바뀌지 않으므로 1년 캐시. 한 번 실행에
    새로 읽는 문서 수에 상한을 둬 러너 시간 제한(8분)을 넘지 않게 한다 —
    못 읽은 것은 다음 실행이 이어서 읽는다.
  - 과거(백테스트): SEC 분기 일괄 자료(Insider Transactions Data Sets,
    분기당 약 10MB)에서 우리 종목 것만 골라 data/insider_hist.json 에 저장.

    python -m screener.insider --history 2009q4      # 과거 자료 구축
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from .net import CACHE_DIR, FetchError, cache_path, fetch_json, fetch_text

ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "data" / "insider_hist.json"

WINDOW_DAYS = 90         # 이 기간 안의 매수를 묶어 본다
MIN_VALUE = 25_000       # 한 사람의 합계가 이보다 작으면 상징적 매수로 보고 뺀다
LIVE_LOOKBACK = 120      # 운영: 이 기간 안 Form 4 만 읽는다(창 90일 + 여유)
FETCH_BUDGET = 350       # 운영: 한 번 실행에 새로 받는 Form 4 원문 상한


# ================================================================ 원문 해석

def _vals(x: str, tag: str) -> list[str]:
    return [v.strip() for v in
            re.findall(r"<" + tag + r">\s*(?:<value>)?\s*([^<]*)", x)]


def _truthy(v: str) -> bool:
    return v.strip().lower() in ("1", "true")


def parse_form4(xml: str) -> list[dict]:
    """Form 4 XML → 장내 매수 목록 [{owner, role, shares, price, value, tdate}].

    nonDerivativeTransaction 블록마다 코드·수량·가격을 짝지어 읽는다(전역
    정규식으로 따로 모으면 블록이 여러 개일 때 짝이 어긋난다).
    """
    owner = (_vals(xml, "rptOwnerName") or [""])[0]
    is_dir = any(_truthy(v) for v in _vals(xml, "isDirector"))
    is_off = any(_truthy(v) for v in _vals(xml, "isOfficer"))
    title = (_vals(xml, "officerTitle") or [""])[0]
    if not (is_dir or is_off):
        return []      # 10% 대주주(펀드)만인 경우 — 회사 내부 정보 신호가 아니다
    role = title or ("이사" if is_dir else "임원")
    out = []
    for blk in re.findall(r"<nonDerivativeTransaction>(.*?)</nonDerivativeTransaction>",
                          xml, flags=re.S):
        code = (_vals(blk, "transactionCode") or [""])[0]
        ad = (_vals(blk, "transactionAcquiredDisposedCode") or [""])[0]
        if code != "P" or ad != "A":
            continue
        try:
            sh = float((_vals(blk, "transactionShares") or ["0"])[0] or 0)
            pr = float((_vals(blk, "transactionPricePerShare") or ["0"])[0] or 0)
        except ValueError:
            continue
        td = (_vals(blk, "transactionDate") or [""])[0][:10]
        out.append({"owner": owner, "role": role, "shares": sh, "price": pr,
                    "value": sh * pr, "tdate": td})
    return out


# ================================================================ 운영 경로

class _Budget:
    def __init__(self, n: int):
        self.left = n
        self.skipped = 0


RUN_BUDGET = _Budget(FETCH_BUDGET)   # 프로세스(=실행 1회) 단위


def live_buys(ticker: str, cik: int, today: date | None = None,
              budget: _Budget | None = None) -> list[dict]:
    """최근 LIVE_LOOKBACK 일 장내 매수. 예산을 넘는 문서는 건너뛰고 센다."""
    today = today or date.today()
    try:
        sub = fetch_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
                         ttl_hours=24)
    except FetchError:
        return []
    rec = (sub.get("filings") or {}).get("recent") or {}
    forms = rec.get("form") or []
    cutoff = (today - timedelta(days=LIVE_LOOKBACK)).isoformat()
    out = []
    for i, f in enumerate(forms):
        if f != "4":
            continue
        fd = rec["filingDate"][i]
        if fd < cutoff:
            continue
        acc = rec["accessionNumber"][i].replace("-", "")
        doc = rec["primaryDocument"][i].split("/")[-1]
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
        if budget is not None and not cache_path(url).exists():
            if budget.left <= 0:
                budget.skipped += 1
                continue
            budget.left -= 1
        try:
            xml = fetch_text(url, ttl_hours=24 * 365)
        except FetchError:
            continue
        for b in parse_form4(xml):
            b.update({"date": fd, "ticker": ticker})
            out.append(b)
    return out


# ================================================================ 과거 자료

def _qlist(start: str, end: date) -> list[str]:
    y, q = int(start[:4]), int(start[5])
    out = []
    while (y, q) <= (end.year, (end.month - 1) // 3 + 1):
        out.append(f"{y}q{q}")
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)
    return out


def _d(s: str) -> str | None:
    try:
        return datetime.strptime(s.strip(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def _tsv(z: zipfile.ZipFile, name: str):
    with z.open(name) as f:
        rd = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"),
                            delimiter="\t", quoting=csv.QUOTE_NONE)
        yield from rd


def _download(q: str) -> bytes | None:
    import urllib.request
    p = CACHE_DIR / "insider_ds" / f"{q}.zip"
    if p.exists() and p.stat().st_size > 1000:
        return p.read_bytes()
    from .net import HEADERS
    url = ("https://www.sec.gov/files/structureddata/data/"
           f"insider-transactions-data-sets/{q}_form345.zip")
    try:
        b = urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS),
                                   timeout=180).read()
    except Exception as e:
        print(f"  {q}: 받기 실패 {type(e).__name__}: {e}")
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b)
    return b


def build_history(start_q: str, ciks: dict[int, str]) -> list[dict]:
    """분기 일괄 자료 → 우리 종목의 장내 매수(임원·이사)만."""
    rows: list[dict] = []
    for q in _qlist(start_q, date.today()):
        b = _download(q)
        if not b:
            continue
        z = zipfile.ZipFile(io.BytesIO(b))
        sub = {}
        for r in _tsv(z, "SUBMISSION.tsv"):
            if r.get("DOCUMENT_TYPE", "").strip() not in ("4", "4/A"):
                continue
            try:
                cik = int(r["ISSUERCIK"])
            except (TypeError, ValueError):
                continue
            if cik in ciks:
                sub[r["ACCESSION_NUMBER"]] = (cik, _d(r["FILING_DATE"]))
        own: dict[str, tuple] = {}
        for r in _tsv(z, "REPORTINGOWNER.tsv"):
            acc = r["ACCESSION_NUMBER"]
            if acc not in sub:
                continue
            rel = r.get("RPTOWNER_RELATIONSHIP", "") or ""
            if "Director" not in rel and "Officer" not in rel:
                continue
            own[acc] = (r.get("RPTOWNERNAME", "").strip(),
                        (r.get("RPTOWNER_TITLE") or "").strip()
                        or ("이사" if "Director" in rel else "임원"))
        n = 0
        for r in _tsv(z, "NONDERIV_TRANS.tsv"):
            acc = r["ACCESSION_NUMBER"]
            if acc not in own or r.get("TRANS_CODE") != "P" \
                    or r.get("TRANS_ACQUIRED_DISP_CD") != "A":
                continue
            try:
                sh = float(r.get("TRANS_SHARES") or 0)
                pr = float(r.get("TRANS_PRICEPERSHARE") or 0)
            except ValueError:
                continue
            cik, fd = sub[acc]
            if not fd:
                continue
            rows.append({"date": fd, "ticker": ciks[cik], "owner": own[acc][0],
                         "role": own[acc][1], "shares": sh, "price": pr,
                         "value": round(sh * pr, 2), "tdate": _d(r.get("TRANS_DATE", "")) or ""})
            n += 1
        print(f"  {q}: 매수 {n}건", flush=True)
    rows.sort(key=lambda r: (r["date"], r["ticker"]))
    return rows


def load_history() -> list[dict]:
    try:
        return json.loads(HIST.read_text(encoding="utf-8"))
    except Exception:
        return []


# ================================================================ 테마 묶음

def window(buys: list[dict], asof: date, days: int = WINDOW_DAYS) -> list[dict]:
    lo = (asof - timedelta(days=days)).isoformat()
    hi = asof.isoformat()
    return [b for b in buys if lo < b["date"] <= hi]


def summarize(buys: list[dict]) -> dict:
    """테마 안 장내 매수 요약 — 사람별 합계가 MIN_VALUE 이상인 것만 센다."""
    per: dict[tuple, float] = {}
    for b in buys:
        k = (b["ticker"], b["owner"])
        per[k] = per.get(k, 0.0) + float(b.get("value") or 0)
    keep = {k: v for k, v in per.items() if v >= MIN_VALUE}
    by_co: dict[str, int] = {}
    for (t, _o) in keep:
        by_co[t] = by_co.get(t, 0) + 1
    return {"companies": sorted(by_co), "per_company": by_co,
            "insiders": len(keep), "value": round(sum(keep.values())),
            "last": max((b["date"] for b in buys), default=None)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", default="2009q4", help="시작 분기(예: 2009q4)")
    args = ap.parse_args()
    import yaml

    from .sources import sec_ticker_map
    cfg = yaml.safe_load((ROOT / "themes.yaml").read_text(encoding="utf-8"))
    tmap = sec_ticker_map()
    ciks = {}
    for th in cfg["themes"]:
        for t in th["tickers"]:
            c = tmap.get(t.upper())
            if c:
                ciks[int(c)] = t.upper()
    print(f"종목 {len(ciks)}개 — 분기 자료 {args.history}부터", flush=True)
    rows = build_history(args.history, ciks)
    HIST.parent.mkdir(exist_ok=True)
    HIST.write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"저장: {HIST} ({len(rows)}건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
