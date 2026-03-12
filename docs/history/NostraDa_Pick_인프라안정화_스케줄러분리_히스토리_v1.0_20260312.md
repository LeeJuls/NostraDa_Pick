# NostraDa Pick - 인프라 안정화 & 스케줄러 분리 히스토리
**버전**: v1.0 | **날짜**: 2026-03-12 | **작업자**: Claude (Backend Agent)

---

## 배경 및 문제 정의

Render Free 티어 서버를 사용 중으로, 15분 동안 요청이 없으면 서버가 sleep 상태로 진입한다.
APScheduler가 Flask 내부에서 동작하므로 sleep 중에는 스케줄러도 중단 → 이슈 출제/판정이 누락되는 치명적 장애가 발생하고 있었다.

추가로 두 가지 문제가 병존:
1. **Resolver 날짜 오판**: "이번 주", "내일" 같은 상대적 시간 표현이 포함된 이슈를 판정할 때 Gemini가 `created_at` 컨텍스트 없이 "현재 기준"으로 오판하는 문제
2. **로컬 API 낭비**: 개발/테스트 시마다 Gemini API를 실제 호출 → 불필요한 quota 소모

---

## 핵심 결정 사항

| # | 결정 | 근거 |
|---|------|------|
| 1 | APScheduler → GitHub Actions 완전 분리 | 서버 sleep과 완전히 독립, 신뢰도 높음 |
| 2 | `DISABLE_SCHEDULER` 환경변수 도입 | 로컬(false=APScheduler 활성) / Render(true=Actions 사용) 분기 |
| 3 | Resolver 프롬프트에 날짜 컨텍스트 명시 | `created_at`, `close_at` 삽입 + "이번 주"는 출제 당시 기준임을 명시 |
| 4 | `GEMINI_USE_FIXTURE` 환경변수 도입 | true → fixture JSON 재사용, false → API 1회 호출 후 fixture 저장 |
| 5 | resolver cron `30 0,12 * * *` 설정 | generator(0:00, 12:00)와 30분 간격으로 T-8 동시 실행 충돌 방지 |
| 6 | pip 캐시 적용 | grpcio 등 빌드 시간 긴 패키지 캐싱으로 Actions 실행 시간 단축 |

---

## 변경 파일 목록

### 수정 파일

| 파일 | 변경 내용 |
|------|-----------|
| `app.py` | `DISABLE_SCHEDULER` 환경변수 체크 후 APScheduler 조건부 기동 |
| `services/resolver_service.py` | 판정 프롬프트에 `created_at` / `close_at` 날짜 컨텍스트 추가 |
| `services/gemini_service.py` | `GEMINI_USE_FIXTURE` 분기 로직 추가, fixture 저장/로드 기능 구현 |
| `render.yaml` | `DISABLE_SCHEDULER=true` 환경변수 추가 |
| `.env` | `DISABLE_SCHEDULER=false`, `GEMINI_USE_FIXTURE=true` 추가 |
| `.gitignore` | `tests/fixtures/*.json` 제외 추가 |

### 신규 파일

| 파일 | 설명 |
|------|------|
| `scripts/run_generate.py` | GitHub Actions용 이슈 출제 실행 스크립트 |
| `scripts/run_resolve.py` | GitHub Actions용 이슈 판정 실행 스크립트 |
| `.github/workflows/issue_generator.yml` | 출제 Actions (UTC 0,4,8,12,16,20 + workflow_dispatch) |
| `.github/workflows/issue_resolver.yml` | 판정 Actions (UTC 0:30,12:30 + workflow_dispatch) |
| `tests/fixtures/.gitkeep` | fixture 디렉토리 유지용 |

---

## app.py 변경 내용

```python
# 변경 전
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(...)
    scheduler.start()

# 변경 후
DISABLE_SCHEDULER = os.environ.get('DISABLE_SCHEDULER', 'false').lower() == 'true'
if not DISABLE_SCHEDULER:
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(...)
        scheduler.start()
        print("✅ APScheduler started.")
else:
    print("ℹ️ APScheduler disabled (DISABLE_SCHEDULER=true). Using GitHub Actions.")
```

---

## resolver_service.py 프롬프트 변경 내용

```python
# 변경 전
prompt = f"""
Prediction Issue: "{issue['title']}"
Category: {issue['category']}
Is this statement true based on real-world events that have occurred up to now?
...
"""

# 변경 후
prompt = f"""
Prediction Issue: "{issue['title']}"
Category: {issue['category']}
This issue was created at {issue['created_at']} (UTC) and the voting closed at {issue['close_at']} (UTC).
IMPORTANT: Relative time expressions like "this week", "tomorrow", "today", "this month" in the question
refer to the period WHEN THE ISSUE WAS CREATED ({issue['created_at'][:10]}), NOT the current time.
Based on real-world events that occurred up to the close time ({issue['close_at'][:10]}), was this prediction correct?
...
"""
```

---

## GitHub Actions 스케줄

| 워크플로우 | cron (UTC) | 실행 시각 (KST) |
|-----------|-----------|----------------|
| issue_generator | `0 0,4,8,12,16,20 * * *` | 09:00, 13:00, 17:00, 21:00, 01:00, 05:00 |
| issue_resolver | `30 0,12 * * *` | 09:30, 21:30 |

---

## GitHub Secrets 등록 (사용자 직접)

| Secret 이름 | 설명 |
|------------|------|
| `SUPABASE_URL` | Supabase 프로젝트 URL |
| `SUPABASE_KEY` | Supabase anon/public 키 |
| `GEMINI_API_KEY` | Google Gemini API 키 |

등록 위치: GitHub 레포 → Settings → Secrets and variables → Actions

---

## 로컬 개발 가이드

### fixture 초기화 (첫 실행 시)
```bash
# .env에서 GEMINI_USE_FIXTURE=false로 변경 후 실행
python scripts/run_generate.py
# tests/fixtures/generated_issues.json 생성 확인 후
# .env를 다시 GEMINI_USE_FIXTURE=true로 복원
```

### 이후 반복 테스트
```bash
# fixture JSON을 재사용 → API 호출 없음
python scripts/run_generate.py  # 📦 [FIXTURE] Loaded N issue(s) from fixture.
```

---

## 관련 명세서

- `docs/dev/NostraDa_Pick_인프라안정화_스케줄러분리_명세서_v1.0_20260312.md`
