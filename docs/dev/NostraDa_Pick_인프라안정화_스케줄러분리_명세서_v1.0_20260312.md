# [개발 명세서 v1.0] 인프라 안정화 — GitHub Actions 스케줄러 분리 및 로컬 테스트 시스템

**날짜:** 2026-03-12
**작성:** PM
**상태:** ✅ 에이전트 리뷰 완료 — 개발 착수 가능

---

## 1. 핵심 결정 사항

| # | 항목 | 결정 | 이유 |
|---|------|------|------|
| 1 | **스케줄러 위치** | Flask APScheduler → GitHub Actions 분리 | Render Free sleep 시 APScheduler도 중단 → 서비스 사실상 중단 |
| 2 | **GitHub Actions 실행 방식** | Render 서버 HTTP 호출이 아닌, 코드 체크아웃 후 Python 직접 실행 | 서버 sleep 여부와 무관하게 독립 실행 보장 |
| 3 | **APScheduler 처리** | `DISABLE_SCHEDULER=true` 환경변수로 조건부 비활성화 | 로컬 개발 시 APScheduler 유지, Render 배포 시 비활성 |
| 4 | **로컬 테스트** | `GEMINI_USE_FIXTURE` 환경변수로 fixture 캐시 제어 | API 1회 호출 후 응답 저장 → 반복 테스트 시 API 호출 0 |
| 5 | **Resolver 프롬프트** | `created_at` + `close_at` 컨텍스트 추가 | "이번 주", "내일" 등 시간 상대어 오판 방지 |
| 6 | **pip 캐시** | GitHub Actions에 `actions/cache` 적용 | `grpcio` 등 빌드 시간 긴 패키지로 인한 실행 지연 방지 |
| 7 | **fixture gitignore** | `tests/fixtures/*.json` gitignore 처리 | 실제 뉴스 기반 Gemini 응답 → 커밋 불필요 |

---

## 2. 기술 스택 변경

| 구분 | 기존 | 변경 후 | 비고 |
|------|------|---------|------|
| 스케줄러 | Flask APScheduler (BackgroundScheduler) | **GitHub Actions cron** | 서버 독립적 실행 |
| 로컬 테스트 | 매번 Gemini API 직접 호출 | **fixture 캐시 시스템** | API 낭비 방지 |
| 배포 환경변수 | 없음 | `DISABLE_SCHEDULER=true` 추가 | APScheduler 비활성화 |

---

## 3. 프로젝트 구조 변경

```
nostrada_pick/
├── app.py                          # ✏️ APScheduler 조건부 비활성화
├── config.py
├── requirements.txt
├── render.yaml                     # ✏️ DISABLE_SCHEDULER=true 추가
├── .env                            # ✏️ DISABLE_SCHEDULER, GEMINI_USE_FIXTURE 추가
├── .gitignore                      # ✏️ tests/fixtures/*.json 추가
│
├── .github/
│   └── workflows/
│       ├── issue_generator.yml     # 🆕 출제 스케줄러 (UTC 0,4,8,12,16,20)
│       └── issue_resolver.yml      # 🆕 판정 스케줄러 (UTC 0,12)
│
├── scripts/
│   ├── run_generate.py             # 🆕 GitHub Actions 출제 runner
│   └── run_resolve.py              # 🆕 GitHub Actions 판정 runner
│
├── services/
│   ├── gemini_service.py           # ✏️ fixture 캐시 로직 추가
│   ├── resolver_service.py         # ✏️ 프롬프트에 날짜 컨텍스트 추가
│   └── supabase_client.py
│
├── tests/
│   └── fixtures/
│       ├── .gitkeep                # 🆕 디렉토리 유지용 (커밋됨)
│       ├── generated_issues.json   # 🆕 출제 응답 캐시 (gitignore)
│       └── resolved_issue.json     # 🆕 판정 응답 캐시 (gitignore)
│
├── routes/
├── templates/
└── static/
```

> ✏️ = 수정  /  🆕 = 신규 생성

---

## 4. GitHub Actions 워크플로우

### 4.1 issue_generator.yml

```yaml
# .github/workflows/issue_generator.yml
name: Issue Generator

on:
  schedule:
    - cron: '0 0,4,8,12,16,20 * * *'   # UTC 0,4,8,12,16,20시 (하루 6회)
  workflow_dispatch:                      # 수동 트리거 지원

jobs:
  generate:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Cache pip dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}
          restore-keys: |
            ${{ runner.os }}-pip-

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run issue generator
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          GEMINI_API_KEYS: ${{ secrets.GEMINI_API_KEYS }}
          FLASK_ENV: production
        run: python scripts/run_generate.py
```

### 4.2 issue_resolver.yml

```yaml
# .github/workflows/issue_resolver.yml
name: Issue Resolver

on:
  schedule:
    - cron: '30 0,12 * * *'    # UTC 0:30, 12:30 (하루 2회, generate와 30분 간격)
  workflow_dispatch:

jobs:
  resolve:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Cache pip dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}
          restore-keys: |
            ${{ runner.os }}-pip-

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run issue resolver
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          GEMINI_API_KEYS: ${{ secrets.GEMINI_API_KEYS }}
          FLASK_ENV: production
        run: python scripts/run_resolve.py
```

> **[T-8 대응]** resolver cron을 `0:30`, `12:30`으로 설정하여 generator(`0:00`, `12:00`)와 30분 간격 부여 → 동시 실행 DB 충돌 방지

---

## 5. Runner 스크립트

### 5.1 scripts/run_generate.py

```python
# scripts/run_generate.py
"""
GitHub Actions 전용 이슈 출제 runner.
환경변수: SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEYS
"""
import sys
import os

# 프로젝트 루트를 Python path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gemini_service import gemini_service

def main():
    print("[Generator] Starting issue generation...")
    try:
        issues = gemini_service.generate_trending_issues(count=1)
        if issues:
            success = gemini_service.save_issues_to_db(issues)
            if success:
                print(f"[Generator] ✅ Successfully generated and saved {len(issues)} issue(s).")
            else:
                print("[Generator] ❌ Failed to save issues to DB.")
                sys.exit(1)
        else:
            print("[Generator] ⚠️ No issues generated (API returned empty).")
            sys.exit(1)
    except Exception as e:
        print(f"[Generator] ❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
```

### 5.2 scripts/run_resolve.py

```python
# scripts/run_resolve.py
"""
GitHub Actions 전용 이슈 판정 runner.
환경변수: SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEYS
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.resolver_service import resolver_service

def main():
    print("[Resolver] Starting issue resolution...")
    try:
        resolver_service.resolve_expired_issues()
        print("[Resolver] ✅ Resolution cycle complete.")
    except Exception as e:
        print(f"[Resolver] ❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
```

---

## 6. 코드 변경 상세

### 6.1 app.py — APScheduler 조건부 비활성화

```python
# app.py (변경 전)
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    scheduler = BackgroundScheduler(daemon=True)
    ...
    scheduler.start()

# app.py (변경 후)
DISABLE_SCHEDULER = os.environ.get('DISABLE_SCHEDULER', 'false').lower() == 'true'

if not DISABLE_SCHEDULER:
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(func=scheduled_generate, trigger="cron",
                          hour="0,4,8,12,16,20", id="issue_gen_job")
        scheduler.add_job(func=scheduled_resolve, trigger="cron",
                          hour="0,12", id="issue_res_job")
        scheduler.start()
        print("✅ APScheduler started.")
else:
    print("ℹ️ APScheduler disabled (DISABLE_SCHEDULER=true). Using GitHub Actions.")
```

### 6.2 services/gemini_service.py — fixture 캐시 로직

```python
# generate_trending_issues() 메서드 상단에 추가

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tests', 'fixtures')
FIXTURE_FILE = os.path.join(FIXTURE_DIR, 'generated_issues.json')

def generate_trending_issues(self, count: int = 3):
    use_fixture = os.environ.get('GEMINI_USE_FIXTURE', '').lower() == 'true'

    if use_fixture:
        # fixture 파일 존재 + 데이터 있음 → fixture 사용
        if os.path.exists(FIXTURE_FILE):
            with open(FIXTURE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data:
                print(f"💡 [FIXTURE] Loaded {len(data)} issue(s) from fixture. No API call.")
                return data[:count]
        # fixture 없거나 비어있음 → 경고 후 실제 API 호출 + 저장
        print("⚠️ [FIXTURE] Fixture file missing or empty. Calling API once and saving...")

    # 실제 API 호출 (기존 로직)
    issues_data = self._call_gemini_api(count)

    # GEMINI_USE_FIXTURE=false 이거나 fixture 없어서 API 호출한 경우 → 저장
    if issues_data and os.environ.get('GEMINI_USE_FIXTURE', '').lower() != '':
        os.makedirs(FIXTURE_DIR, exist_ok=True)
        with open(FIXTURE_FILE, 'w', encoding='utf-8') as f:
            json.dump(issues_data, f, ensure_ascii=False, indent=2)
        print(f"💾 [FIXTURE] Saved {len(issues_data)} issue(s) to fixture.")

    return issues_data
```

### 6.3 services/resolver_service.py — 프롬프트 날짜 컨텍스트

```python
# _resolve_single_issue() 내 prompt 변경

# 변경 전
prompt = f"""
Prediction Issue: "{issue['title']}"
Category: {issue['category']}

Is this statement true based on real-world events that have occurred up to now?
Provide the answer as 'Yes' or 'No' and a brief reason.
Format output as valid JSON: {{"answer": "Yes" or "No", "reason": "..."}}
"""

# 변경 후
prompt = f"""
Prediction Issue: "{issue['title']}"
Category: {issue['category']}
This issue was created at {issue['created_at']} (UTC) and the voting closed at {issue['close_at']} (UTC).

IMPORTANT: "this week", "tomorrow", "today" in the question refers to the period
WHEN THE ISSUE WAS CREATED ({issue['created_at'][:10]}), not the current time.

Based on real-world events that occurred up to the close time ({issue['close_at'][:10]}),
was this prediction correct?
Answer with Yes or No, and provide a brief reason.
Format output as valid JSON: {{"answer": "Yes" or "No", "reason": "..."}}
"""
```

---

## 7. 환경변수 변경

### 7.1 .env (로컬 개발용 추가)

```bash
# .env 추가 항목

# 스케줄러 제어
# false(기본): APScheduler 활성 (로컬 개발)
# true: APScheduler 비활성 (Render 배포 시 사용)
DISABLE_SCHEDULER=false

# Gemini fixture 캐시 제어
# true: fixture 파일 사용 (API 호출 없음) ← 로컬 기본값 권장
# false: 실제 API 1회 호출 + fixture 저장
# 미설정: 항상 실제 API 호출 (production 동작)
GEMINI_USE_FIXTURE=true
```

### 7.2 render.yaml 변경

```yaml
# render.yaml (envVars에 추가)
- key: DISABLE_SCHEDULER
  value: "true"
```

---

## 8. .gitignore 변경

```
# 기존 항목 유지 후 아래 추가

# Gemini fixture 캐시 (실제 뉴스 데이터 포함 가능 — 커밋 불필요)
tests/fixtures/*.json
```

---

## 9. GitHub Secrets 등록 (1회 작업)

GitHub Repo → Settings → Secrets and variables → Actions → New repository secret

| Secret 키 | 값 출처 |
|-----------|--------|
| `SUPABASE_URL` | Supabase 프로젝트 Settings > API > URL |
| `SUPABASE_KEY` | Supabase 프로젝트 Settings > API > service_role key |
| `GEMINI_API_KEYS` | Google AI Studio (콤마 구분 다중 키 지원) |

---

## 10. Phase별 개발 계획

### Phase 1 — 스케줄러 분리 (핵심)
| # | 작업 | 파일 | 담당 |
|---|------|------|------|
| 1-1 | APScheduler 조건부 비활성화 | `app.py` | Back |
| 1-2 | `scripts/` 디렉토리 생성 | — | Back |
| 1-3 | `scripts/run_generate.py` 작성 | 신규 | Back |
| 1-4 | `scripts/run_resolve.py` 작성 | 신규 | Back |
| 1-5 | `issue_generator.yml` 작성 | 신규 | Back |
| 1-6 | `issue_resolver.yml` 작성 | 신규 | Back |
| 1-7 | `render.yaml`에 `DISABLE_SCHEDULER=true` 추가 | `render.yaml` | Back |
| 1-8 | `.env`에 `DISABLE_SCHEDULER=false` 추가 | `.env` | Back |

**QA 체크포인트:**
- [ ] 로컬: `DISABLE_SCHEDULER=false` → APScheduler 기동 로그 확인
- [ ] 로컬: `DISABLE_SCHEDULER=true` → APScheduler 기동 로그 없음 확인 (T-7)
- [ ] `python scripts/run_generate.py` 로컬 실행 → DB에 이슈 저장 확인 (T-1)
- [ ] `python scripts/run_resolve.py` 로컬 실행 → 마감 이슈 판정 확인 (T-2)

### Phase 2 — Resolver 프롬프트 수정
| # | 작업 | 파일 | 담당 |
|---|------|------|------|
| 2-1 | `_resolve_single_issue()` 프롬프트 수정 | `resolver_service.py` | Back |

**QA 체크포인트:**
- [ ] "이번 주" 포함 이슈 판정 시 `created_at` 기준으로 Gemini에 전달되는지 로그 확인 (T-6)

### Phase 3 — Fixture 캐시 시스템
| # | 작업 | 파일 | 담당 |
|---|------|------|------|
| 3-1 | `tests/fixtures/` 디렉토리 생성 | — | Back |
| 3-2 | `tests/fixtures/.gitkeep` 생성 | 신규 | Back |
| 3-3 | `gemini_service.py`에 fixture 로직 추가 | `gemini_service.py` | Back |
| 3-4 | `.env`에 `GEMINI_USE_FIXTURE=true` 추가 | `.env` | Back |
| 3-5 | `.gitignore`에 `tests/fixtures/*.json` 추가 | `.gitignore` | Back |

**QA 체크포인트:**
- [ ] `GEMINI_USE_FIXTURE=true` + fixture 있음 → "Loaded from fixture" 로그, API 미호출 (T-3)
- [ ] `GEMINI_USE_FIXTURE=false` → API 1회 호출 + fixture 파일 생성 (T-4)
- [ ] `GEMINI_USE_FIXTURE=true` + fixture 없음 → 경고 로그 + API 호출 + fixture 저장 (T-9)

### Phase 4 — GitHub Actions 배포 및 최종 검증
| # | 작업 | 담당 |
|---|------|------|
| 4-1 | GitHub Secrets 등록 (SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEYS) | 사용자 직접 |
| 4-2 | `issue_generator.yml` 수동 트리거 테스트 | QA |
| 4-3 | `issue_resolver.yml` 수동 트리거 테스트 | QA |
| 4-4 | Render 배포 후 APScheduler 비활성 확인 | QA |

**QA 체크포인트:**
- [ ] GitHub Actions `workflow_dispatch`로 수동 트리거 → 성공 (T-1, T-2)
- [ ] Render 서버 sleep 상태에서 Actions 트리거 → 서버 무관하게 정상 실행 (T-5)
- [ ] UTC 0시 generate + 0시30분 resolve 순차 실행 → DB 충돌 없음 (T-8)

---

## 11. 테스트 시나리오

| # | 시나리오 | 실행 방법 | 기대 결과 |
|---|----------|-----------|-----------|
| T-1 | GitHub Actions 출제 수동 트리거 | Actions 탭 → issue_generator → Run workflow | Supabase issues 테이블에 새 이슈 저장 |
| T-2 | GitHub Actions 판정 수동 트리거 | Actions 탭 → issue_resolver → Run workflow | 마감된 OPEN 이슈 → RESOLVED 변경 |
| T-3 | fixture 사용 출제 테스트 | `GEMINI_USE_FIXTURE=true python scripts/run_generate.py` | "Loaded from fixture" 로그, API 미호출 |
| T-4 | fixture 갱신 | `GEMINI_USE_FIXTURE=false python scripts/run_generate.py` | API 1회 호출 + `tests/fixtures/generated_issues.json` 생성 |
| T-5 | 서버 sleep 중 Actions 실행 | Render 서버 수동 suspend 후 Actions 트리거 | 정상 실행 |
| T-6 | 시간 상대어 이슈 판정 | "이번 주" 포함 이슈 수동 판정 | `created_at` 날짜가 프롬프트에 포함된 것 로그 확인 |
| T-7 | APScheduler 비활성 확인 | `DISABLE_SCHEDULER=true` → `python app.py` | "APScheduler disabled" 로그, scheduler 기동 없음 |
| T-8 | generate + resolve 동시 실행 | 두 workflow 동시에 수동 트리거 | DB 중복/충돌 없이 각각 정상 완료 |
| T-9 | fixture 없을 때 `true` 모드 | fixture 삭제 후 `GEMINI_USE_FIXTURE=true python scripts/run_generate.py` | 경고 로그 → API 1회 호출 → fixture 생성 |

---

## 12. 에이전트 리뷰 결과

| 에이전트 | 판정 | 주요 반영 사항 |
|---------|------|-------------|
| PM | ✅ 승인 | fixture `.gitignore` 처리 (섹션 8), 유틸 스크립트 이동은 이번 범위 외 |
| Backend | ✅ 승인 | pip 캐시 설정 (섹션 4), fixture fallback 처리 (섹션 6.2), resolver 30분 지연 (섹션 4.2) |
| Frontend | ✅ 승인 | 프론트 변경 없음. 스마트 폴링 확인은 T-1에서 병행 |
| QA | ✅ 승인 | T-7, T-8, T-9 시나리오 추가 (섹션 11) |
