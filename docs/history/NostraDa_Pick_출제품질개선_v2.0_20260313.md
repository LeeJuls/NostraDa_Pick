# NostraDa Pick - 출제 품질 개선 v2.0 히스토리
**버전**: v2.0 | **날짜**: 2026-03-13 | **작업자**: Claude (Backend Agent)

---

## 배경 및 문제 정의

Article-First Architecture(v1.0) 적용 이후에도 남아 있던 출제 품질 이슈들을 연속 수정.

**발견된 문제:**

| # | 문제 | 발생 예시 |
|---|------|-----------|
| 1 | **카테고리 편중** | count=4 생성 시 economy 2개 출제 (max_per_cat=2 하드코딩 → count 무관하게 2 허용) |
| 2 | **코인 2개 동시 출제** | economy 내 BTC 질문 + ETH 질문 동시 출제 허용 |
| 3 | **논리적으로 불가한 경제 질문** | ONS GDP 발표 기사 → "GDP가 수정될까?" (이미 발표된 데이터, 단기 수정 불가) |
| 4 | **스포츠 'draw' 오번역** | "Will Burnley and Bournemouth draw?" → 한국어 "추첨" 오번역 |
| 5 | **statement/announce 패턴 누락** | "Will [govt] announce new sanctions against [vague actors]?" 등 모호한 패턴 여전히 생성 |
| 6 | **정치 질문 기준 불명확** | 검증 가능 여부 기준 없이 다양한 정치 질문 생성 |
| 7 | **테크 키노트 질문 모호** | "Will X be mentioned/highlighted at the keynote?" → 측정 불가 |
| 8 | **vague subject 사용** | "Will any country condemn the drone strike?" → 확률 100% |

---

## 핵심 결정 사항

| # | 결정 | 근거 |
|---|------|------|
| 1 | `max_per_cat = max(1, math.ceil(count / 5))` 동적 계산 | count=4 시 카테고리당 최대 1개, count=8 시 최대 2개 |
| 2 | `is_coin` 플래그 + `coin_count` 전역 추적 → 배치당 코인 최대 1개 | economy 내 코인 질문 중복 구조적 제거 |
| 3 | 이미 발표된 GDP/CPI → 시장 반응(GBP/USD, FTSE) 질문 유도 프롬프트 추가 | 24-48h 내 측정 가능한 outcome으로 리다이렉트 |
| 4 | 스포츠 "draw" 동사 금지 → "finish tied (0-0 or equal score)" 강제 | 한국어 번역 시 "추첨" 오번역 방지 |
| 5 | 정치 질문 4가지 검증 패턴 명시 | Poll number / Legal decision / Parliamentary vote / Named person action |
| 6 | Named Entity Required 규칙 추가 | "any country / any official" 등 vague subject 전면 금지 |
| 7 | 테크/키노트 규칙 추가 | mention/discuss 금지 → binary verifiable product outcome 강제 |
| 8 | statement/announce 추가 금지 패턴 명시 | unnamed actors 대상 제재 공약, follow-up 성명 등 포함 |
| 9 | 후처리 검증에도 동일 공식 적용 | `_max_per_cat = max(1, math.ceil(count / 5))` |

---

## 변경 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `services/gemini_service.py` | 동적 max_per_cat, is_coin 제한, 프롬프트 규칙 5가지 추가/강화 |
| `static/js/app.js` | 관련 기사 보기 폰트 0.6em → 0.9em |

---

## 코드 변경 핵심 부분

### 1. 동적 max_per_cat (카테고리 편중 방지)

```python
# 변경 전 — 하드코딩
max_per_cat = 2  # count=4여도 economy 2개 허용

# 변경 후 — 동적 계산
import math
max_per_cat = max(1, math.ceil(count / len(categories)))
# count=4 → ceil(4/5) = 1 → 카테고리당 최대 1개
# count=8 → ceil(8/5) = 2 → 카테고리당 최대 2개

# 후처리 검증에도 동일 공식
_max_per_cat = max(1, math.ceil(count / 5))
```

### 2. is_coin 플래그 + coin_count (코인 중복 방지)

```python
# 후보 생성 시 is_coin 태깅
# 뉴스 후보 — category가 crypto이면 코인 취급
'is_coin': cat == 'crypto',

# 가격 후보 — ticker가 -USD로 끝나면 코인
is_crypto_price = ticker.endswith('-USD')
'is_coin': is_crypto_price,

# 라운드-로빈 선택 시 coin_count 추적
coin_count = 0
for cat in round_robin_order:
    for idx, c in enumerate(candidates_in_cat):
        if c.get('is_coin') and coin_count >= 1:
            continue  # 두 번째 코인 스킵
        pick = candidates_in_cat.pop(idx)
        break
    if pick and pick.get('is_coin'):
        coin_count += 1
```

### 3. 스포츠 경기 결과 허용 유형 명시

```
[SPORTS — MATCH QUESTIONS]
- WORD CHOICE — avoid "draw" as a verb (mistranslated as "lottery" in Korean)
  ❌ FORBIDDEN: "Will Team A and Team B draw?"
  ✅ CORRECT  : "Will Team A and Team B finish tied (0-0 or equal score)?"
- ALLOWED question types:
  ✅ Win/loss result  : "Will Arsenal win against..."
  ✅ Exact score      : "Will the match end 2-1?"
  ✅ Total goals      : "Will there be 3 or more total goals?"
  ✅ First scorer     : "Will [player] score the first goal?"
```

---

## Gemini 프롬프트 신규/강화 규칙 요약

### [ECONOMY NEWS — ALREADY-RELEASED DATA] (신규)
```
- GDP, CPI, trade balance 등 이미 발표된 지표 기사 → 단기 수정 불가
- 대신: GBP/USD, FTSE 100, bond yield 등 시장 반응 질문으로 유도
- 24-48h 내 측정 가능한 시장 지표를 threshold 질문으로 활용
```

### [POLITICS / ELECTION QUESTIONS] (신규)
```
검증 가능한 4가지 패턴만 허용:
1. PATTERN 1 — POLL NUMBER: 특정 조사기관(YouGov, Ipsos 등) 수치
2. PATTERN 2 — LEGAL/CONSTITUTIONAL DECISION: 법원 판결, 실격
3. PATTERN 3 — PARLIAMENTARY VOTE: 입법 기록 확인 가능 투표
4. PATTERN 4 — NAMED PERSON'S SPECIFIC ACTION: 사임, 임명, 해임

금지: "take steps", "gain momentum", "stabilize", "condemn", "formally reverse"
```

### [NAMED ENTITY REQUIRED] (신규)
```
❌ FORBIDDEN: "Will any country condemn...?" (193개국 중 하나면 YES → 불확실성 0)
❌ FORBIDDEN: "Will any official comment on...?"
✅ GOOD: "Will the U.S. State Department formally sanction RSF leadership by X?"
✅ GOOD: "Will the African Union convene an emergency summit on Sudan by X?"
→ 모든 질문 주어는 단일 named entity (특정 국가/인물/기관)
```

### [TECH/KEYNOTE QUESTIONS] (신규)
```
❌ FORBIDDEN: "Will X be mentioned/discussed/referenced/highlighted in the keynote?"
❌ FORBIDDEN: "Will the keynote explicitly mention X?"
✅ ALLOWED: "Will NVIDIA officially announce a release date for Blackwell Ultra at GTC 2026?"
✅ ALLOWED: "Will NVDA stock price rise more than 5% within 24 hours after the GTC keynote?"
→ 단일 press release / product page / stock price로 검증 가능한 결과만 허용
```

### [ATTACK/TERRORISM/CONFLICT EVENTS] (강화)
```
❌ FORBIDDEN: 사상자수 질문 (already in source → not uncertain)
❌ FORBIDDEN: "Will [govt] release a follow-up statement?" (tweet으로도 충족 → unmeasurable)
❌ FORBIDDEN: "Will [entity] announce new sanctions against [unnamed actors]?"
✅ ALLOWED: 구체적 법률명/기관명/개인명 포함한 escalation 질문
```

### [statement/announce 추가 금지 패턴] (강화)
```
❌ "Will [entity] release a follow-up/additional official statement about X?"
❌ "Will [entity] announce a new/specific [policy/funding/initiative] for X?"
❌ "Will [entity] issue a formal press release announcing [new sanctions/policy]?"
❌ "Will [entity] announce new sanctions against [unnamed entities / groups / actors]?"
```

---

## 관련 커밋

| 커밋 | 내용 |
|------|------|
| `8c19e92` | 카테고리 최대 허용치 count 비례 동적 계산 (economy 2개 중복 방지) |
| `2e7b35c` | economy 내 코인(crypto) 최대 1개 제한 — 코인 2개 동시 출제 방지 |
| `a56aa99` | 이미 발표된 경제 데이터 기사 → 시장반응 질문으로 유도 |
| `8ae63ae` | 스포츠 문제에서 'draw' 동사 사용 금지 → 번역 오류 방지 |
| `1992fa5` | 관련 기사 보기 폰트 0.6em → 0.9em |

---

## 알려진 잔여 이슈

- **Article-specific 미준수 (드물게)**: Gemini가 간혹 지정 기사와 다른 질문 생성 → `⚠️ MUST be about THIS topic` 규칙으로 완화
- **카테고리 오분류 (드물게)**: 원유 가격 질문이 "tech" 분류되는 경우
- **컴패니언 규칙 누적**: 프롬프트 길이 증가 → 향후 Article-First 전환으로 컨텍스트 최적화 예정
