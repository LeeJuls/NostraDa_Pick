# 노스트라 다 찍기 - 빌드 에러(requirements.txt) 해결 히스토리 (v1.0)
*작성일: 2026-03-06*

## 1. 문제 상황 및 원인
- **문제:** Render 배포 중 `pip install` 실패.
- **에러 메시지:** `OSError: [Errno 2] No such file or directory: '/C:/b/.../anaconda-anon-usage_.../work'`
- **원인:** 로컬 Anaconda 환경에서 `pip freeze` 추출 시, 로컬 빌드 경로(`@ file:///...`)가 포함된 패키지들이 `requirements.txt`에 기록됨. Render와 같은 원격 서버에서는 해당 로컬 경로를 찾을 수 없어 빌드가 중단됨.

## 2. 해결 내용
- **도구 활용:** `fix_req.py` 스크립트를 실행하여 `requirements.txt`를 정제함.
- **상세 조치:**
  1. `requirements.txt` 내의 `@ file:///` 패턴이 포함된 라인을 감지하여 패키지 이름만 남기도록 수정.
  2. `anaconda-`, `conda`, `truststore` 등 로컬 환경 전용 패키지들을 제외 리스트에 추가하여 필터링.
  3. 파일 인코딩을 `UTF-16 LE`에서 표준 `UTF-8`로 변환하여 호환성 확보.
- **검증:** 
  - 로컬 서버(`app.py`) 가동 확인.
  - 브라우저를 통해 `localhost:5000`에서 UI 및 데이터 정상 렌더링 확인.

## 3. 향후 조치
- 현재 로컬에서 수정이 완료되었으므로, 해당 변경사항을 Git에 커밋 후 Push하여 Render의 자동 배포가 정상적으로 동작하는지 확인 필요.
- 향후 패키지 추가 시 `pip freeze > requirements.txt` 대신 필요한 패키지만 명시적으로 기록하는 것을 권장.
