# 노스트라 다 찍기 - 의존성(requirements.txt) 빌드 에러 해결 명세서 (v1.0)
*작성일: 2026-03-05*

## 1. 개요 및 문제 시나리오
- **이슈:** `pip install -r requirements.txt` 실행 시 `[Errno 2] No such file or directory: '/C:/b/.../work'` 에러 발생
- **원인:** 개발 환경(Anaconda/Windows)에서 추출된 `requirements.txt`에 로컬 캐시/빌드 패스(`@ file:///...`)가 그대로 기록되었으며, 파일이 `UTF-16 LE` 인코딩으로 저장되어 환경 간 호환성 문제가 생김.

## 2. 해결 및 변경 계획 (개발 내용)
### [수정 1] 인코딩 및 로컬 경로 제거
- **대상 파일:** `requirements.txt`
- **변경 사항:**
  1. 파일을 읽어 `UTF-8` 인코딩으로 재저장.
  2. `@ file:///...` 패턴을 가진 줄을 필터링. 프로젝트 구동에 필수적인 패키지는 표준 PyPI 패키징 이름(예: `urllib3`, `truststore` 등)으로 버전만 명시하거나, 빌드 디펜던시인 경우 목록에서 제외.

### [수정 2] 패키지 재설치 및 검증
- **대상:** 로컬 Python 가상환경
- **로직:** 수정한 `requirements.txt`를 바탕으로 종속성이 꼬인 부분 없이 정상 설치되는지 확인.

## 3. 테스트(QA) 계획
1. `pip install -r requirements.txt` 실행 시 에러가 출력되지 않는지 확인.
2. `python app.py` 또는 `flask run` 시 모듈 누락 에러(ImportError)가 발생하지 않고 서버가 기동되는지 확인.
