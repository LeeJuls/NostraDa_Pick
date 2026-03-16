# NostraDa Pick - 채점 시스템 복구 + UI 정답 표시 + 출제 품질 개선 v3.0 히스토리
**버전**: v3.0 | **날짜**: 2026-03-16 | **작업자**: Claude (Backend + Frontend Agent)

---

## 배경 및 문제 정의

출제는 정상 동작하나 채점(resolver)이 한 번도 실행된 적 없어 104개 이슈 전부 OPEN 상태로 누적.
프론트엔드에서 정답 발표 후 어느 쪽이 정답인지 표시 없음.
날짜만 다른 동일 질문이 반복 출제되는 중복 문제도 지속.

**발견된 문제:**

| # | 문제 | 원인 |
|---|------|------|
| 1 | **채점 완전 불능** | `resolver_service.py`가 `gemini-2.0-flash-lite` 하드코딩 — 이 모델 free tier daily limit = 0 → 항상 429 |
| 2 | **104개 OPEN 누적** | Resolver 2x/day 실행으로 backlog 소화 불가 |
| 3 | **날짜만 다른 중복** | 같은 기사가 매 4h run마다 재선택 → 날짜만 다른 동일 질문 2~3개 생성 |
| 4 | **배치 내 중복** | 같은 run 내 생성된 이슈끼리 dedup 없음 |
| 5 | **"공식 발표할 예정" 질문 지속** | BANNED PATTERNS에 deployment/dispatch announcement 미포함 |
| 6 | **정답 미표시** | RESOLVED 이슈에서 어느 옵션이 정답인지 UI에 표시 없음 |
| 7 | **마감됨 이슈 무한 누적** | API가 OPEN 이슈 전체 반환, 기한 필터 없음 |

---

## 핵심 결정 사항

| # | 결정 | 근거 |
|---|------|------|
| 1 | Resolver 모델 FALLBACK_MODELS 방식으로 교체 | generator와 동일한 모델 로테이션 — gemini-3.1-flash-lite-preview 우선 |
| 2 | 48h 초과 이슈 → 배치 Gemini 호출 (50개/청크) | 104개 누적 이슈를 2~3회 API 호출로 한꺼번에 처리 |
| 3 | 48h 이내 이슈 → 기존 개별 채점 유지 | 정확도 우선 |
| 4 | Resolver GitHub Actions 빈도 2x → 6x/day | 마감 후 최대 4시간 내 채점 보장 |
| 5 | source URL 중복 체크 추가 | OPEN 이슈의 source URL과 후보 URL 비교 → 동일 기사 재출제 차단 |
| 6 | 배치 내 실시간 dedup | 선택된 후보를 즉시 dedup 목록에 추가 |
| 7 | _normalize_title() — 날짜/숫자 제거 후 의미 단어만 비교 | "발표 by 2026-03-15" vs "발표 by 2026-03-16" → 동일 취급 |
| 8 | RESOLVED 카드에 정답 즉시 표시 | `correct_option_id` 기반 ✅ 버튼 강조, 오답 투명도 0.3 |
| 9 | 투표자 정답/오답 구분 표시 | 정답 맞힘: 🏆, 틀림: ❌ |
| 10 | "공식 발표" 질문 금지 추가 | "Will [govt] officially announce deployment of X?" → 발표가 아닌 실제 이벤트로 유도 |
| 11 | 마감됨 이슈 48h 후 자동 숨김 | close_at 기준 48h 지난 OPEN 이슈 API 응답에서 제외 |
| 12 | RESOLVED 이슈 노출 24h → 48h | 정답 확인 시간 여유 확보 |

---

## 변경 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `services/resolver_service.py` | 전면 재작성 — FALLBACK_MODELS 방식, 배치 채점(_resolve_batch), 개별 채점(_resolve_single_issue), 공통 로직 분리(_apply_resolution, _call_gemini_with_retry) |
| `services/gemini_service.py` | source URL dedup, 배치 내 실시간 dedup, _normalize_title() 날짜/숫자 정규화, "공식 발표" 금지 프롬프트 추가 |
| `static/js/app.js` | RESOLVED 카드 정답 표시, checkVotedIssues 정답/오답 구분 |
| `routes/api.py` | OPEN 이슈 48h 필터, RESOLVED 노출 24h→48h |
| `.github/workflows/issue_resolver.yml` | cron 2x/day → 6x/day |

---

## 코드 변경 핵심 부분

### 1. Resolver 모델 교체 (채점 복구의 핵심)

```python
# 변경 전 — 항상 실패
self.model = genai.GenerativeModel('gemini-2.0-flash-lite')  # free tier limit: 0

# 변경 후 — generator와 동일한 FALLBACK_MODELS
from services.gemini_service import FALLBACK_MODELS

def _setup_model(self):
    model_name = FALLBACK_MODELS[self.current_model_idx % len(FALLBACK_MODELS)]
    genai.configure(api_key=self.api_keys[self.current_key_idx])
    self.model = genai.GenerativeModel(model_name)
    # gemini-3.1-flash-lite-preview 우선 (500 RPD free tier)
```

### 2. 배치 채점 (_resolve_batch)

```python
MAX_AGE_HOURS = 48   # 이 이상 된 이슈는 배치로 처리
BATCH_CHUNK_SIZE = 50

# 50개씩 하나의 프롬프트에 묶어서 Gemini 1회 호출
prompt = (
    "You are a factual judge. For each prediction question below, "
    "answer Yes or No based on real-world events up to the close date.\n\n"
    + "\n".join(lines)
    + "\n\nReturn ONLY a JSON array: "
      '[{"index": 0, "answer": "Yes"}, ...]\n'
      f"Include ALL {len(chunk)} items."
)
# 104개 → 2회 Gemini 호출로 처리
```

### 3. 날짜/숫자 정규화 dedup

```python
def _normalize_title(text: str) -> str:
    t = text.lower()
    t = re.sub(r'\d{4}-\d{2}-\d{2}', ' ', t)   # 2026-03-15 제거
    t = re.sub(r'\d{1,2}:\d{2}', ' ', t)         # 16:36 제거
    t = re.sub(r'\$[\d,]+\.?\d*', ' ', t)         # $73,500 제거
    t = re.sub(r'\b\d+\.?\d*\s*%?\b', ' ', t)    # 숫자/% 제거
    t = re.sub(r'[^a-z ]', ' ', t)
    return t
# "호르무즈 배치 발표 by 2026-03-15 16:36" == "호르무즈 배치 발표 by 2026-03-16 16:00" → 중복 차단
```

### 4. UI 정답 표시 (app.js)

```javascript
// RESOLVED 카드 렌더링 시
if (isResolved && issue.correct_option_id) {
    const correctBtn = card.querySelector(`.bet-btn[data-option-id="${issue.correct_option_id}"]`);
    const wrongBtn   = card.querySelector(`.bet-btn:not([data-option-id="${issue.correct_option_id}"])`);
    if (correctBtn) {
        correctBtn.innerHTML = `✅ ${correctBtn.textContent}`;
        correctBtn.style.border  = '3px solid #28a745';
        correctBtn.style.opacity = '1';
    }
    if (wrongBtn) wrongBtn.style.opacity = '0.3';
}

// 투표자 정답/오답 구분
const isWinner = String(optionId) === String(correctOptionId);
b.innerHTML = isWinner ? `🏆 ${cleanText}` : `❌ ${cleanText}`;
b.style.border = isWinner ? '4px solid #28a745' : '4px solid #dc3545';
```

### 5. API 이슈 숨김 필터

```python
# 변경 전
open_resp = supabase.table('issues').select('*').eq('status', 'OPEN').execute()  # 전체 반환

# 변경 후
open_hide_threshold = (now - timedelta(hours=48)).isoformat()
open_resp = supabase.table('issues').select('*').eq('status', 'OPEN').gte('close_at', open_hide_threshold).execute()
# close_at이 48h 이상 지난 마감됨 이슈는 목록에서 자동 제거

resolved_hide_threshold = (now - timedelta(hours=48)).isoformat()
resolved_resp = supabase.table('issues').select('*').eq('status', 'RESOLVED').gte('resolved_at', resolved_hide_threshold).execute()
# RESOLVED 노출 24h → 48h
```

---

## Resolver 실행 결과 (2026-03-16 최초 정상 채점)

```
📋 Found 104 expired issue(s) to resolve.
  → 48h 초과(배치): 32개 | 48h 이내(개별): 72개
📦 Batch resolving 32 old issues (50/chunk)...
  Chunk [1~32/32]
  ✅ 32개 배치 처리 완료
🧐 [1/72] ~ [72/72] 개별 처리 완료
[run_resolve] Done.
```

DB 결과: OPEN 107개 → **RESOLVED 104개 + OPEN 3개** (처리 전 미마감)

---

## 관련 커밋

| 커밋 | 내용 |
|------|------|
| `676105f` | fix: 채점 불능 + 중복 문제 수정 (resolver FALLBACK_MODELS, source URL dedup, 배치 채점, Actions 6x/day) |
| `0262866` | feat: RESOLVED 정답 표시 + 날짜 dedup + 공식발표 금지 강화 |
| `9722317` | fix: 마감됨 이슈 48h 후 자동 숨김 + RESOLVED 노출 24h→48h |

---

## 잔여 이슈 / 다음 단계

- issue_generation_flow2.html 업데이트 (현재 아키텍처 반영)
- RESOLVED 카드 UI 디자인 추가 개선 여지 (정답 뱃지 별도 스타일)
- Resolver rate limit 추적: 하루 6회 × (fresh 이슈 수) 기준 quota 모니터링 필요
