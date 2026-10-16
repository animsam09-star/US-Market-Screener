// 종목 상세 창이 부르는 서버 중계 — /api/ohlcv · /api/fin · /api/news · /api/profile
//
// 미국 실적발표 정리(us-earnings-screening/worker.js)에서 이미 라이브로 검증된
// 함수를 그대로 옮겨 왔다(새로 짜지 않았다). 야후·네이버·구글 번역은 CORS
// 헤더를 주지 않아 브라우저가 직접 부르면 막히므로 여기서 대신 받아 준다.
// 키는 필요 없다. run.py 가 이 파일을 _worker.js 앞에 이어 붙인다 —
// 맨 아래 detailApi() 를 _worker.js 의 fetch 가 정적 파일보다 먼저 부른다.

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

/* ---- 주가 차트 데이터 ----
   야후 차트는 CORS 헤더를 주지 않아 브라우저에서 직접 못 부른다. 여기서
   대신 받아 정규화해 내려준다. 지표(120일선·일목 52일+26 선행)를 왼쪽 끝까지
   그리려면 화면에 보이는 3년보다 넉넉히 받아야 한다.
   야후의 v8 차트 엔드포인트는 crumb 없이도 열린다(실측). */
const YUA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";

/* ---- 뉴스 ----
   "지난 뉴스는 필요없다" — 그래서 두 가지를 지킨다.
   (1) 구글뉴스 검색에 when:7d 를 붙여 최근 7일치만 받는다. 안 붙이면
       관련도 순으로 와서 3주 전 기사가 맨 위에 올라온다(실측).
   (2) 받은 뒤 발행시각 내림차순으로 다시 정렬한다 — 소스 순서를 믿지 않는다.
   한국어(구글뉴스)와 영문 원문(야후)을 같이 받아 시각순으로 섞는다. */
const NEWS_DAYS = 7;
const NEWS_MAX = 20;

const unent = (x) =>
  String(x || "")
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/<[^>]*>/g, "")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&")
    .trim();

const tag = (block, name) => {
  // 정규식을 문자열로 짓기 때문에 역슬래시를 쓰면 안 된다 — "[\s\S]" 는 JS
  // 문자열 단계에서 [sS] 로 줄어들어 's' 와 'S' 만 찾는다(그래서 RSS 항목이
  // 통째로 버려졌다). [^] 는 줄바꿈 포함 아무 글자나 뜻하고 escape 가 없다.
  const m = block.match(new RegExp("<" + name + "[^>]*>([^]*?)</" + name + ">"));
  return m ? unent(m[1]) : "";
};

/* 종목 전용 RSS. 야후 search 는 시장 전반 기사가 섞여 애플을 열었는데
   알파벳·엔비디아 기사가 올라온다 — 이쪽이 그 종목 기사만 준다.
   (구글뉴스 RSS 는 한국어라 먼저 붙였는데 Worker 에서 503 이 온다.
    구글이 데이터센터 IP 를 막는다 — 실측. 그래서 영문을 받아 번역한다.) */
async function yahooRss(t) {
  const u = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=" +
    encodeURIComponent(t) + "&region=US&lang=en-US";
  const r = await fetch(u, { headers: { "User-Agent": YUA } });
  if (!r.ok) throw new Error("yahoo rss " + r.status);
  const xml = await r.text();
  const out = [];
  for (const m of xml.matchAll(/<item>([\s\S]*?)<\/item>/g)) {
    const b = m[1];
    const w = Date.parse(tag(b, "pubDate"));
    const title = tag(b, "title");
    if (!isFinite(w) || !title) continue;
    out.push({ t: title, u: tag(b, "link"), s: "", w });
  }
  return out;
}

/* 제목 한 줄 번역. 개요 탭과 같은 경로(구글 번역)를 쓴다 — 이쪽은 Worker 에서
   막히지 않는 것을 이미 확인했다. 실패하면 원문을 그대로 둔다. */
async function trKo(text) {
  try {
    const r = await fetch(
      "https://translate.googleapis.com/translate_a/single?client=gtx" +
        "&sl=en&tl=ko&dt=t&q=" + encodeURIComponent(text.slice(0, 400)),
      { headers: { "User-Agent": YUA } }
    );
    if (!r.ok) return null;
    const d = await r.json();
    if (!Array.isArray(d) || !Array.isArray(d[0])) return null;
    return d[0].map((x) => (x && x[0]) || "").join("").trim() || null;
  } catch (e) {
    return null;
  }
}

async function yahooNews(t) {
  const u = "https://query1.finance.yahoo.com/v1/finance/search?q=" +
    encodeURIComponent(t) + "&newsCount=12&quotesCount=0";
  const r = await fetch(u, { headers: { "User-Agent": YUA } });
  if (!r.ok) return [];
  const d = await r.json().catch(() => null);
  return ((d || {}).news || []).map((x) => ({
    t: x.title || "", u: x.link || "", s: x.publisher || "",
    w: (x.providerPublishTime || 0) * 1000, ko: 0,
  })).filter((x) => x.t && x.u && x.w);
}

async function news(url) {
  const t = (url.searchParams.get("ticker") || "").trim().toUpperCase();
  if (!/^[A-Z0-9][A-Z0-9.\-]{0,9}$/.test(t)) {
    return json({ message: "티커를 확인하세요" }, 400);
  }
  // 한쪽이 죽어도 나머지는 살린다.
  // 한쪽이 죽어도 나머지는 살린다.
  const [rss, srch] = await Promise.all([
    yahooRss(t).catch(() => []),
    yahooNews(t).catch(() => []),
  ]);
  const cut = Date.now() - NEWS_DAYS * 86400000;
  // 같은 기사가 두 소스에 다 있다. 제목 앞부분으로 묶고, 매체 이름이 있는
  // 쪽(search)의 정보를 채워 넣는다.
  const byKey = new Map();
  for (const x of [...rss, ...srch]) {
    if (!(x.w >= cut) || !x.t || !x.u) continue;
    const k = x.t.slice(0, 40).toLowerCase().replace(/[^a-z0-9가-힣]/g, "");
    const had = byKey.get(k);
    if (!had) { byKey.set(k, x); continue; }
    if (!had.s && x.s) had.s = x.s;
  }
  const items = [...byKey.values()].sort((a, b) => b.w - a.w).slice(0, NEWS_MAX);
  // 제목을 한국어로. 한 번에 여러 개를 부르되 너무 몰아치지 않는다.
  for (let i = 0; i < items.length; i += 6) {
    const part = items.slice(i, i + 6);
    const ko = await Promise.all(part.map((x) => trKo(x.t)));
    part.forEach((x, j) => { if (ko[j]) x.k = ko[j]; });
  }
  return new Response(JSON.stringify({ code: t, items, days: NEWS_DAYS }), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      // 주가와 나란히 보는 것이라 오래 묵히지 않는다. 번역 비용도 여기서 아낀다.
      "Cache-Control": "public, max-age=300",
    },
  });
}

async function ohlcv(url) {
  const t = (url.searchParams.get("ticker") || "").trim().toUpperCase();
  // 미국 티커는 영문·숫자에 하이픈·점 정도가 붙는다(BRK-B). 그 외는 막는다.
  if (!/^[A-Z0-9][A-Z0-9.\-]{0,9}$/.test(t)) {
    return json({ message: "티커를 확인하세요" }, 400);
  }
  const src =
    "https://query1.finance.yahoo.com/v8/finance/chart/" +
    encodeURIComponent(t) +
    "?range=5y&interval=1d&includePrePost=false";
  try {
    const r = await fetch(src, { headers: { "User-Agent": YUA } });
    if (!r.ok) return json({ message: `주가 조회 실패 (${r.status})` }, 502);
    const d = await r.json();
    const res = ((d.chart || {}).result || [])[0];
    const q = (((res || {}).indicators || {}).quote || [])[0];
    if (!res || !q) return json({ message: "주가 데이터가 없습니다" }, 502);
    const ts = res.timestamp || [];
    const rows = [];
    for (let i = 0; i < ts.length; i++) {
      const o = q.open[i], h = q.high[i], l = q.low[i], c = q.close[i];
      // 거래정지·결측일은 버린다. 남기면 차트가 바닥까지 떨어진다.
      if (![o, h, l, c].every((x) => typeof x === "number" && isFinite(x) && x > 0)) {
        continue;
      }
      const dt = new Date(ts[i] * 1000);
      const ymd =
        dt.getUTCFullYear() +
        String(dt.getUTCMonth() + 1).padStart(2, "0") +
        String(dt.getUTCDate()).padStart(2, "0");
      rows.push([ymd, o, h, l, c, q.volume[i] || 0]);
    }
    if (rows.length < 30) return json({ message: "주가 데이터가 부족합니다" }, 502);
    // 원본과 다름: 거래소 이름을 같이 준다(야후가 이미 응답에 담아 준다).
    // 스크리너에는 거래소 정보가 없는데, Motley Fool·구글 파이낸스 링크는
    // 거래소(nyse/nasdaq)를 틀리면 404 가 난다(실측: fool.com/quote/nyse/nvda → 404).
    const ex = ((res.meta || {}).fullExchangeName) || null;
    return new Response(JSON.stringify({ code: t, rows, ex }), {
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        // 일봉이라 장중에도 30분에 한 번이면 충분하다.
        "Cache-Control": "public, max-age=1800",
      },
    });
  } catch (e) {
    return json({ message: "주가를 불러오지 못했습니다: " + String(e).slice(0, 80) }, 502);
  }
}

/* ---- 기업 개요 ----
   무슨 사업을 하는 회사인지. 야후 assetProfile 의 사업 설명을 중계한다.
   전 종목 설명을 페이지에 심으면 수 MB 가 늘어나므로 열 때 그 종목만 받는다.
   설명은 영어 원문 그대로다 — 옮기면 뉘앙스가 바뀐다. */
/* 네이버는 미국 종목도 한국어 기업개요를 준다. 종목 코드 규칙이 거래소마다
   달라서 몇 가지를 차례로 시도한다 — 나스닥은 뒤에 `.O`, NYSE 는 티커 그대로,
   클래스주는 `BRK-B` 가 아니라 `BRKb` 다. */
async function naverOverview(t) {
  const cls = t.replace(/[.\-]([A-Z])$/, (m, c) => c.toLowerCase());
  const cands = [...new Set([t + ".O", t, cls + ".O", cls])];
  for (const c of cands) {
    try {
      const r = await fetch(
        `https://api.stock.naver.com/stock/${encodeURIComponent(c)}/overview`,
        { headers: { "User-Agent": YUA, Referer: "https://m.stock.naver.com/" } }
      );
      if (!r.ok) continue;
      const d = await r.json();
      if (d && d.summary) {
        return {
          summary: String(d.summary).replace(/<br\s*\/?>/gi, "\n").trim(),
          nameKo: d.companyName || null,
          industryKo: ((d.industry || {}).industryGroupKor) || null,
        };
      }
    } catch (e) { /* 다음 후보로 */ }
  }
  return null;
}

async function yahooProfile(t) {
  try {
    const { ck, crumb } = await yAuth();
    if (!crumb) return {};
    const r = await fetch(
      "https://query2.finance.yahoo.com/v10/finance/quoteSummary/" +
        `${t}?modules=assetProfile&crumb=${encodeURIComponent(crumb)}`,
      { headers: { "User-Agent": YUA, Cookie: ck } }
    );
    if (!r.ok) return {};
    const d = await r.json();
    return ((((d.quoteSummary || {}).result || [])[0] || {}).assetProfile) || {};
  } catch (e) {
    return {};
  }
}

/* 영문 설명을 한국어로 옮긴다. 네이버에 한국어 개요가 없는 종목(주로 중소형)
   에만 쓴다. 긴 글은 한 번에 못 보내므로 문장 경계로 잘라 나눠 보낸다 —
   문장 중간에서 자르면 번역이 엉킨다. 실패하면 원문을 그대로 둔다. */
async function translateKo(text) {
  if (!text) return null;
  const parts = [];
  let buf = "";
  for (const sent of text.split(/(?<=[.!?])\s+/)) {
    if ((buf + sent).length > 900 && buf) { parts.push(buf); buf = ""; }
    buf += (buf ? " " : "") + sent;
  }
  if (buf) parts.push(buf);
  if (parts.length > 6) parts.length = 6;        // 지나치게 긴 글은 앞부분만
  const out = [];
  for (const p of parts) {
    try {
      const r = await fetch(
        "https://translate.googleapis.com/translate_a/single?client=gtx" +
          "&sl=en&tl=ko&dt=t&q=" + encodeURIComponent(p),
        { headers: { "User-Agent": YUA } }
      );
      if (!r.ok) return null;
      const d = await r.json();
      if (!Array.isArray(d) || !Array.isArray(d[0])) return null;
      out.push(d[0].map((x) => (x && x[0]) || "").join(""));
    } catch (e) {
      return null;
    }
  }
  const joined = out.join(" ").trim();
  return joined || null;
}

async function profile(url) {
  const t = (url.searchParams.get("ticker") || "").trim().toUpperCase();
  if (!/^[A-Z0-9][A-Z0-9.\-]{0,9}$/.test(t)) {
    return json({ message: "티커를 확인하세요" }, 400);
  }
  // 한국어 설명이 있으면 그걸 쓴다. 없으면 야후 영문을 번역해서 준다 —
  // 영문 원문을 그대로 보여 달라는 화면이 아니다.
  const [ko, p] = await Promise.all([naverOverview(t), yahooProfile(t)]);
  let summary = (ko && ko.summary) || null;
  let lang = summary ? "ko" : null;
  if (!summary && p.longBusinessSummary) {
    const tr = await translateKo(p.longBusinessSummary);
    summary = tr || p.longBusinessSummary;
    lang = tr ? "ko-mt" : "en";        // ko-mt = 기계 번역
  }
  if (!summary && !p.industry) {
    return json({ message: "개요를 불러오지 못했습니다" }, 502);
  }
  return new Response(
    JSON.stringify({
      code: t,
      summary,
      lang: lang || "en",
      nameKo: (ko && ko.nameKo) || null,
      sector: p.sector || null,
      industry: (ko && ko.industryKo) || p.industry || null,
      industryEn: p.industry || null,
      employees: p.fullTimeEmployees ?? null,
      website: p.website || null,
      city: p.city || null,
      state: p.state || null,
      country: p.country || null,
    }),
    {
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        // 사업 설명은 거의 안 바뀐다. 하루 캐시.
        "Cache-Control": "public, max-age=86400",
      },
    }
  );
}

/* 야후의 quoteSummary 계열은 쿠키 + crumb 이 있어야 열린다. */
async function yAuth() {
  const c0 = await fetch("https://fc.yahoo.com", { headers: { "User-Agent": YUA } });
  const ck = (c0.headers.get("set-cookie") || "").split(";")[0];
  const c1 = await fetch("https://query1.finance.yahoo.com/v1/test/getcrumb", {
    headers: { "User-Agent": YUA, Cookie: ck },
  });
  const crumb = (await c1.text()).trim();
  return { ck, crumb: crumb && crumb.length <= 40 ? crumb : "" };
}

/* ---- 분기 실적 탭 ----
   최근 6개 분기의 매출·매출총이익·영업이익·순이익과 이익률, 그리고 그 분기
   EPS 컨센서스 대비 서프라이즈. 야후 두 곳에서 받아 합친다.
   한국판은 여기가 영업이익 컨센인데, 미국은 영업이익 컨센이 무료로 열려
   있지 않아 EPS 기준이다(Finnhub·FMP 모두 유료 전용임을 확인). */
const TS_FIELDS = ["TotalRevenue", "GrossProfit", "OperatingIncome", "NetIncome"];
const tsTypes = (annual) =>
  TS_FIELDS.map((f) => (annual ? "annual" : "quarterly") + f).join(",");

async function yTimeseries(t, annual) {
  const now = Math.floor(Date.now() / 1000);
  const url =
    "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/" +
    `${t}?symbol=${t}&type=${tsTypes(annual)}` +
    `&period1=${now - 3600 * 24 * (annual ? 2400 : 900)}&period2=${now + 86400}`;
  const r = await fetch(url, { headers: { "User-Agent": YUA } });
  if (!r.ok) throw new Error("timeseries " + r.status);
  const d = await r.json();
  const by = new Map();               // asOfDate → {sales, gp, op, np}
  const pre = annual ? "annual" : "quarterly";
  const KEY = {
    [pre + "TotalRevenue"]: "sales",
    [pre + "GrossProfit"]: "gp",
    [pre + "OperatingIncome"]: "op",
    [pre + "NetIncome"]: "np",
  };
  for (const blk of ((d.timeseries || {}).result) || []) {
    for (const [k, arr] of Object.entries(blk)) {
      const field = KEY[k];
      if (!field || !Array.isArray(arr)) continue;
      for (const e of arr) {
        if (!e || !e.asOfDate) continue;
        const v = (e.reportedValue || {}).raw;
        if (typeof v !== "number") continue;
        const row = by.get(e.asOfDate) || { d: e.asOfDate };
        row[field] = v / 1e6;         // 백만달러
        by.set(e.asOfDate, row);
      }
    }
  }
  return [...by.values()].sort((a, b) => (a.d < b.d ? -1 : 1));
}

async function yProfileEpsTrend(t) {
  // crumb 이 필요한 엔드포인트다. 쿠키를 받고 crumb 을 얻어야 열린다.
  try {
    const { ck, crumb } = await yAuth();
    if (!crumb) return { eps: {}, fwd: [] };
    const r = await fetch(
      "https://query2.finance.yahoo.com/v10/finance/quoteSummary/" +
        `${t}?modules=earningsHistory&crumb=${encodeURIComponent(crumb)}`,
      { headers: { "User-Agent": YUA, Cookie: ck } }
    );
    if (!r.ok) return { eps: {}, fwd: [] };
    const d = await r.json();
    const hist =
      ((((d.quoteSummary || {}).result || [])[0] || {}).earningsHistory || {})
        .history || [];
    const out = {};
    for (const h of hist) {
      const q = ((h.quarter || {}).fmt) || "";
      if (!q) continue;
      out[q] = {
        eps_a: (h.epsActual || {}).raw ?? null,
        eps_e: (h.epsEstimate || {}).raw ?? null,
        // 야후는 비율(0.0674)로 준다 — %로 맞춘다.
        surp: (h.surprisePercent || {}).raw != null
          ? Math.round(h.surprisePercent.raw * 1000) / 10
          : null,
      };
    }
    const fwd = await yTrend(t, ck, crumb);
    return { eps: out, fwd };
  } catch (e) {
    return { eps: {}, fwd: [] };      // 컨센이 없어도 실적표는 보여준다
  }
}

/* 앞으로의 컨센서스(매출·EPS). 야후 earningsTrend 는 **앞선 분기만** 준다
   — 0q 는 아직 발표 안 된 분기다. 지난 분기의 매출 컨센은 무료로 열려 있는
   곳이 없어(야후·StockAnalysis 모두 EPS 만), 매출은 서프라이즈 대신
   '앞으로의 기대치'를 (E) 열로 보여준다. */
async function yTrend(t, ck, crumb) {
  try {
    const r = await fetch(
      "https://query2.finance.yahoo.com/v10/finance/quoteSummary/" +
        `${t}?modules=earningsTrend&crumb=${encodeURIComponent(crumb)}`,
      { headers: { "User-Agent": YUA, Cookie: ck } }
    );
    if (!r.ok) return [];
    const d = await r.json();
    const tr =
      ((((d.quoteSummary || {}).result || [])[0] || {}).earningsTrend || {})
        .trend || [];
    return tr
      .filter((x) => x.period === "0q" || x.period === "+1q")
      .map((x) => ({
        end: x.endDate || "",
        rev_e: (((x.revenueEstimate || {}).avg) || {}).raw ?? null,
        eps_e: (((x.earningsEstimate || {}).avg) || {}).raw ?? null,
      }))
      .filter((x) => x.end && (x.rev_e != null || x.eps_e != null));
  } catch (e) {
    return [];
  }
}

const daysApart = (a, b) =>
  Math.abs((new Date(a + "T00:00:00Z") - new Date(b + "T00:00:00Z")) / 86400000);

async function fin(url) {
  const t = (url.searchParams.get("ticker") || "").trim().toUpperCase();
  if (!/^[A-Z0-9][A-Z0-9.\-]{0,9}$/.test(t)) {
    return json({ message: "티커를 확인하세요" }, 400);
  }
  const annual = url.searchParams.get("period") === "year";
  let rows;
  try {
    rows = await yTimeseries(t, annual);
  } catch (e) {
    return json({ message: "실적을 불러오지 못했습니다 (" + e.message + ")" }, 502);
  }
  if (!rows.length) return json({ message: "분기 실적이 없습니다" }, 404);
  rows = rows.slice(annual ? -5 : -6);

  // 연간 표에는 분기 EPS 서프라이즈를 붙이지 않는다(기간이 다르다).
  const { eps, fwd } = annual ? { eps: {}, fwd: [] } : await yProfileEpsTrend(t);
  const q = rows.map((r) => {
    const pct = (a, b) => (a != null && b ? (a / b) * 100 : null);
    // 실적 발표일과 회계분기 종료일이 며칠 어긋나므로 가까운 것을 붙인다.
    let best = null;
    for (const [d, v] of Object.entries(eps)) {
      const g = daysApart(d, r.d);
      if (g <= 20 && (!best || g < best[0])) best = [g, v];
    }
    const e = best ? best[1] : {};
    return {
      d: r.d,
      key: r.d.replace(/-/g, "").slice(0, 6),
      label: annual ? r.d.slice(0, 4) : r.d.slice(2, 4) + "." + r.d.slice(5, 7),
      est: false,
      sales: r.sales ?? null,
      gp: r.gp ?? null,
      op: r.op ?? null,
      np: r.np ?? null,
      gpm: pct(r.gp, r.sales),
      opm: pct(r.op, r.sales),
      nim: pct(r.np, r.sales),
      eps_a: e.eps_a ?? null,
      eps_e: e.eps_e ?? null,
      surp: e.surp ?? null,
    };
  });
  // 이미 실적이 있는 분기와 겹치지 않는 것만 (E) 열로 덧붙인다.
  for (const f of fwd) {
    if (q.some((x) => daysApart(f.end, x.d || "1900-01-01") <= 20)) continue;
    if (q.some((x) => x.key === f.end.replace(/-/g, "").slice(0, 6))) continue;
    q.push({
      key: f.end.replace(/-/g, "").slice(0, 6),
      label: f.end.slice(2, 4) + "." + f.end.slice(5, 7),
      est: true,
      sales: f.rev_e != null ? f.rev_e / 1e6 : null,
      gp: null, op: null, np: null, gpm: null, opm: null, nim: null,
      eps_a: null, eps_e: f.eps_e ?? null, surp: null,
    });
  }
  q.sort((a, b) => (a.key < b.key ? -1 : 1));

  return new Response(JSON.stringify({ code: t, q, dart: false }), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=1800",
    },
  });
}

/* 상세 창 라우팅. 처리할 주소가 아니면 null 을 돌려줘 정적 파일로 넘긴다. */
async function detailApi(url) {
  if (url.pathname === "/api/ohlcv") return ohlcv(url);
  if (url.pathname === "/api/fin") return fin(url);
  if (url.pathname === "/api/news") return news(url);
  if (url.pathname === "/api/profile") return profile(url);
  return null;
}
