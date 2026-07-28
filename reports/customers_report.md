# 고객군 자동 지정 리포트

생성: 2026-07-28 08:11:30 UTC · 대상 연도: 2024

## 1. 사용 가능한 산업연관표

<details><summary>전체 목록</summary>

- `59` Total Requirements, Commodity-by-Commodity - Summary
- `58` Total Requirements, Commodity-by-Commodity - Sector
- `57` Total Requirements, Industry-by-Commodity - Summary
- `56` Total Requirements, Industry-by-Commodity - Sector
- `61` Total Requirements, Industry-by-Industry - Summary
- `60` Total Requirements, Industry-by-Industry - Sector
- `262` The Domestic Supply of Commodities by Industries - Summary
- `261` The Domestic Supply of Commodities by Industries - Sector
- `259` The Use of Commodities by Industries - Summary
- `258` The Use of Commodities by Industries - Sector

</details>

선택한 표: **TableID 259** — The Use of Commodities by Industries - Summary

데이터: 2024년, 4,640행

## 2. 행 코드(공급 산업) 목록

<details><summary>전체</summary>

- `111CA` Farms
- `113FF` Forestry, fishing, and related activities
- `211` Oil and gas extraction
- `212` Mining, except oil and gas
- `213` Support activities for mining
- `22` Utilities
- `23` Construction
- `311FT` Food and beverage and tobacco products
- `313TT` Textile mills and textile product mills
- `315AL` Apparel and leather and allied products
- `321` Wood products
- `322` Paper products
- `323` Printing and related support activities
- `324` Petroleum and coal products
- `325` Chemical products
- `326` Plastics and rubber products
- `327` Nonmetallic mineral products
- `331` Primary metals
- `332` Fabricated metal products
- `333` Machinery
- `334` Computer and electronic products
- `335` Electrical equipment, appliances, and components
- `3361MV` Motor vehicles, bodies and trailers, and parts
- `3364OT` Other transportation equipment
- `337` Furniture and related products
- `339` Miscellaneous manufacturing
- `42` Wholesale trade
- `481` Air transportation
- `482` Rail transportation
- `483` Water transportation
- `484` Truck transportation
- `485` Transit and ground passenger transportation
- `486` Pipeline transportation
- `487OS` Other transportation and support activities
- `493` Warehousing and storage
- `4A0` Other retail
- `511` Publishing industries, except internet (includes software)
- `512` Motion picture and sound recording industries
- `513` Broadcasting and telecommunications
- `514` Data processing, internet publishing, and other information services
- `521CI` Federal Reserve banks, credit intermediation, and related activities
- `523` Securities, commodity contracts, and investments
- `524` Insurance carriers and related activities
- `525` Funds, trusts, and other financial vehicles
- `532RL` Rental and leasing services and lessors of intangible assets
- `5411` Legal services
- `5412OP` Miscellaneous professional, scientific, and technical services
- `5415` Computer systems design and related services
- `55` Management of companies and enterprises
- `561` Administrative and support services
- `562` Waste management and remediation services
- `61` Educational services
- `621` Ambulatory health care services
- `622` Hospitals
- `623` Nursing and residential care facilities
- `624` Social assistance
- `711AS` Performing arts, spectator sports, museums, and related activities
- `713` Amusements, gambling, and recreation industries
- `721` Accommodation
- `722` Food services and drinking places
- `81` Other services, except government
- `GFE` Federal government enterprises
- `GFGD` Federal general government (defense)
- `GFGN` Federal general government (nondefense)
- `GSLE` State and local government enterprises
- `GSLG` State and local general government
- `HS` Housing
- `ORE` Other real estate
- `Other` Noncomparable imports and rest-of-the-world adjustment
- `T005` Total Intermediate
- `T00OSUB` Less: Other subsidies on production
- `T00OTOP` Other taxes on production
- `T00SUB` Less: Subsidies on products
- `T00TOP` Taxes on products and imports
- `T018` Total industry output (basic prices)
- `Used` Scrap, used and secondhand goods
- `V001` Compensation of employees
- `V003` Gross operating surplus
- `VABAS` Value Added (basic prices)
- `VAPRO` Value Added (producer prices)

</details>

## 3. 테마별 고객 산업

### 전력기기·그리드

공급 산업: `335` Electrical equipment, appliances, and components  (NAICS 335 ← `IPG335S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Construction | `23` | 29.3% | IPCONGD |
| Nonresidential private fixed investment in equipment | `F02E` | 23.8% | — |
| Machinery | `333` | 7.2% | IPG333S |
| Electrical equipment, appliances, and components | `335` | 5.5% | IPG335S |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 5.4% | IPG3361T3S |
| Residential private fixed investment | `F02R` | 5.3% | — |
| Miscellaneous professional, scientific, and technica | `5412OP` | 2.8% | — |
| Wholesale trade | `42` | 2.6% | IPBUSEQ |

제안 `customers.series`: **IPCONGD** (IPUTIL → IPCONGD)

### 반도체 첨단패키징·후공정

공급 산업: `334` Computer and electronic products  (NAICS 3344 ← `IPG3344S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Nonresidential private fixed investment in equipment | `F02E` | 47.0% | — |
| Wholesale trade | `42` | 9.2% | IPBUSEQ |
| Computer and electronic products | `334` | 6.5% | IPG334S |
| Broadcasting and telecommunications | `513` | 5.3% | — |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 4.2% | IPG3361T3S |
| Management of companies and enterprises | `55` | 3.9% | — |
| Other transportation equipment | `3364OT` | 3.3% | IPG3364T9S |
| Miscellaneous professional, scientific, and technica | `5412OP` | 2.3% | — |

제안 `customers.series`: **IPBUSEQ** (IPG3344S → IPBUSEQ)

### 항공 애프터마켓·MRO

공급 산업: `3361MV` Motor vehicles, bodies and trailers, and parts  (NAICS 3364 ← `IPG3364T9S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Nonresidential private fixed investment in equipment | `F02E` | 48.7% | — |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 31.9% | IPG3361T3S |
| Administrative and support services | `561` | 3.1% | — |
| Machinery | `333` | 1.9% | IPG333S |
| Wholesale trade | `42` | 1.4% | IPBUSEQ |
| Truck transportation | `484` | 1.3% | — |
| Motor vehicle and parts dealers | `441` | 1.2% | — |
| Other retail | `4A0` | 1.1% | — |

제안 `customers.series`: **IPG3361T3S** (IPG3364T9S → IPG3361T3S)

### 데이터센터 열관리

공급 산업: `333` Machinery  (NAICS 333 ← `IPG333S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Nonresidential private fixed investment in equipment | `F02E` | 60.5% | — |
| Construction | `23` | 10.2% | IPCONGD |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 6.2% | IPG3361T3S |
| Machinery | `333` | 6.1% | IPG333S |
| Oil and gas extraction | `211` | 2.3% | IPMINE |
| Food and beverage and tobacco products | `311FT` | 1.1% | — |
| Administrative and support services | `561` | 1.1% | — |
| Chemical products | `325` | 1.0% | IPG325S |

제안 `customers.series`: **IPCONGD** (IPG3341S → IPCONGD)

### 정유·정제마진

공급 산업: `324` Petroleum and coal products  (NAICS 324 ← `IPG324S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Construction | `23` | 20.8% | IPCONGD |
| Truck transportation | `484` | 14.5% | — |
| Air transportation | `481` | 9.8% | — |
| Utilities | `22` | 6.5% | IPUTIL |
| Petroleum and coal products | `324` | 4.4% | IPG324S |
| Other transportation and support activities | `487OS` | 4.0% | — |
| Farms | `111CA` | 3.4% | — |
| Chemical products | `325` | 3.1% | IPG325S |

제안 `customers.series`: **IPCONGD** (IPG324S → IPCONGD)

### 원자력 연료주기

공급 산업: `22` Utilities  (NAICS 22 ← `IPUTIL`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Other real estate | `ORE` | 11.1% | — |
| Utilities | `22` | 8.6% | IPUTIL |
| Food services and drinking places | `722` | 7.3% | — |
| Other retail | `4A0` | 4.4% | — |
| Wholesale trade | `42` | 4.0% | IPBUSEQ |
| Construction | `23` | 3.8% | IPCONGD |
| Chemical products | `325` | 3.6% | IPG325S |
| Farms | `111CA` | 3.1% | — |

제안 `customers.series`: **IPUTIL** (그대로)

### 철강·특수강

공급 산업: `331` Primary metals  (NAICS 331 ← `IPG331S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Fabricated metal products | `332` | 27.4% | IPG332S |
| Primary metals | `331` | 23.5% | IPG331S |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 14.6% | IPG3361T3S |
| Machinery | `333` | 10.7% | IPG333S |
| Electrical equipment, appliances, and components | `335` | 7.4% | IPG335S |
| Construction | `23` | 2.5% | IPCONGD |
| Oil and gas extraction | `211` | 2.4% | IPMINE |
| Other transportation equipment | `3364OT` | 1.8% | IPG3364T9S |

제안 `customers.series`: **IPG332S** (그대로)

### 방산·탄약

공급 산업: `3361MV` Motor vehicles, bodies and trailers, and parts  (NAICS 3364 ← `IPG3364T9S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Nonresidential private fixed investment in equipment | `F02E` | 48.7% | — |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 31.9% | IPG3361T3S |
| Administrative and support services | `561` | 3.1% | — |
| Machinery | `333` | 1.9% | IPG333S |
| Wholesale trade | `42` | 1.4% | IPBUSEQ |
| Truck transportation | `484` | 1.3% | — |
| Motor vehicle and parts dealers | `441` | 1.2% | — |
| Other retail | `4A0` | 1.1% | — |

제안 `customers.series`: **IPG3361T3S** (없음 → IPG3361T3S)

## 4. 이 리포트가 못 하는 것

- **고객 티커는 자동으로 못 정한다.** 산업연관표는 산업 단위이고 상장사 매핑이 없다. ④교체주기 축이 쓰는 `customers.tickers` 는 여전히 수동이다.
- 비중은 미국 국내 산업 간 거래 기준이다. 수출 비중이 큰 테마는 실제 고객이 표에 안 잡힌다.
- 산업연관표는 공표가 늦다(현재 2024년). 최근 구조 변화는 안 잡힌다.
