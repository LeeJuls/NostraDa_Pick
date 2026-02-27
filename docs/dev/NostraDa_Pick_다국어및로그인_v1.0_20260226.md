# NostraDa_Pick 개발 명세서 (다국어 및 UI/Timer, Google OAuth 뼈대)
- **작성일**: 2026년 2월 26일
- **버전**: v1.0
- **목적**: 프론트엔드 UI 버그 픽스, 타이머 기능 실시간 적용 및 로그인 환경 세팅

## 1. 다국어 지원 (JS 및 템플릿 처리)
- **감지 로직**: `navigator.language` 객체를 이용해 브라우저 운영체제의 사용 언어를 구함 (맨 앞 2자리만 파싱, 예: `ko-KR` -> `ko`)
- **저장 영역**: 브라우저 `localStorage`에 `userLang`이라는 키로 언어 코드를 저장하여 새로고침해도 유지되게 만듦
- **적용 언어**: `EN`, `KO`, `JA`, `DE`, `FR`, `ES`, `PT`, `ZH`
- **타이틀 번역**:
  - `EN`, 그 외 공통: NostraDamu Pick
  - `KO`: 노스트라다찍어.
  - `JA`: ノストラダ撮影
  - 로고(`<a class="logo">`)와 HTML 타이틀(`document.title`)이 자동 변환됨

## 2. 타이머 기능
- **적용 대상**: `data-deadline` 속성이 적용된 DOM 엘리먼트 (예: `<div class="deadline-timer" data-deadline="2026-03-01T23:59:59Z">`)
- **실시간 갱신**: JS의 `setInterval((), 1000)` 함수를 이용해 1초마다 실시간 날짜를 계산, 일, 시간, 분, 초가 감소하는 레이아웃 적용

## 3. 베팅 UI (Yes/No 버튼 기능)
- **진행바 예외 처리**: 데이터가 0일 경우 기존 CSS 레이아웃이 깨지지 않게끔 `text-align: left/right` 처리 및 겹침 방지 코드 추가
- **비회원 로그인 유도**: HTML `<body>` 태그에 `data-logged-in` 속성을 Flask Jinja (`{{ 'true' if session.get('user') else 'false' }}`)로 부여하고 프론트엔드에서 베팅 버튼 클릭 이벤트 핸들러 안에 `if (!isLoggedIn) return window.location.href = '/auth/login'`를 넣어 로그인을 유도함

## 4. 백엔드 인증 (Authlib Google OAuth 연동)
- **설치 모듈**: `Authlib==1.3.0` 및 의존성 라이브러리 추가
- **라우터 구조**: `route/auth.py` 블루프린트를 생성해 로그인 처리(`/auth/login`), 콜백 처리(`/auth/callback`), 로그아웃(`/auth/logout`) 엔드포인트를 할당함
- **권한 승인 시점**:
    - 구글 API에서 이메일 및 프로필 정보를 취득
    - 해당 정보를 플라스크 세션(`session['user']`)에 기록하여 로그인 환경 활성화
- **추후 요구사항**: `.env` 파일 내에 `GOOGLE_CLIENT_ID` 및 `GOOGLE_CLIENT_SECRET` 키 값이 존재해야 콜백 에러가 발생하지 않음
