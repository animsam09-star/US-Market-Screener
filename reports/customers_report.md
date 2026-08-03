# 고객군 자동 지정 리포트

생성: 2026-08-03 10:11:52 UTC · 대상 연도: 2024

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
| Construction | `23` | 41.4% | —  건설 — 실질 산출 지수 없음(건설지출은 명목) |
| Machinery | `333` | 10.2% | IPG333S |
| Electrical equipment, appliances, and components | `335` | 7.8% | —  자기 산업 — 순환이라 낙수 축에 못 씀 |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 7.6% | IPG3361T3S |
| Miscellaneous professional, scientific, and technica | `5412OP` | 3.9% | —  전문서비스 — 산업생산 지수 없음 |
| Wholesale trade | `42` | 3.7% | —  도매 — 산업생산 지수 없음 |
| Farms | `111CA` | 2.6% | — |
| Fabricated metal products | `332` | 2.3% | IPG332S |

자기 산업 내 거래 7.8% — 후보에서 제외했다.

제안 `customers.series`: **IPG333S** (비중 10.2%, IPUTIL → IPG333S)

### 반도체 첨단패키징·후공정

공급 산업: `334` Computer and electronic products  (NAICS 3344 ← `IPG3344S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Wholesale trade | `42` | 17.3% | —  도매 — 산업생산 지수 없음 |
| Computer and electronic products | `334` | 12.3% | —  자기 산업 — 순환이라 낙수 축에 못 씀 |
| Broadcasting and telecommunications | `513` | 10.0% | —  방송·통신 — 산업생산 지수 없음 |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 8.0% | IPG3361T3S |
| Management of companies and enterprises | `55` | 7.3% | —  지주회사 — 산업 아님 |
| Other transportation equipment | `3364OT` | 6.3% | IPG3364T9S |
| Miscellaneous professional, scientific, and technica | `5412OP` | 4.3% | —  전문서비스 — 산업생산 지수 없음 |
| Ambulatory health care services | `621` | 3.8% | — |

자기 산업 내 거래 12.3% — 후보에서 제외했다.

제안 없음 — 지표화 가능한 최상위 고객 `Motor vehicles, bodies and trailers, and` 이 8.0% 에 불과해 전방수요를 대표하지 못한다. 현재 값 `IPG3344S` 유지 권장.

### 항공 애프터마켓·MRO

공급 산업: `3364OT` Other transportation equipment  (NAICS 3364 ← `IPG3364T9S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Other transportation equipment | `3364OT` | 88.5% | —  자기 산업 — 순환이라 낙수 축에 못 씀 |
| Other transportation and support activities | `487OS` | 2.7% | — |
| Miscellaneous professional, scientific, and technica | `5412OP` | 2.1% | —  전문서비스 — 산업생산 지수 없음 |
| Air transportation | `481` | 1.7% | —  항공운송 — 산업생산 지수 없음 |
| Rail transportation | `482` | 1.5% | — |
| Water transportation | `483` | 1.4% | — |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 1.0% | IPG3361T3S |
| Machinery | `333` | 0.4% | IPG333S |

자기 산업 내 거래 88.5% — 후보에서 제외했다.

제안 없음 — 지표화 가능한 최상위 고객 `Motor vehicles, bodies and trailers, and` 이 1.0% 에 불과해 전방수요를 대표하지 못한다. 현재 값 `AIRRPMTSI` 유지 권장.

### 데이터센터 열관리

공급 산업: `333` Machinery  (NAICS 333 ← `IPG333S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Construction | `23` | 25.9% | —  건설 — 실질 산출 지수 없음(건설지출은 명목) |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 15.8% | IPG3361T3S |
| Machinery | `333` | 15.4% | —  자기 산업 — 순환이라 낙수 축에 못 씀 |
| Oil and gas extraction | `211` | 5.9% | IPMINE |
| Food and beverage and tobacco products | `311FT` | 2.8% | — |
| Administrative and support services | `561` | 2.8% | —  사업지원 서비스 — 산업생산 지수 없음 |
| Chemical products | `325` | 2.5% | IPG325S |
| Fabricated metal products | `332` | 2.5% | IPG332S |

자기 산업 내 거래 15.4% — 후보에서 제외했다.

제안 `customers.series`: **IPG3361T3S** (비중 15.8%, IPG3341S → IPG3361T3S)

### 정유·정제마진

공급 산업: `324` Petroleum and coal products  (NAICS 324 ← `IPG324S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Construction | `23` | 20.8% | —  건설 — 실질 산출 지수 없음(건설지출은 명목) |
| Truck transportation | `484` | 14.5% | —  트럭운송 — 산업생산 지수 없음 |
| Air transportation | `481` | 9.8% | —  항공운송 — 산업생산 지수 없음 |
| Utilities | `22` | 6.5% | IPUTIL |
| Petroleum and coal products | `324` | 4.4% | —  자기 산업 — 순환이라 낙수 축에 못 씀 |
| Other transportation and support activities | `487OS` | 4.0% | — |
| Farms | `111CA` | 3.4% | — |
| Chemical products | `325` | 3.1% | IPG325S |

자기 산업 내 거래 4.4% — 후보에서 제외했다.

제안 없음 — 지표화 가능한 최상위 고객 `Utilities` 이 6.5% 에 불과해 전방수요를 대표하지 못한다. 현재 값 `IPG324S` 유지 권장.

### 원자력 연료주기

공급 산업: `22` Utilities  (NAICS 22 ← `IPUTIL`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Other real estate | `ORE` | 11.1% | — |
| Utilities | `22` | 8.6% | —  자기 산업 — 순환이라 낙수 축에 못 씀 |
| Food services and drinking places | `722` | 7.3% | — |
| Other retail | `4A0` | 4.4% | — |
| Wholesale trade | `42` | 4.0% | —  도매 — 산업생산 지수 없음 |
| Construction | `23` | 3.8% | —  건설 — 실질 산출 지수 없음(건설지출은 명목) |
| Chemical products | `325` | 3.6% | IPG325S |
| Farms | `111CA` | 3.1% | — |

자기 산업 내 거래 8.6% — 후보에서 제외했다.

제안 없음 — 지표화 가능한 최상위 고객 `Chemical products` 이 3.6% 에 불과해 전방수요를 대표하지 못한다. 현재 값 `IPUTIL` 유지 권장.

### 철강·특수강

공급 산업: `331` Primary metals  (NAICS 3311 ← `IPG3311A2S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Fabricated metal products | `332` | 27.4% | IPG332S |
| Primary metals | `331` | 23.5% | —  자기 산업 — 순환이라 낙수 축에 못 씀 |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 14.6% | IPG3361T3S |
| Machinery | `333` | 10.7% | IPG333S |
| Electrical equipment, appliances, and components | `335` | 7.4% | IPG335S |
| Construction | `23` | 2.5% | —  건설 — 실질 산출 지수 없음(건설지출은 명목) |
| Oil and gas extraction | `211` | 2.4% | IPMINE |
| Other transportation equipment | `3364OT` | 1.8% | IPG3364T9S |

자기 산업 내 거래 23.5% — 후보에서 제외했다.

제안 `customers.series`: **IPG332S** (비중 27.4%, 그대로)

### 방산·탄약

공급 산업: `3364OT` Other transportation equipment  (NAICS 3364 ← `IPG3364T9S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Other transportation equipment | `3364OT` | 88.5% | —  자기 산업 — 순환이라 낙수 축에 못 씀 |
| Other transportation and support activities | `487OS` | 2.7% | — |
| Miscellaneous professional, scientific, and technica | `5412OP` | 2.1% | —  전문서비스 — 산업생산 지수 없음 |
| Air transportation | `481` | 1.7% | —  항공운송 — 산업생산 지수 없음 |
| Rail transportation | `482` | 1.5% | — |
| Water transportation | `483` | 1.4% | — |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 1.0% | IPG3361T3S |
| Machinery | `333` | 0.4% | IPG333S |

자기 산업 내 거래 88.5% — 후보에서 제외했다.

제안 없음 — 지표화 가능한 최상위 고객 `Motor vehicles, bodies and trailers, and` 이 1.0% 에 불과해 전방수요를 대표하지 못한다. 현재 값 `없음` 유지 권장.

### 화학·석유화학

공급 산업: `325` Chemical products  (NAICS 325 ← `IPG325S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Chemical products | `325` | 30.5% | —  자기 산업 — 순환이라 낙수 축에 못 씀 |
| Miscellaneous professional, scientific, and technica | `5412OP` | 12.3% | —  전문서비스 — 산업생산 지수 없음 |
| Plastics and rubber products | `326` | 11.0% | IPG326S |
| Ambulatory health care services | `621` | 9.4% | — |
| Farms | `111CA` | 4.9% | — |
| Construction | `23` | 3.7% | —  건설 — 실질 산출 지수 없음(건설지출은 명목) |
| Hospitals | `622` | 3.5% | — |
| Petroleum and coal products | `324` | 2.3% | IPG324S |

자기 산업 내 거래 30.5% — 후보에서 제외했다.

제안 `customers.series`: **IPG326S** (비중 11.0%, 그대로)

### 비료·농화학

공급 산업: `325` Chemical products  (NAICS 325 ← `IPG325S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Chemical products | `325` | 30.5% | —  자기 산업 — 순환이라 낙수 축에 못 씀 |
| Miscellaneous professional, scientific, and technica | `5412OP` | 12.3% | —  전문서비스 — 산업생산 지수 없음 |
| Plastics and rubber products | `326` | 11.0% | IPG326S |
| Ambulatory health care services | `621` | 9.4% | — |
| Farms | `111CA` | 4.9% | — |
| Construction | `23` | 3.7% | —  건설 — 실질 산출 지수 없음(건설지출은 명목) |
| Hospitals | `622` | 3.5% | — |
| Petroleum and coal products | `324` | 2.3% | IPG324S |

자기 산업 내 거래 30.5% — 후보에서 제외했다.

제안 `customers.series`: **IPG326S** (비중 11.0%, IPG311A2S → IPG326S)

### 주택건설

공급 산업: `321` Wood products  (NAICS 321 ← `IPG321S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Construction | `23` | 47.4% | —  건설 — 실질 산출 지수 없음(건설지출은 명목) |
| Wood products | `321` | 19.2% | —  자기 산업 — 순환이라 낙수 축에 못 씀 |
| Wholesale trade | `42` | 5.3% | —  도매 — 산업생산 지수 없음 |
| Other real estate | `ORE` | 4.6% | — |
| Furniture and related products | `337` | 4.0% | — |
| Paper products | `322` | 2.5% | — |
| Rail transportation | `482` | 2.2% | — |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 1.8% | IPG3361T3S |

자기 산업 내 거래 19.2% — 후보에서 제외했다.

제안 없음 — 지표화 가능한 최상위 고객 `Motor vehicles, bodies and trailers, and` 이 1.8% 에 불과해 전방수요를 대표하지 못한다. 현재 값 `없음` 유지 권장.

### 제지·포장

공급 산업: `322` Paper products  (NAICS 322 ← `IPG322S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Paper products | `322` | 27.3% | —  자기 산업 — 순환이라 낙수 축에 못 씀 |
| Food and beverage and tobacco products | `311FT` | 15.6% | — |
| Printing and related support activities | `323` | 4.9% | — |
| Wholesale trade | `42` | 4.6% | —  도매 — 산업생산 지수 없음 |
| Administrative and support services | `561` | 3.8% | —  사업지원 서비스 — 산업생산 지수 없음 |
| Food services and drinking places | `722` | 3.4% | — |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 3.3% | IPG3361T3S |
| Construction | `23` | 3.2% | —  건설 — 실질 산출 지수 없음(건설지출은 명목) |

자기 산업 내 거래 27.3% — 후보에서 제외했다.

제안 없음 — 지표화 가능한 최상위 고객 `Motor vehicles, bodies and trailers, and` 이 3.3% 에 불과해 전방수요를 대표하지 못한다. 현재 값 `IPG311A2S` 유지 권장.

### 트럭·물류

- 산업 식별 실패: FRED 시리즈 `TRUCKD11` 에서 NAICS 를 못 뽑음

### 건설·농기계

공급 산업: `333` Machinery  (NAICS 3331 ← `IPG3331S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Construction | `23` | 25.9% | —  건설 — 실질 산출 지수 없음(건설지출은 명목) |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 15.8% | IPG3361T3S |
| Machinery | `333` | 15.4% | —  자기 산업 — 순환이라 낙수 축에 못 씀 |
| Oil and gas extraction | `211` | 5.9% | IPMINE |
| Food and beverage and tobacco products | `311FT` | 2.8% | — |
| Administrative and support services | `561` | 2.8% | —  사업지원 서비스 — 산업생산 지수 없음 |
| Chemical products | `325` | 2.5% | IPG325S |
| Fabricated metal products | `332` | 2.5% | IPG332S |

자기 산업 내 거래 15.4% — 후보에서 제외했다.

제안 `customers.series`: **IPG3361T3S** (비중 15.8%, IPMINE → IPG3361T3S)

### 의료기기

공급 산업: `339` Miscellaneous manufacturing  (NAICS 339 ← `IPG339S`)

| 고객 산업 | 코드 | 비중 | FRED 지표 |
|---|---|---|---|
| Hospitals | `622` | 39.8% | — |
| Ambulatory health care services | `621` | 29.3% | — |
| Miscellaneous manufacturing | `339` | 5.7% | —  자기 산업 — 순환이라 낙수 축에 못 씀 |
| Motor vehicles, bodies and trailers, and parts | `3361MV` | 3.2% | IPG3361T3S |
| Administrative and support services | `561` | 3.0% | —  사업지원 서비스 — 산업생산 지수 없음 |
| Miscellaneous professional, scientific, and technica | `5412OP` | 3.0% | —  전문서비스 — 산업생산 지수 없음 |
| Machinery | `333` | 2.4% | IPG333S |
| Construction | `23` | 2.3% | —  건설 — 실질 산출 지수 없음(건설지출은 명목) |

자기 산업 내 거래 5.7% — 후보에서 제외했다.

제안 없음 — 지표화 가능한 최상위 고객 `Motor vehicles, bodies and trailers, and` 이 3.2% 에 불과해 전방수요를 대표하지 못한다. 현재 값 `IPG339S` 유지 권장.

### 유전서비스·시추

- 산업 식별 실패: FRED 시리즈 `IPN213111N` 에서 NAICS 를 못 뽑음

## 4. 이 리포트가 못 하는 것

- **고객 티커는 자동으로 못 정한다.** 산업연관표는 산업 단위이고 상장사 매핑이 없다. ④교체주기 축이 쓰는 `customers.tickers` 는 여전히 수동이다.
- 비중은 미국 국내 산업 간 거래 기준이다. 수출 비중이 큰 테마는 실제 고객이 표에 안 잡힌다.
- 산업연관표는 공표가 늦다(현재 2024년). 최근 구조 변화는 안 잡힌다.
