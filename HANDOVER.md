# NostraDa Pick 인수인계서

> 최종 업데이트: 2026-03-13

---

## 1. 프로젝트 개요

글로벌 핫이슈(스포츠, 경제, 정치 등)의 단기 결과(Yes/No)를 예측하는 텍스트 기반 시뮬레이션 게임.
4시간마다 Gemini AI가 자동으로 문제 출제 → 유저 투표 → AI가 결과 판정 → 포인트 지급.

---

## 2. 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | Flask (Python 3.11+) + Jinja2 |
| DB/Auth | Supabase (PostgreSQL) + Google OAuth |
| AI 출제 | Gemini API (gemini-3.1-flash-lite-preview) |
| AI 결과판정 | Gemini API (gemini-2.0-flash-lite) |
| 스포츠 API | football-data.org (축구) + api-sports.io (NBA/MLB) |
| 번역 | Google Translate API (이슈 생성 시 1회 호출, 7개 언어) |
| 배포 | Render.com |
| Keep Alive | cron-job.org (10분 간격) |
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
│   ├── gemini_service.py           # ⭐ Gemini AI 출제 + 번역 (핵심)
│   ├── resolver_service.py         # 결과 판정 (Yes/No + 포인트)
│   ├── sports_schedule_service.py  # 스포츠 경기 일정 API
│   └── supabase_client.py          # DB 연결
├── templates/index.html            # 메인 페이지 (Jinja2)
├── static/
│   ├── css/style.css
│   └── js/app.js                   # ⭐ 프론트엔드 로직 + 7개 언어 번역
├── scripts/
│   ├── reset_issues.py             # DB 이슈/베팅 전체 삭제
│   └── gen_new_issues.py           # 수동 이슈 생성 (인자: count)
├── .github/workflows/
│   ├── issue_generator.yml         # 4시간마다 자동 출제
│   └── issue_resolver.yml          # 4시간마다 자동 결과 판정
└── render.yaml                     # Render 배포 설정
```

---

## 4. 환경변수 (.env)

```env
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=xxx

# Gemini
GEMINI_API_KEY=xxx              # 또는 GEMINI_API_KEYS=key1,key2,key3

# Google OAuth
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx

# Flask
FLASK_ENV=production            # production | development
SECRET_KEY=xxx

# 스포츠 API
FOOTBALL_DATA_API_KEY=xxx       # football-data.org
API_SPORTS_KEY=xxx              # api-sports.io (NBA/MLB)

# Python
PYTHON_VERSION=3.11.0
```

**Render에도 동일한 환경변수가 등록되어 있어야 함.**

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

# 4. .env 파일 생성 (위 환경변수 참고)

# 5. 실행
flask run --debug
```

---

## 6. 주요 스크립트

```bash
# 이슈 전체 삭제 (bets → issues 순서)
python scripts/reset_issues.py

# 수동 이슈 생성 (4개)
python scripts/gen_new_issues.py 4

# Windows에서 인코딩 오류 시
set PYTHONIOENCODING=utf-8
python scripts/gen_new_issues.py 4
```

---

## 7. Gemini 프롬프트 규칙 (gemini_service.py)

현재 적용된 출제 규칙:

| 규칙 | 내용 |
|------|------|
| FUTURE ONLY | 과거 이벤트 생성 금지, 2025년 이전 금지 |
| ABSOLUTE UTC TIME | "tomorrow", "today" 금지 → "(UTC+0) 2026-03-13 18:00" 형식 강제 |
| RESOLVABLE BY CLOSE TIME | 투표 마감(+4h) 전에 결과 공개되는 이벤트 금지 |
| WITHIN 48 HOURS | 이벤트 48시간 이내만 허용 |
| PRICE/MARKET 24H | 가격 예측은 24시간 이내 |
| SPECIFIC ENTITIES | 회사명, 국가명, 선수명 등 구체적 명시 필수 |
| SPORTS INTEGERS | 골/점수 정수만 (1.5골 금지) |
| NO RELEASE PREDICTIONS | 엔터테인먼트 출시/발표 예측 금지 (학습데이터 한계) |
| CATEGORY MAX 2 | 동일 카테고리 최대 2개 |
| SPORTS SCHEDULE ONLY | 스포츠 경기는 API 제공 일정에서만 생성 |

---

## 8. 자동화 (GitHub Actions)

| 워크플로우 | 주기 | 역할 |
|-----------|------|------|
| issue_generator.yml | UTC 0,4,8,12,16,20시 | 자동 문제 출제 |
| issue_resolver.yml | UTC 0,4,8,12,16,20시 | 자동 결과 판정 + 포인트 지급 |

**Keep Alive**: cron-job.org (10분 간격) — GitHub Actions가 아닌 외부 서비스

---

## 9. 시간 처리 (중요!)

- **모든 시간은 UTC+0 기준** (`datetime.now(timezone.utc)`)
- `datetime.now()` 사용 금지 → 서버 로컬 시간(KST+9)이 반환되어 9시간 오차 발생
- close_at = 이슈 생성 시점 + 4시간 (UTC)
- 한국어 표기: `(UTC+0)` → `UTC 0시 기준` (자동 후처리)
- `strftime` 형식: `'(UTC+0) %Y-%m-%d %H:%M'`

---

## 10. 배포 프로세스

1. `main` 브랜치에 push → Render 자동 배포 (2~3분)
2. Render 환경변수는 대시보드에서 별도 관리
3. GitHub Actions는 push와 무관하게 cron으로 독립 실행

---

## 11. 현재 알려진 이슈 / 주의사항

- **Gemini 학습데이터 한계**: 이미 발생한 이벤트를 미래로 착각할 수 있음 (오징어게임2 등)
- **스포츠 경기 일정**: API 제공 경기만 사용. API에 없는 경기는 생성 안 됨
- **Gemini 429 에러**: 무료 API 쿼터 초과 시 모델/키 자동 로테이션 → 전부 소진 시 더미 데이터 폴백
- **Render 무료 Sleep**: cron-job.org가 10분마다 ping하여 방지 중
- **번역 캐싱**: 이슈 생성 시 1회 번역 → DB 저장. app.js의 translations 객체는 UI 라벨용 (별도)

---

## 12. 외부 서비스 계정

| 서비스 | 용도 | 대시보드 |
|--------|------|---------|
| Render | 배포 | https://dashboard.render.com |
| Supabase | DB | https://supabase.com/dashboard |
| cron-job.org | Keep Alive | https://console.cron-job.org |
| GitHub | 소스코드 + CI/CD | https://github.com/LeeJuls/NostraDa_Pick |
| football-data.org | 축구 경기 일정 | https://www.football-data.org |
| api-sports.io | NBA/MLB 경기 일정 | https://api-sports.io |
