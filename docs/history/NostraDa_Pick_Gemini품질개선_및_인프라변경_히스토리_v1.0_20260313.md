# NostraDa Pick - Gemini 품질 개선 & 인프라 변경 히스토리
**버전**: v1.0 | **날짜**: 2026-03-13 | **작업자**: Claude (Backend Agent)

---

## 배경 및 문제 정의

Gemini AI가 생성하는 예측 문제에서 복수의 품질 이슈가 누적됐고, Keep Alive 방식의 신뢰도 문제도 동시에 발생.

**Gemini 출제 품질 문제:**
1. **과거 이벤트 출제** — 학습 데이터 기반으로 이미 종료된 2025년 이벤트를 미래로 착각해 출제
2. **시간대 오류** — 서버가 KST 환경 → `datetime.now()` = KST+9 → close_at이 실제보다 9시간 늦게 저장
3. **모호한 시간 표현** — "내일", "오늘 밤", "by end of session" → UTC 기준 불명확
4. **이벤트 판정 순서 오류** — ECB 발표가 13:15 UTC인데 투표 마감이 14:35 UTC → 답 공개 후에도 투표 가능
5. **5일 뒤 이벤트 출제** — UCL 경기가 실제로는 5일 뒤인데 48시간 이내로 착각
6. **소수점 점수** — "1.5골 이상" 등 스포츠에서 불가능한 소수점 점수 사용
7. **엔터테인먼트 오정보** — 이미 공개된 콘텐츠(오징어 게임 시즌2 등)를 미발표로 인식해 출제
8. **카테고리 편중** — 4문제 중 economy 3개 등 다양성 부족
9. **스포츠 일정 추측** — 없는 UCL 경기를 있다고 생성

**Keep Alive 문제:**
- GitHub Actions cron `*/10 * * * *` 설정에도 실제 실행 간격이 20~43분으로 지연
- 15분 이상 빈 구간 발생 → Render Sleep → 서비스 중단

---

## 핵심 결정 사항

| # | 결정 | 근거 |
|---|------|------|
| 1 | `datetime.now()` → `datetime.now(timezone.utc)` 전면 교체 | 서버 KST 환경에서 9시간 오차 발생 근본 원인 제거 |
| 2 | UTC 시간 형식 `suffix` → `prefix` 변경 | `2026-03-12 18:30 UTC` → `(UTC+0) 2026-03-12 18:30` |
| 3 | 한국어 후처리: `(UTC+0)` → `UTC 0시 기준` | 번역 시 자연스러운 한국어 표현 |
| 4 | RESOLVABLE BY CLOSE TIME 규칙 추가 | 이벤트 발생 시각이 close_at 이전이면 출제 금지 → 부정 투표 방지 |
| 5 | 48시간 이내 + 가격예측 24시간 이내 제한 | 너무 먼 미래 이벤트 방지, 리텐션 주기(4시간) 유지 |
| 6 | 구체적 실체 명시 강제 | "official press release" 같은 모호한 표현 금지 |
| 7 | 스포츠 점수 정수만 허용 | 실제 스포츠에 소수점 점수 없음 |
| 8 | 엔터테인먼트 출시/발표 금지 | Gemini 학습 데이터 한계 → 이미 나온 콘텐츠 재출제 방지 |
| 9 | 카테고리 다양성 최대 2개 (프롬프트 + 코드 이중 검증) | 동일 카테고리 편중 방지 |
| 10 | 스포츠 API 연동 (football-data.org + api-sports.io) | 경기 일정 추측 금지, 실제 일정만 사용 |
| 11 | GitHub Actions Keep Alive → cron-job.org 교체 | GitHub Actions cron 지연/스킵 문제 근본 해결 |

---

## 변경 파일 목록

### 수정 파일

| 파일 | 변경 내용 |
|------|-----------|
| `services/gemini_service.py` | UTC timezone 전면 적용, 프롬프트 규칙 9가지 추가, 카테고리 검증 로직, 스포츠 API 연동, 한국어 후처리 |
| `services/resolver_service.py` | `datetime.now()` → `datetime.now(timezone.utc)`, `tools='google_search_retrieval'` 제거 (SDK 0.8.3 호환) |
| `services/sports_schedule_service.py` | football-data.org(축구) + api-sports.io(NBA/MLB) 경기 일정 조회 |
| `routes/api.py` | UTC timezone 통일 |
| `static/js/app.js` | 리더보드 → 예언자 순위 (7개 언어), UTC 실시간 시계, 섹션 헤더 대시 단축, refresh_info 수정 |
| `templates/index.html` | UTC 시계 요소 추가, refresh_info 기본값 수정 |
| `config.py` | `FOOTBALL_DATA_API_KEY`, `API_SPORTS_KEY` 환경변수 추가 |

### 삭제 파일

| 파일 | 이유 |
|------|------|
| `.github/workflows/keep_alive.yml` | cron-job.org로 대체 |

### 신규 외부 서비스

| 서비스 | 역할 | 설정 |
|--------|------|------|
| cron-job.org | Render Keep Alive ping | 10분 간격, User-Agent 헤더 설정 |
| football-data.org | 축구 경기 일정 API | `FOOTBALL_DATA_API_KEY` 환경변수 |
| api-sports.io | NBA/MLB 경기 일정 API | `API_SPORTS_KEY` 환경변수 |

---

## Gemini 프롬프트 주요 규칙 변경

```
[변경 전]
- 날짜만 전달 (Today is 2026-03-12)
- 상대적 시간 표현 허용
- 스포츠 경기 일정 추측 허용
- 시간 형식: "2026-03-12 18:30 UTC" (suffix)

[변경 후]
- 현재 UTC 시각 + 마감 UTC 시각 전달
- ABSOLUTE UTC TIME 강제: "(UTC+0) 2026-03-12 18:30" (prefix)
- FUTURE ONLY: 2025년 이전 이벤트 금지
- RESOLVABLE BY CLOSE TIME: 투표 마감 전 결과 공개 금지
- WITHIN 48 HOURS: 이벤트 최대 48시간 이내
- PRICE/MARKET 24H: 가격 예측은 24시간 이내
- SPECIFIC ENTITIES: 회사명, 국가명 등 구체적 명시 필수
- SPORTS INTEGERS: 정수 점수만 허용
- NO RELEASE PREDICTIONS: 엔터테인먼트 출시/발표 금지
- CATEGORY MAX 2: 동일 카테고리 최대 2개
- SPORTS SCHEDULE ONLY: API 제공 경기 목록에서만 생성
```

---

## 코드 변경 핵심 부분

### UTC timezone 버그 수정

```python
# 변경 전 (버그 — KST+9 환경에서 9시간 오차)
close_at = (datetime.now() + timedelta(hours=4)).isoformat()

# 변경 후
from datetime import datetime, timezone, timedelta
close_at = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
```

### 카테고리 다양성 검증 (코드 레벨 안전장치)

```python
# JSON 파싱 후 동일 카테고리 최대 2개까지만
from collections import Counter
cat_count = Counter()
filtered = []
for issue in issues_data:
    cat = issue.get('category', '')
    if cat_count[cat] < 2:
        filtered.append(issue)
        cat_count[cat] += 1
issues_data = filtered
```

### 한국어 UTC 후처리

```python
if lang == 'ko':
    translated = translated.replace('(UTC+0)', 'UTC 0시 기준')
```

---

## Render 환경변수 추가 사항

| 키 | 값 |
|----|-----|
| `FOOTBALL_DATA_API_KEY` | football-data.org API 키 |
| `API_SPORTS_KEY` | api-sports.io API 키 |

---

## 관련 커밋

| 커밋 | 내용 |
|------|------|
| `01ecd58` | Keep Alive GitHub Actions 삭제 |
| `6053307` | Gemini 프롬프트 품질 규칙 3가지 추가 |
| `d4c2206` | resolver_service + api.py UTC 통일, tools 제거 |
| `7ecf72a` | NBA/MLB api-sports.io 연동 |
| `b3a462a` | football-data.org 축구 경기 일정 연동 |
| `07f1dd4` | 가격 예측 24h + UTC+0 기준 강화 |
| `519bcdb` | 실시간 데이터 없음 명시, KST→UTC 강제 |
| `b154995` | 구체적 실체 명시 강제 |
| `20651cf` | 이벤트 48시간 이내 제한 |
| `741108e` | 투표 마감 전 결과 공개 금지 |
| `e07368a` | 한국어 UTC 0시 기준 후처리 |
| `f25cd41` | 리더보드 → 예언자 순위 (7개 언어) |
| `68a6cfe` | UTC 시계 버그 수정 |
| `77b261e` | close_at timezone 버그 수정 |
