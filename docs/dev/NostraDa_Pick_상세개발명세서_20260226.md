# 🔧 NostraDa_Pick (노다픽) 개발(작업) 명세서

> **프로젝트**: NostraDa_Pick (AI 기반 예언/투표 시뮬레이션 게임)  
> **작성일**: 2026-02-26  
> **목적**: 백엔드 인프라 구축, 제미나이 출제 파이프라인, 프론트엔드 연동, 트랜잭션 최적화  
> **실행 환경**: Flask, Supabase(PostgreSQL), Vanilla JS/CSS, Python  
> **GitHub**: (리포지토리 명) — 커밋 접두사 [GA] (Global Agentic Rule 적용)
> **참여 역할**: PM (기획/조율), Back (엔진/서버), Front (UI/UX), QA (품질검증)

---

## 실행 순서

```
Phase 1 (DB 뼈대) → Phase 2 (AI 동력) → Phase 3 (UI 화면) → Phase 4 (정산 및 트랜잭션)
```

- 각 Phase 완료 후 단위 단위로 테스트 (Save Point 롤백 확보)
- 테스트 완료된 기능은 `[GA]` 태그를 달고 커밋 (푸시는 사용자 승인 후 진행)
- 기획 확장: 실시간 배당률(Dynamic Odds) 및 레벨/랭킹 시스템 등 '리텐션' 요소 코어에 반영

---

## Phase 1: 백엔드 DB 뼈대 및 인프라 구축

### Task 1-1: Supabase 기초 스키마(테이블) 생성
**배경**: 게임의 모든 데이터가 저장될 4대 테이블(`users`, `issues`, `options`, `bets`)을 생성해야 합니다.

**작업 담당**: 
- 👑 **메인 작업자**: **Back** (스키마 설계 및 SQL 스크립트 작성)
- 🤝 **협업 포인트**:
  - **PM**: 향후 확장(ex. 댓글 테이블)을 고려한 스키마 리뷰 
  - **QA**: 제약조건(UNIQUE, Foreign Key 등) 및 NULL 허용 기준 검토

**작업 내용**:
1. Supabase SQL Editor에서 실행할 수 있는 DDL 쿼리 스크립트 작성 (예: `docs/dev/schema_init.sql` 저장)
2. 각 테이블의 제약조건 확립
    - `users`: `id`, `email`, `points`(기본값 1000), `created_at`
    - `issues`: `id`, `title`, `category`, `status`('OPEN', 'RESOLVING' 등), `close_at`, `resolved_at`, `correct_option_id`
    - `options`: `id`, `issue_id`(FK), `title`, `pool_amount`(누적 베팅액)
    - `bets`: `id`, `user_id`(FK), `issue_id`(FK), `option_id`(FK), `amount`, `status`

**변경 파일**: `docs/dev/schema_init.sql` (신규 파일)  
**테스트**: 로컬 스크립트(`supabase_client.py`)에서 4개 테이블에 각각 SELECT 쿼리를 날려 에러(존재하지 않음 등)가 발생하지 않는지 확인.  
**기대 결과**: 기반 뼈대가 완성되어 데이터 삽입 준비 완료

### Task 1-2: Flask 기본 API 라우팅 설정
**배경**: 프론트엔드에서 데이터를 요청하거나, 외부 스크립트가 호출할 기본 API 뼈대 구축이 필요합니다.

**작업 담당**: 
- 👑 **메인 작업자**: **Back** (Flask 앱 구조화 및 라우팅 작성)
- 🤝 **협업 포인트**:
  - **Front**: 데이터 바인딩 시 필요한 JSON 구조(Key 이름) 사전 조율
  - **QA**: 서버 실행 시 발생하는 포트/환경변수 에러 체크

**작업 내용**:
1. `routes/api.py` (또는 `app.py` 내부 블루프린트) 생성
2. 더미 데이터를 반환하거나 빈 리스트를 반환하는 GET 엔드포인트 세팅
    - `/api/issues/open` (열려 있는 이슈 목록)
    - `/api/issues/<issue_id>` (이슈 상세 정보)
    - `/api/users/me` (내 정보 조회)

**변경 파일**: `app.py`, `routes/api.py` (신규 파일)  
**테스트**: 서버 구동 후 브라우저나 Postman에서 `/api/issues/open` 접속 시 200 OK 응답 확인  
**기대 결과**: DB 연동 없이도 API 서버 정상 구동 확인

---

## Phase 2: 제미나이(AI) 문제 출제 자동화 파이프라인

### Task 2-1: 제미나이 프롬프트 설계 및 파싱 스크립트
**배경**: AI가 사람이 읽기 편한 문장이 아닌, DB에 넣기 좋은 JSON 형태로 출제해야 합니다.

**작업 담당**: 
- 👑 **메인 작업자**: **Back** (Gemini 연동 및 파싱 로직 구현)
- 🤝 **협업 포인트**:
  - **PM**: 출제될 이슈 목록(카테고리: 경제, 시사 등) 및 프롬프트 문구(프롬프트 엔지니어링) 제공
  - **QA**: 제미나이 API 응답 지연/Rate Limit 발생 시 어떻게 방어할 것인지 예외 처리 집중 검수

**작업 내용**:
1. `services/gemini_service.py` 파일 생성
2. `google-generativeai` 패키지를 이용해 Gemini 모델 호출
3. 시스템 프롬프트 확립 (예: "너는 스포츠/경제 전문가다... 응답은 리스트형 JSON으로만 하라.")
4. 일반 텍스트나 포맷 에러 시 재시도(Retry)하는 예외처리(try-except) 구현

**변경 파일**: `services/gemini_service.py` (신규 파일)  
**테스트**: 스크립트 1회 실행 시 파이썬 `dict` 형태로 깔끔하게 반환되는지 콘솔 출력 검증  
**기대 결과**: 정제된 퀴즈 데이터(Python Dict) 확보

### Task 2-2: 파싱 데이터 DB Insert 로직 (출제 엔진)
**배경**: Task 2-1에서 얻은 딕셔너리를 Supabase의 `issues`와 `options` 테이블에 동시에 넣어야 합니다.

**작업 담당**: 
- 👑 **메인 작업자**: **Back** (DB 쿼리 모듈 작성)
- 🤝 **협업 포인트**:
  - **QA**: `issues`는 Insert 되었으나 중간에 에러가 발생하여 `options`가 없는 반쪽짜리 데이터가 생성되지 않는지 무결성 검증

**작업 내용**:
1. `services/db_service.py`에 `create_auto_issue(issue_data)` 함수 구현
2. 전달받은 데이터를 이용해 `issues` 테이블에 Insert 후 반환된 `issue.id`를 추출
3. 추출된 `issue.id`를 이용해 하위 `options` 2개(Yes, No)를 Insert

**변경 파일**: `services/db_service.py` (신규 파일)  
**테스트**: 함수 구동 후 Supabase 대시보드(또는 조회 스크립트)에서 이슈와 옵션이 매칭되어 잘 들어갔는지 확인  
**기대 결과**: 한 번의 스크립트 실행으로 문제 1세트 출제 완결

---

## Phase 3: 프론트엔드 UI/UX (리텐션 요소 반영)

### Task 3-1: 메인 레이아웃 및 이슈 카드 디자인
**배경**: 예측 게임 특성상 투표하고 싶은 디자인과 실시간 변동 스코어(Pool)를 시각화해야 합니다.

**작업 담당**: 
- 👑 **메인 작업자**: **Front** (HTML 레이아웃 및 CSS 인터랙션 개발)
- 🤝 **협업 포인트**:
  - **PM**: 게임의 몰입감을 극대화하는 UX 흐름(카드 배치 등) 리뷰
  - **QA**: 각 종 크롬, 엣지, 모바일 억지 해상도에서의 화면 깨짐(CSS Break) 테스트 

**작업 내용**:
1. `templates/index.html` 기반 레이아웃 (헤더, 잔여 포인트 표시, 이슈 리스트 영역)
2. `style.css` 에 '이슈 카드' 스타일링 (마감 임박 뱃지, 카테고리 컬러, Yes/No 투표 버튼)
3. **[리텐션 강화]** 선택지별 '누적 포인트 게이지(Progress Bar)'를 디자인 추가. 

**변경 파일**: `templates/index.html`, `static/css/style.css`  
**테스트**: 하드코딩된 더미 HTML로 브라우저 렌더링 검수 (디자인 깨짐 체크)  
**기대 결과**: 직관적이고 베팅하고 싶은 심리를 자극하는 UI 확보

### Task 3-2: Jinja2 데이터 바인딩 및 AJAX 베팅 연동
**배경**: 하드코딩된 화면을 실제 API와 연동하고, 클릭 시 비동기로 투표를 처리합니다.

**작업 담당**: 
- 👑 **메인 작업자**: **Front** (비동기 Fetch 액션 및 화면 조작)
- 🤝 **협업 포인트**:
  - **Back**: 프론트엔드가 요청할 POST `/api/bets`의 데이터 형식 및 응답 성공/실패 메시지 맵핑 협력
  - **QA**: 연속으로 버튼 클릭(광클) 시 서버 1회 전송 후 버튼 바로 비활성화(Debouncing) 되는지 확인

**작업 내용**:
1. `app.py` 의 `index` 라우터에서 DB 데이터를 조회하여 템플릿으로 전달
2. `static/js/app.js` 에 베팅 버튼 클릭 이벤트 추가 (`fetch` API 전송)
3. 베팅 성공 시 현 화면의 포인트/배당 게이지 바를 동적으로 업데이트

**변경 파일**: `app.py`, `templates/index.html`, `static/js/app.js`  
**테스트**: 투표 버튼 클릭 -> 서버 응답 -> 화면 동적 갱신(새로고침 없이) 테스트  
**기대 결과**: 부드러운 유저 경험

---

## Phase 4: 트랜잭션 및 정산 (핵심 로직 고도화)

### Task 4-1: 베팅 트랜잭션 Supabase RPC 
**배경**: 투표 시 "유저 잔고 확인 -> 잔고 차감 -> bets 삽입 -> options pool 증가"가 **동시(ACID)**에 이루어져야 합니다.

**작업 담당**: 
- 👑 **메인 작업자**: **Back** (Supabase 스토어드 프로시저 작성)
- 🤝 **협업 포인트**:
  - **QA**: **[최우선 검증]** 베팅 마감시간이 끝난 뒤에 들어오는 요청 차단 여부, 잔고 이상 베팅 시도 등 가장 공격적으로 에지 케이스 부하 테스트를 수행해야 함

**작업 내용**:
1. 다중 쿼리 시 Race Condition 방지를 위해 Supabase 내장 **RPC (Stored Procedure - PL/pgSQL)** 작성: `place_bet(p_user_id, p_option_id, p_amount)` 
2. 로직: 잔여금 확인 -> 차감 -> Insert -> Update
3. 백엔드에서는 해당 RPC만 호출 

**변경 파일**: `docs/dev/rpc_place_bet.sql` (생성 가이드), `routes/api.py` 수정  
**테스트**: 동시 다발적 100건 API Call(Postman, JMeter 등) 수행 시 데이터 무결성 검증  
**기대 결과**: 서버 부하 및 동시 베팅 시의 숫자 오류 원천 차단

### Task 4-2: 이슈 결과 확정 및 수익금 정산
**배경**: AI가 결과를 판단했을 때 맞춘 자들에게 승리 배당금을 분배해야 합니다.

**작업 담당**: 
- 👑 **메인 작업자**: **Back** (정산 로직 및 분배 알고리즘 구현)
- 🤝 **협업 포인트**:
  - **PM**: 무승부거나 맞춘 사람이 0명일 경우 원금을 돌려주는지(Refund) 혹은 서버가 흡수할지에 대한 최종 정책 전달
  - **QA**: `Pool / Pool` 연산 중 수학적 예외 상황(Zero Divide)을 발생시켜 방어 로직 확인

**작업 내용**:
1. 승리 옵션의 베팅 유저들을 추출 후, 전체 `pool_amount` 기반 **실시간 배당률** 계산
2. 승자의 `users.points` 리워드 지급 로직 실행 (`users` 테이블 업데이트)
3. 예외처리 반영

**변경 파일**: `services/resolution_service.py` (신규 파일)  
**테스트**: 가상 데이터로 모의 정산 실시 후 최종 각 유저 잔고 일치 확인  
**기대 결과**: 프로젝트 사이클 전체 완성

---

## 커밋/히스토리 계획
| 순서 | Task | 대상 파일 | 커밋 메시지 |
|---|---|---|---|
| 1 | Task 1-1, 1-2 | `docs/*`, `app.py`, `api.py` | `[GA] set: Supabase 스키마 DDL 작성 및 기본 API 라우팅` |
| 2 | Task 2-1, 2-2 | `gemini_service.py`, `db_service.py` | `[GA] feat: 제미나이 문제 출제 파이프라인 엔진 구현` |
| 3 | Task 3-1, 3-2 | `index.html`, `style.css`, `app.js` | `[GA] view: 메인 UI, 투표 카드 렌더링 및 비동기 AJAX 연동` |
| 4 | Task 4-1 | `rpc_...sql`, `api.py` | `[GA] refactor: 동시성 방지를 위한 베팅 트랜잭션 RPC 도입` |
| 5 | Task 4-2 | `resolution_service.py` | `[GA] feat: 이슈 정산 및 수익금(배당금) 분배 로직 구현` |

---

## ⛔ 주의사항
1. 외부 패키지(`gemini`, `supabase-py` 등)는 이미 가상환경 및 `.env`에 세팅되었음을 확인 완료. 추가 패키지는 가급적 지양하라.
2. 각 Task 완료 시 마다 반드시 `[GA]` 태그를 달아 커밋 할 것.
3. Push는 절대 에이전트 선에서 임의로 진행하지 말고 대기하라.
4. QA 파트는 매 Phase의 **테스트** 항목을 직접 시뮬레이션하고 넘어가야 함.
