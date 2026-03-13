# NostraDa Pick 인수인계서
**버전**: VER01 | **날짜**: 2026-03-13 | **작성자**: Claude (Backend Agent)

---

## 1. 프로젝트 개요

글로벌 핫이슈(스포츠, 경제, 정치 등)의 단기 결과(Yes/No)를 예측하는 텍스트 기반 시뮬레이션 게임.
4시간마다 Gemini AI가 자동으로 문제 출제 → 유저 투표 → AI가 결과 판정 → 포인트 지급.

- **라이브 URL**: https://nostrada-pick.onrender.com
- **GitHub**: https://github.com/LeeJuls/NostraDa_Pick

---

## 2. 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | Flask (Python 3.11+) + Jinja2 |
| DB/Auth | Supabase (PostgreSQL) + Google OAuth |
| AI 출제 | Gemini API (`gemini-3.1-flash-lite-preview`) |
| AI 결과판정 | Gemini API (`gemini-2.0-flash-lite`) |
| 스포츠 API | football-data.org (축구) + api-sports.io (NBA/MLB) |
| 번역 | Google Translate API (이슈 생성 시 1회, 7개 언어 일괄) |
| 배포 | Render.com |
| Keep Alive | cron-job.org (10분 간격 ping) |
| CI/CD | GitHub Actions (issue_generator, issue_resolver) |

---

## 3. 핵심 파일 구조

```
├── app.py                          # Flask 엔트리포인트
├── config.py                       # 환경변수 관리
├── routes/
│   ├── api.py                      # AJAX API (베팅, 관리자 기능)
│   └── auth.py                     # Google OAuth 로그인
├── services/
│   ├── gemini_service.py           # ⭐ Gemini AI 출제 + 7개 언어 번역 (핵심)
│   ├── resolver_service.py         # 결과 판정 (Yes/No + 포인트 지급)
│   ├── sports_schedule_service.py  # 스포츠 경기 일정 (football-data.org + api-sports.io)
│   └── supabase_client.py          # DB 연결
├── templates/index.html            # 메인 페이지 (Jinja2)
├── static/
│   ├── css/style.css
│   └── js/app.js                   # ⭐ 프론트엔드 로직 + UI 라벨 7개 언어
├── scripts/
│   ├── reset_issues.py             # DB 이슈/베팅 전체 삭제 (bets→issues 순서)
│   └── gen_new_issues.py           # 수동 이슈 생성 (python gen_new_issues.py 4)
├── .github/workflows/
│   ├── issue_generator.yml         # UTC 0,4,8,12,16,20시 자동 출제
│   └── issue_resolver.yml          # UTC 0:30,12:30 자동 결과 판정
├── render.yaml                     # Render 배포 설정
└── docs/
    ├── HANDOVER_VER01.md           # ← 현재 파일
    ├── dev/                        # 기능 명세서
    └── history/                    # 작업 히스토리
```

---

## 4. 환경변수 (.env)

로컬 `.env` 파일 생성 필요 (gitignore됨):

```env
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=xxx

# Gemini (복수 키 가능: key1,key2,key3)
GEMINI_API_KEY=xxx

# Google OAuth
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx

# Flask
FLASK_ENV=development       # 로컬: development | 서버: production
SECRET_KEY=xxx

# 스포츠 API
FOOTBALL_DATA_API_KEY=xxx   # football-data.org
API_SPORTS_KEY=xxx          # api-sports.io (NBA/MLB)

# Python
PYTHON_VERSION=3.11.0

# 로컬 개발 옵션
DISABLE_SCHEDULER=false     # true: APScheduler 비활성 (Actions 사용)
GEMINI_USE_FIXTURE=false    # true: fixture JSON 재사용 (API 호출 절약)
```

> **Render에도 동일한 변수 등록 필요** (FLASK_ENV=production, DISABLE_SCHEDULER=true)

---

## 5. 로컬 개발 환경 세팅

```bash
# 1. 클론
git clone https://github.com/LeeJuls/NostraDa_Pick.git
cd NostraDa_Pick

# 2. 가상환경
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Mac/Linux

# 3. 의존성 설치
pip install -r requirements.txt

# 4. .env 파일 생성 (위 섹션 참고)

# 5. 실행
flask run --debug
# → http://localhost:5000
# → Admin Panel: http://localhost:5000/admin (localhost에서만 노출)
```

---

## 6. 주요 스크립트

```bash
# Windows 인코딩 설정 (이모지 출력 오류 방지)
set PYTHONIOENCODING=utf-8

# 이슈 전체 삭제 (bets → issues 순서로 삭제)
python scripts/reset_issues.py

# 수동 이슈 생성 (숫자: 생성할 문제 수)
python scripts/gen_new_issues.py 4
```

---

## 7. 자동화 스케줄

| 구분 | 주기 | 역할 |
|------|------|------|
| GitHub Actions: issue_generator | UTC 0,4,8,12,16,20시 | 자동 문제 출제 |
| GitHub Actions: issue_resolver | UTC 0:30, 12:30 | 자동 결과 판정 + 포인트 지급 |
| cron-job.org | 10분 간격 | Render Sleep 방지 ping |

**GitHub Actions Secrets 필요 (레포 → Settings → Secrets):**
`SUPABASE_URL`, `SUPABASE_KEY`, `GEMINI_API_KEY`, `GEMINI_API_KEYS`

---

## 8. Gemini 출제 규칙 (gemini_service.py)

| 규칙 | 내용 |
|------|------|
| FUTURE ONLY | 과거 이벤트 금지, 2025년 이전 금지 |
| ABSOLUTE UTC TIME | "tomorrow/today" 금지 → `(UTC+0) 2026-03-13 18:00` 형식 강제 |
| RESOLVABLE BY CLOSE TIME | 투표 마감(+4h) 전 결과 공개 이벤트 금지 |
| WITHIN 48 HOURS | 이벤트 최대 48시간 이내 |
| PRICE/MARKET 24H | 가격 예측은 24시간 이내 |
| SPECIFIC ENTITIES | 회사명·국가명·선수명 등 구체적 명시 필수 |
| SPORTS INTEGERS | 골/점수 정수만 허용 (1.5골 금지) |
| NO RELEASE PREDICTIONS | 엔터테인먼트 출시/발표 예측 금지 |
| CATEGORY MAX 2 | 동일 카테고리 최대 2개 (코드 레벨 검증 병행) |
| SPORTS SCHEDULE ONLY | 스포츠 문제는 API 제공 경기 목록에서만 생성 |

---

## 9. 시간 처리 주의사항 ⚠️

- **모든 시간은 UTC+0 기준** → `datetime.now(timezone.utc)` 사용 필수
- `datetime.now()` 사용 금지 → 서버 로컬 시간(KST+9) 반환 → 9시간 오차 발생
- `close_at` = 이슈 생성 시점 + 4시간 (UTC)
- strftime 형식: `'(UTC+0) %Y-%m-%d %H:%M'`
- 한국어 후처리: `(UTC+0)` → `UTC 0시 기준` (자동 치환)

---

## 10. 배포 프로세스

1. `main` 브랜치에 push → Render 자동 배포 (약 2~3분 소요)
2. Render 환경변수는 대시보드에서 별도 관리 (push와 무관)
3. GitHub Actions는 push와 무관하게 cron으로 독립 실행

---

## 11. 외부 서비스 계정

| 서비스 | 용도 | 대시보드 |
|--------|------|---------|
| Render | 배포 서버 | https://dashboard.render.com |
| Supabase | DB + Auth | https://supabase.com/dashboard |
| cron-job.org | Keep Alive | https://console.cron-job.org |
| GitHub | 소스코드 + CI/CD | https://github.com/LeeJuls/NostraDa_Pick |
| football-data.org | 축구 경기 일정 | https://www.football-data.org/client/register |
| api-sports.io | NBA/MLB 일정 | https://api-sports.io |
| Google Cloud | OAuth + Translate API | https://console.cloud.google.com |

---

## 12. 알려진 이슈 / 주의사항

- **Gemini 학습데이터 한계**: 이미 발생한 이벤트를 미래로 착각 가능 → 엔터 출시 금지 규칙으로 완화
- **스포츠 일정 의존**: API에 없는 경기는 출제 안 됨 (의도된 동작)
- **Gemini 429 에러**: 무료 쿼터 초과 시 키/모델 자동 로테이션 → 전부 소진 시 더미 데이터 폴백
- **번역**: 이슈 생성 시 1회 Google Translate → DB 저장. 이후 API 호출 없음
- **Admin Panel**: `localhost`에서만 접근 가능 (프로덕션에서는 숨김)
