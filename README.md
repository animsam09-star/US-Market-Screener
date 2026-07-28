# 미국 섹터 스크리너

**이미 오른 섹터를 따라가지 않고, 앞으로 오를 섹터를 찾기 위한 도구.**

두 축의 교집합으로 테마를 고른다.

- **촉매 축** — 왜 오를 이유가 있나 (9개 축)
- **미반영 축** — 왜 아직 가격에 없나 (4개 축)

촉매만 보면 결국 남들이 이미 산 걸 산다. 미반영 축이 그걸 막는다.

전 지표가 **무료 공공데이터**다: FRED · SEC XBRL · SEC 전문검색 · Federal Register ·
Yahoo Finance · BEA 산업연관표.

---

## 판별 방법

각 축은 지표 하나가 아니라 **주장 · 확증 · 기각** 3요소로 판정한다.

| | |
|---|---|
| **주장** | 관측 가능한 명제 |
| **확증** | 독립된 두 번째 데이터가 같은 말을 하는가 |
| **기각** | 같은 숫자를 만드는 *나쁜 이유*를 배제했는가 |

기각에 걸린 축은 **점수 0이 아니라 '기각 + 사유'** 로 화면에 남는다.
조용한 0점은 "신호가 약함"과 "논리가 틀림"을 구별하지 못하게 만들기 때문이다.

예: 가동률이 높다고 다 공급 부족이 아니다. 생산능력이 줄고 생산도 줄었다면
수요가 늘어 가동률이 오른 게 아니라 **설비를 닫아서** 오른 사양산업이다.
이 판별에는 `CAPUTL*`(가동률) 외에 `CAPG*`(생산능력)와 `IPG*`(생산)가 함께 필요하다.

촉매 점수는 9개 축의 단순평균이 아니라 **최강 2개 축의 평균**이다. 테마는 보통
한두 축으로 오르고, 9개를 평균하면 강한 신호가 무관한 축에 희석된다.

전체 판별식은 **[설계_촉매판별.md](설계_촉매판별.md)** 참조.

---

## 쓰는 법

### 처음 한 번

```bash
pip install -r requirements.txt
```

BEA 산업연관표(고객군 자동 지정)를 쓰려면 [무료 키](https://apps.bea.gov/API/signup/)를
발급받아 `bea_key.txt` 에 한 줄로 넣는다. 키가 없어도 나머지는 다 돌아간다.

```bash
python check_key.py     # 키가 읽히고 실제로 통하는지 확인
```

### 실행

```bash
python run.py
```

`out/screener.html` 이 만들어지고 브라우저가 열린다.

| 옵션 | |
|---|---|
| `--theme 정유` | 이름에 '정유'가 들어간 테마만 |
| `--no-open` | 브라우저 안 열기 |
| `--refresh` | 캐시 무시하고 새로 받기 |

### 테마 추가·수정

`themes.yaml` 블록 하나를 복사해 고치면 된다. 파일 상단에 필드 설명이 있다.

핵심은 `customers:` 블록이다. **①낙수와 ④교체주기는 테마 자신이 아니라 테마의
고객을 재야 한다.** 전력기기가 오르는 이유는 전력기기 산업생산이 늘어서가 아니라
유틸리티·데이터센터의 설비가 늙고 증설이 밀려서다.

---

## 사내망에서 쓸 때 (중요)

다올 사내망은 SSL 검사 프록시를 쓴다. 인증서를 갈아끼우기 때문에 `certifi` 번들을
쓰는 도구(`curl`, `requests` 기본값)는 **전부 실패**한다 —
`CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain`.

Windows 인증서 저장소에는 사내 CA가 등록돼 있으므로, `truststore` 로 OS 네이티브
검증을 파이썬에 주입하면 해결된다. `screener/net.py` 가 이미 하고 있고,
`requirements.txt` 에 포함돼 있다.

설치 자체가 SSL 때문에 막히면:

```bash
python -m pip install truststore --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

`git push` 가 같은 이유로 막히면 Windows 인증서 저장소를 쓰게 한다:

```bash
git config --global http.sslBackend schannel
```

GitHub Actions 러너는 사내망 밖이라 이 문제가 없다.

---

## 자동 갱신 · 외부 접근

`.github/workflows/update.yml` 이 평일 미국장 마감 후 하루 한 번 돌면서 대시보드를
다시 만든다. 결과는 두 곳에서 볼 수 있다.

- **GitHub Pages** — 어디서든 URL로 열람
- **Actions 아티팩트** — Pages를 안 쓰는 경우 `screener-html` 다운로드

필요한 저장소 시크릿 (Settings → Secrets and variables → Actions):

| 이름 | 필수 | 용도 |
|---|---|---|
| `BEA_API_KEY` | 선택 | 산업연관표 기반 고객군 자동 지정 |
| `SCREENER_UA` | 권장 | SEC 가 요구하는 연락처 포함 User-Agent. 없으면 403 위험 |

---

## 한계 (읽고 쓸 것)

- **컨센서스 추정치 리비전이 없다.** 무료로 구할 수 없어 SEC XBRL 기반 TTM 매출
  증가율의 가속도로 대신했다. 실제 리비전보다 2~3개월 늦다.
- **⑩ 대체·점유율 이전 축은 미구현.** 세부 품목별 출하 믹스가 필요하다.
- **⑧⑨ 재고·병목 축은 테마별 산업 시리즈를 지정해야 켜진다.** 전 제조업 총계로
  폴백하면 모든 테마가 같은 점수를 받아 순위가 무의미해지므로, 지정 없으면 끈다.
- 이 도구는 **후보를 좁히는 장치**이지 매수 판단이 아니다. 각 축의 '근거↗' 링크로
  원본을 확인하고 판단할 것.

## 폴더

```
run.py                 실행 진입점
check_key.py           BEA 키 점검
themes.yaml            테마 정의 — 여기만 고치면 된다
설계_촉매판별.md         판별식 설계 문서
screener/
  net.py               truststore + 디스크 캐시 + 레이트리밋
  sources.py           FRED / SEC / Yahoo / Federal Register 어댑터
  axes.py              촉매 9축 판별식 (주장·확증·기각)
  signals.py           미반영 4축 + 재무 집계 + 테마 평가
  stats.py             분위·시차상관·TTM 등 통계
  dashboard.py         HTML 생성
  keys.py              API 키 로딩
```
