# Garim Backend (FastAPI)

가림(GARIM) 서비스의 핵심 비즈니스 로직, 데이터베이스 통신, 외부 AI 워커 연동을 담당하는 FastAPI 백엔드입니다.

## 🚀 서버 실행 방법

현재 프로젝트는 **Docker Compose**를 이용한 통합 환경 실행을 권장합니다.
로컬 환경에서 직접 실행하려면 아래 가이드를 참고하세요.

### 방법 1. Docker 통합 환경 (권장)
프로젝트 최상단 폴더에서 아래 명령어를 실행하면 DB, Redis, 백엔드 전체가 한 번에 실행됩니다.
```bash
docker-compose up -d --build
```

### 방법 2. 로컬 직접 실행
Python 3.10 이상의 환경에서 가상환경을 세팅한 후 실행합니다.
```bash
# 패키지 설치
pip install -r requirements.txt

# 서버 실행 (uvicorn)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
> **참고**: `main.py`를 직접 실행하지 않고 uvicorn 명령어로 실행하는 이유는, 로깅 중복 출력 방지 및 파일 상대 경로 일원화를 위해서입니다.

## ☁️ 외부 코랩(Colab) 워커 통신 방법 (Cloudflare Tunnel)

백엔드 서버와 구글 코랩에 있는 GPU 워커가 양방향 통신을 하려면 백엔드 주소가 외부에 노출되어야 합니다.

- **[옵션 1] 정식 도메인이 있는 경우 (권장)**
  이미 `garim.shop`과 같은 정식 도메인이 Cloudflare Zero Trust에 연결되어 있다면, **백엔드에서 따로 스크립트를 실행할 필요가 없습니다.** (코랩 설정 파일에 정식 도메인 주소 기입)

- **[옵션 2] 정식 도메인이 없는 경우 (일회성 임시 터널)**
  로컬 환경에서 정식 도메인 없이 테스트 중이라면, 아래 스크립트를 실행해 1회용 임시 터널을 개통합니다.
  ```bash
  python cloudflare_tunnel.py
  ```
  출력된 `https://xxx.trycloudflare.com` 형태의 주소를 코랩 워커 설정(`BACKEND_URL`)에 입력하시면 됩니다.

## 📂 폴더 구조도

```text
backend/
├── controllers/        # API 요청/응답 처리 (Controller 계층)
├── core/               # DB 설정, 로깅, 환경변수, 보안 등 공통 모듈
├── docker/             # DB 초기화 SQL 스크립트 및 도커 관련 설정
├── local_worker/       # 로컬 컴퓨터 리소스를 활용하는 백그라운드 워커
├── models/             # 데이터베이스 테이블 매핑 (SQLAlchemy ORM)
├── routes/             # 도메인별 API 라우터 (엔드포인트) 정의
├── schemas/            # 데이터 검증 및 직렬화 (Pydantic DTO)
├── services/           # 핵심 비즈니스 로직 및 외부 API 호출 계층
├── storage/            # 사용자 업로드 파일 및 처리 결과물 임시 저장소
├── tools/              # 개발 지원용 외부 도구 및 스크립트 모음
├── utils/              # 프로젝트 전반에 걸쳐 재사용 가능한 유틸 함수들
├── cloudflare_tunnel.py # 로컬-코랩 연동을 위한 1회용 터널 발급 스크립트
├── Dockerfile          # 백엔드 컨테이너 생성을 위한 도커 빌드 파일
├── main.py             # FastAPI 앱 진입점 및 서버 실행 파일
└── requirements.txt    # 백엔드 필수 파이썬 패키지 목록
```

## ⚙️ 깃(Git) 사용 가이드 (충돌 방지)
- 코드를 업로드(push)하기 전에 반드시 `git pull`을 받아 최신 상태를 유지하세요.
- `git add .` (전체 추가) 대신, 가급적 **본인이 수정한 파일만 명시적으로 지정**(`git add 경로/파일명`)해서 커밋하는 것을 권장합니다.
- 커밋 메시지 작성 시 반드시 [가림 프로젝트 Git 커밋 메시지 규칙](../docs/guides/GIT_메세지작성.md)을 준수해 주세요.
