# Docker 개발/운영 환경 분리 작업 지시서

> Codex 작업용 통합본: 개발 frontend 포트 `3000` 기준 반영

## 목적

현재 프로젝트의 `db`, `redis`, `backend`, `frontend`, `nginx` 서비스를 Docker Compose로 관리한다.

개발 환경과 운영 환경을 명확히 분리하되, 각 환경에서 아래 서비스들을 하나의 Docker Compose 명령으로 실행할 수 있도록 구성한다.

- db
- redis
- backend
- frontend
- nginx

기존 코드 동작을 깨지 않도록 최소 수정으로 진행한다.

> **수정 반영 사항**: 개발 환경의 frontend Vite dev server 포트는 `3000`을 기준으로 한다. 따라서 개발 nginx는 `/` 요청을 `final_frontend:3000`으로 proxy하고, `frontend/Dockerfile.dev`, `docker-compose.dev.yml`, `.env.development`, 체크리스트도 모두 `3000` 기준으로 작성한다. 운영 환경은 frontend dev server를 사용하지 않으므로 `3000` 포트 기준을 적용하지 않고, 기존처럼 frontend build 결과물인 `dist`를 nginx가 서빙한다.

---

## 1. 유지해야 할 기본 조건

가능하면 기존 서비스명을 유지한다.

- `final_db`
- `final_redis`
- `final_backend`
- `final_frontend`
- `final_nginx`

가능하면 기존 network 구조를 유지한다.

Docker 내부 통신은 Compose service name 기준으로 연결한다.

예시:

```env
DB_HOST=final_db
REDIS_URL=redis://final_redis:6379/0
```

기존 backend/frontend 코드가 사용하는 API 경로가 `/api/...` 기준으로 동작하도록 nginx proxy 설정과 맞춘다.

---

## 2. 생성 또는 수정할 파일 구조

가능하면 아래 구조로 구성한다.

```text
.
├── docker-compose.dev.yml
├── docker-compose.prod.yml
├── .env.development
├── .env.production
├── nginx/
│   ├── dev.conf
│   └── prod.conf
├── backend/
│   ├── Dockerfile.dev
│   └── Dockerfile.prod
└── frontend/
    ├── Dockerfile.dev
    └── Dockerfile.prod
```

개발/운영 Docker Compose 파일 모두에서 `backend`와 `frontend`는 각각의 Dockerfile을 명시적으로 참조한다.

개발:

- backend: `./backend/Dockerfile.dev`
- frontend: `./frontend/Dockerfile.dev`

운영:

- backend: `./backend/Dockerfile.prod`
- frontend: `./frontend/Dockerfile.prod`

`docker-compose.dev.yml`과 `docker-compose.prod.yml`의 backend/frontend 서비스에는 반드시 아래 항목을 명시한다.

```yaml
build:
  context: ...
  dockerfile: ...
```

---

# 3. 개발 환경 구성

## 3.1 개발 환경 목표

개발용 Docker Compose 파일을 별도로 작성한다.

개발 환경에서도 아래 서비스를 하나의 Docker Compose 명령으로 실행할 수 있어야 한다.

- `final_db`
- `final_redis`
- `final_backend`
- `final_frontend`
- `final_nginx`

개발 환경에서도 nginx와 frontend는 반드시 별도 서비스로 분리한다.

개발 환경 구조는 다음과 같아야 한다.

```text
브라우저
  ↓
final_nginx
  ├── /      → final_frontend:3000
  └── /api   → final_backend:8000
```

개발 환경에서 frontend는 nginx로 정적 build 결과물을 서빙하지 않는다.

- `final_frontend`: Vite dev server 실행
- `final_nginx`: reverse proxy 역할
- `final_nginx`: `/` 요청을 `final_frontend:3000`으로 proxy
- `final_nginx`: `/api` 요청을 `final_backend:8000`으로 proxy

---

## 3.2 backend 개발 구성

backend 개발 환경은 아래 조건을 만족해야 한다.

- `backend/Dockerfile.dev`를 사용해서 image를 build한다.
- 로컬 `./backend` 디렉토리를 컨테이너 내부 앱 경로에 volume mount한다.
- backend는 `uvicorn --reload` 방식으로 실행한다.
- Python 코드 수정 시 Docker image를 다시 build하지 않아도 변경 사항이 바로 반영되어야 한다.
- 단, `requirements.txt`, Dockerfile, 시스템 패키지 변경 시에는 rebuild가 필요할 수 있다.

예시:

```yaml
final_backend:
  build:
    context: ./backend
    dockerfile: Dockerfile.dev
  container_name: final_backend
  volumes:
    - ./backend:/app
  command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
  env_file:
    - .env.development
  depends_on:
    - final_db
    - final_redis
  networks:
    - garim_network
```

주의:

- 실제 `main:app` 경로는 현재 프로젝트 구조에 맞게 확인해서 수정한다.
- 예를 들어 FastAPI app이 `app.main:app`에 있다면 명령을 아래처럼 수정한다.

```yaml
command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 3.3 backend 개발 Dockerfile 기준

`backend/Dockerfile.dev`는 개발 실행에 필요한 Python 패키지를 설치하고, reload 실행이 가능한 구조로 작성한다.

예시:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

주의:

- 실제 Python 버전은 프로젝트 기준에 맞춘다.
- 실제 FastAPI app import 경로는 프로젝트 구조에 맞춘다.

---

## 3.4 frontend 개발 구성

frontend 개발 환경은 아래 조건을 만족해야 한다.

- `frontend/Dockerfile.dev`를 사용해서 image를 build한다.
- 로컬 `./frontend` 디렉토리를 컨테이너 내부 앱 경로에 volume mount한다.
- frontend는 개발 환경에서 nginx로 정적 build 결과물을 서빙하지 않는다.
- frontend는 Vite dev server 방식으로 실행한다.
- frontend 코드 수정 시 `npm run build` 없이 HMR 또는 reload로 바로 반영되어야 한다.
- `node_modules` 충돌을 피하기 위해 `/app/node_modules`는 별도 익명 volume으로 분리한다.

개발용 frontend 실행 명령은 아래 기준으로 작성한다.

```bash
npm run dev -- --host 0.0.0.0 --port 3000
```

개발용 docker-compose의 frontend 서비스 예시:

```yaml
final_frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile.dev
  container_name: final_frontend
  volumes:
    - ./frontend:/app
    - /app/node_modules
  command: npm run dev -- --host 0.0.0.0 --port 3000
  expose:
    - "3000"
  env_file:
    - .env.development
  networks:
    - garim_network
```

---

## 3.5 frontend 개발 Dockerfile 기준

개발용 `frontend/Dockerfile.dev`는 반드시 아래 조건을 지켜야 한다.

- `npm run build`를 수행하지 않는다.
- nginx 기반 image를 사용하지 않는다.
- frontend 컨테이너는 Vite dev server만 실행한다.
- `FROM nginx:alpine` 같은 정적 서빙 구조를 사용하지 않는다.

개발용 frontend Dockerfile 예시:

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
```

아래와 같은 구조는 개발용 frontend Dockerfile에 넣으면 안 된다.

```dockerfile
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
```

위 구조는 운영용에서도 현재 요구사항과 맞지 않을 수 있다. 운영에서도 nginx는 별도 서비스로 유지해야 한다.

---

## 3.6 nginx 개발 구성

nginx는 개발 환경에서도 별도 서비스로 둔다.

개발 환경 nginx는 정적 파일을 직접 서빙하지 않고 reverse proxy 역할만 한다.

- `/` 요청 → `final_frontend:3000`으로 proxy
- `/api` 요청 → `final_backend:8000`으로 proxy

WebSocket 또는 Vite HMR이 정상 동작하도록 nginx 설정에 upgrade 헤더를 포함한다.

`nginx/dev.conf` 예시:

```nginx
server {
    listen 80;
    server_name localhost;

    location /api/ {
        proxy_pass http://final_backend:8000/api/;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://final_frontend:3000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

필요하다면 Vite HMR용 경로나 WebSocket 처리도 현재 프로젝트 구조에 맞게 추가한다.

---

# 4. 운영 환경 구성

## 4.1 운영 환경 목표

운영용 Docker Compose 파일을 별도로 작성한다.

운영 환경에서도 아래 서비스를 하나의 Docker Compose 명령으로 실행할 수 있어야 한다.

- `final_db`
- `final_redis`
- `final_backend`
- `final_frontend`
- `final_nginx`

운영 환경에서도 nginx와 frontend는 별도 서비스로 분리한다.

운영 환경에서는 backend와 frontend 모두 volume으로 소스코드를 연결하지 않는다.

운영 환경에서는 backend와 frontend 모두 Dockerfile을 통해 image build 후 실행한다.

- backend는 `backend/Dockerfile.prod` 사용
- frontend는 `frontend/Dockerfile.prod` 사용

운영 환경 구조는 다음과 같아야 한다.

```text
브라우저
  ↓
final_nginx
  ├── /      → frontend dist 정적 파일 서빙
  └── /api   → final_backend:8000
```

운영 환경에서는 uploads, logs, database data처럼 실제 보존이 필요한 데이터 디렉토리에만 volume을 사용한다.

---

## 4.2 backend 운영 구성

운영 backend는 `backend/Dockerfile.prod`를 통해 image build 후 실행한다.

운영 backend는 source volume을 사용하지 않는다.

운영 backend는 `uvicorn --reload` 없이 실행해야 한다.

예시:

```yaml
final_backend:
  build:
    context: ./backend
    dockerfile: Dockerfile.prod
  container_name: final_backend
  command: uvicorn main:app --host 0.0.0.0 --port 8000
  env_file:
    - .env.production
  depends_on:
    - final_db
    - final_redis
  networks:
    - garim_network
```

주의:

- 실제 실행 경로와 app import 경로는 현재 프로젝트 구조에 맞게 확인해서 수정한다.
- 운영에서는 `--reload`를 사용하지 않는다.

---

## 4.3 backend 운영 Dockerfile 기준

`backend/Dockerfile.prod`는 운영 실행에 필요한 파일을 image 안에 복사하고, 의존성을 설치한 뒤 일반 실행 모드로 구동되도록 작성한다.

예시:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

주의:

- 실제 Python 버전은 프로젝트 기준에 맞춘다.
- 실제 FastAPI app import 경로는 프로젝트 구조에 맞춘다.
- 운영용 Dockerfile에서는 `--reload`를 사용하지 않는다.

---

## 4.4 frontend 운영 구성

운영용 `frontend/Dockerfile.prod`는 `npm run build`를 수행해서 dist를 생성해야 한다.

하지만 frontend 컨테이너가 nginx로 직접 실행되면 안 된다.

현재 요구사항에서는 nginx를 별도 서비스로 유지해야 하므로, frontend 컨테이너는 build 결과물인 dist를 생성하는 역할만 담당한다.

운영 환경 구조:

- `final_frontend`: frontend 소스를 build해서 dist 생성
- `final_nginx`: frontend build 결과물인 dist를 서빙
- `final_nginx`: `/` 요청은 frontend build 결과물로 처리
- `final_nginx`: `/api` 요청은 `final_backend`로 proxy

frontend 원본 소스가 nginx를 통해 직접 노출되지 않도록 하고, 운영 nginx에는 dist 결과물만 연결한다.

---

## 4.5 frontend 운영 Dockerfile 기준

운영용 `frontend/Dockerfile.prod`는 build 결과물인 `dist`를 생성해야 한다.

예시:

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

RUN npm run build

CMD ["sh", "-c", "ls -al dist && tail -f /dev/null"]
```

중요:

아래 같은 구조는 운영용 frontend Dockerfile에서 사용하지 않는다.

```dockerfile
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
```

이 구조는 frontend 컨테이너가 nginx 역할까지 하게 만들 수 있으므로, 현재 요구사항인 `frontend`와 `nginx` 별도 서비스 분리와 맞지 않는다.

---

## 4.6 frontend dist 공유 방식

운영에서 nginx가 dist를 읽을 수 있도록 named volume을 사용하는 방식으로 구성한다.

예시:

```yaml
volumes:
  frontend_dist:
```

```yaml
final_frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile.prod
  container_name: final_frontend
  env_file:
    - .env.production
  volumes:
    - frontend_dist:/app/dist
  command: sh -c "npm run build && cp -r dist/* /app/dist && tail -f /dev/null"
  networks:
    - garim_network
```

다만 위 예시는 참고용이다. 더 안정적인 방식이 있다면 그 방식으로 구성해도 된다.

반드시 지켜야 할 조건은 아래와 같다.

- frontend 원본 소스는 운영 nginx에 직접 연결하지 않는다.
- nginx는 build 결과물인 dist만 서빙한다.
- frontend와 nginx는 별도 서비스로 유지한다.
- 운영 환경에서는 `./frontend:/app` 같은 source volume mount를 사용하지 않는다.

---

## 4.7 nginx 운영 구성

운영 환경 nginx는 별도 서비스로 구성한다.

운영 nginx는 다음 역할을 한다.

- `/` 요청 → frontend dist 정적 파일 서빙
- `/api` 요청 → `final_backend:8000`으로 proxy

`nginx/prod.conf` 예시:

```nginx
server {
    listen 80;
    server_name localhost;

    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://final_backend:8000/api/;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

운영용 docker-compose의 nginx 서비스는 frontend dist volume을 읽도록 구성한다.

예시:

```yaml
final_nginx:
  image: nginx:alpine
  container_name: final_nginx
  ports:
    - "80:80"
  volumes:
    - frontend_dist:/usr/share/nginx/html:ro
    - ./nginx/prod.conf:/etc/nginx/conf.d/default.conf:ro
  depends_on:
    - final_backend
    - final_frontend
  networks:
    - garim_network
```

---

# 5. 환경변수 분리

개발/운영 환경변수를 분리한다.

아래 파일을 기준으로 작성한다.

- `.env.development`
- `.env.production`

Docker Compose에서 각 환경에 맞는 `env_file`을 참조하도록 한다.

환경에 따라 달라질 수 있는 값은 개발/운영 기준으로 분리한다.

예시:

- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DATABASE_URL`
- `REDIS_URL`
- `API URL`
- `CORS_ORIGINS`
- `COOKIE_SECURE`
- `COOKIE_SAMESITE`
- `ENV`
- `DEBUG`

Docker 내부 통신에서는 compose service name 기준으로 연결되게 한다.

예시:

```env
DB_HOST=final_db
REDIS_URL=redis://final_redis:6379/0
```

개발 환경 예시:

```env
ENV=development
DEBUG=true
DB_HOST=final_db
REDIS_URL=redis://final_redis:6379/0
CORS_ORIGINS=http://localhost,http://localhost:3000,http://127.0.0.1
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
```

운영 환경 예시:

```env
ENV=production
DEBUG=false
DB_HOST=final_db
REDIS_URL=redis://final_redis:6379/0
CORS_ORIGINS=https://실제도메인
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
```

주의:

- 실제 변수명은 현재 backend/frontend 코드에서 사용하는 이름을 확인해서 맞춘다.
- 민감한 운영 값은 실제 배포 시 Git에 커밋하지 않도록 한다.

---

# 6. API 경로 기준

기존 backend/frontend 코드가 사용하는 API 경로가 `/api/...` 기준으로 동작하도록 nginx proxy 설정과 맞춘다.

프론트엔드에서 API 요청은 가능하면 `/api/...` 상대 경로 기준으로 동작하게 한다.

예시:

```js
axios.get("/api/...");
```

nginx는 `/api` 요청을 backend로 proxy해야 한다.

개발/운영 모두 같은 API 경로 기준으로 동작하게 한다.

주의:

- backend가 실제로 `/api` prefix를 포함하고 있다면 nginx에서 `/api/`를 유지해서 proxy한다.
- backend 라우터가 `/api` prefix 없이 구성되어 있다면 nginx의 `proxy_pass` 경로를 프로젝트 구조에 맞게 조정한다.

---

# 7. 데이터 volume 기준

개발 환경에서는 편의를 위해 필요한 volume을 사용할 수 있다.

운영 환경에서는 소스코드 volume을 사용하지 않는다.

운영 환경에서 volume을 사용할 수 있는 항목은 실제 보존이 필요한 데이터로 제한한다.

예시:

- Postgres data
- Redis data가 필요한 경우
- uploads
- logs
- processed files
- 기타 사용자가 업로드하거나 시스템이 생성한 보존 대상 파일

운영에서 아래와 같은 source volume mount는 사용하지 않는다.

```yaml
- ./backend:/app
- ./frontend:/app
```

---

# 8. 실행 명령 문서화

각 환경별 실행 명령을 README 또는 별도 문서에 정리한다.

## 8.1 개발 실행

```bash
docker compose --env-file .env.development -f docker-compose.dev.yml up -d --build
```

## 8.2 개발 로그 확인

```bash
docker compose --env-file .env.development -f docker-compose.dev.yml logs -f
```

## 8.3 개발 종료

```bash
docker compose --env-file .env.development -f docker-compose.dev.yml down
```

## 8.4 운영 실행

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

## 8.5 운영 로그 확인

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f
```

## 8.6 운영 종료

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml down
```

---

# 9. 체크리스트 작성

작업 후 개발 환경과 운영 환경 각각에서 정상 동작 여부를 확인할 수 있는 체크리스트를 작성한다.

## 9.1 개발 환경 체크리스트

- [ ] `docker-compose.dev.yml`로 전체 서비스 실행 가능
- [ ] `final_db` 컨테이너 정상 실행
- [ ] `final_redis` 컨테이너 정상 실행
- [ ] `final_backend` 컨테이너 정상 실행
- [ ] `final_frontend` 컨테이너에서 Vite dev server 정상 실행
- [ ] `final_nginx` 컨테이너 정상 실행
- [ ] 브라우저에서 nginx 주소로 접속 시 frontend 화면 표시
- [ ] `/api/...` 요청이 nginx를 통해 backend로 proxy됨
- [ ] backend가 db에 연결됨
- [ ] backend가 redis에 연결됨
- [ ] backend 코드 수정 시 uvicorn reload 반영
- [ ] frontend 코드 수정 시 Vite HMR 또는 reload 반영
- [ ] Vite HMR WebSocket이 nginx proxy를 통과해서 정상 동작

## 9.2 운영 환경 체크리스트

- [ ] `docker-compose.prod.yml`로 전체 서비스 실행 가능
- [ ] backend가 `Dockerfile.prod`를 통해 build됨
- [ ] frontend가 `Dockerfile.prod`를 통해 build됨
- [ ] 운영 backend가 `--reload` 없이 실행됨
- [ ] 운영 frontend 원본 소스가 nginx에 직접 노출되지 않음
- [ ] nginx가 frontend dist 결과물만 서빙함
- [ ] `/` 요청 시 정적 frontend 화면이 표시됨
- [ ] `/api/...` 요청이 backend로 proxy됨
- [ ] backend가 db에 연결됨
- [ ] backend가 redis에 연결됨
- [ ] uploads, logs, database data 등 보존 대상 volume이 정상 유지됨

---

# 10. 개발/운영 역할 차이 요약

## 개발 환경

- backend: `Dockerfile.dev` build + source volume mount + `uvicorn --reload`
- frontend: `Dockerfile.dev` build + source volume mount + Vite dev server
- nginx: reverse proxy
- frontend build 결과물을 nginx로 서빙하지 않음
- 코드 수정 시 빠르게 반영되는 구조

## 운영 환경

- backend: `Dockerfile.prod` build + 일반 실행
- frontend: `Dockerfile.prod` build + dist 생성
- nginx: dist 정적 서빙 + `/api` proxy
- backend/frontend source volume mount 금지
- 보존 데이터에만 volume 사용

---

# 11. 작업 시 주의사항

1. 기존 코드 동작을 깨지 않도록 최소 수정으로 진행한다.
2. 기존 서비스명과 network 구조는 가능하면 유지한다.
3. 개발 환경과 운영 환경의 역할 차이를 반드시 지킨다.
4. 개발 환경에서도 backend/frontend는 각각 Dockerfile.dev를 명시적으로 읽어서 build한다.
5. 개발 frontend Dockerfile에는 `npm run build`나 nginx 실행 구조를 넣지 않는다.
6. 운영 frontend Dockerfile은 dist를 생성하되, frontend 컨테이너가 nginx 역할을 하지 않게 한다.
7. nginx는 개발/운영 모두에서 별도 서비스로 유지한다.
8. 운영 nginx는 frontend 원본 소스가 아니라 dist 결과물만 서빙한다.
9. `/api/...` 경로가 개발/운영 모두 동일하게 동작하도록 proxy 설정을 맞춘다.
10. 실제 app import 경로, package manager, port, 환경변수명은 현재 프로젝트 구조를 확인해서 맞춘다.

---

# 12. Codex 작업 요청 요약

아래 기준으로 실제 파일을 생성하거나 수정해줘.

- `docker-compose.dev.yml` 생성 또는 수정
- `docker-compose.prod.yml` 생성 또는 수정
- `.env.development` 생성 또는 수정
- `.env.production` 생성 또는 수정
- `nginx/dev.conf` 생성 또는 수정
- `nginx/prod.conf` 생성 또는 수정
- `backend/Dockerfile.dev` 생성 또는 수정
- `backend/Dockerfile.prod` 생성 또는 수정
- `frontend/Dockerfile.dev` 생성 또는 수정
- `frontend/Dockerfile.prod` 생성 또는 수정
- README 또는 별도 문서에 실행 명령과 체크리스트 추가

작업 후 아래 흐름이 모두 정상 동작해야 한다.

개발:

```text
브라우저 → final_nginx → final_frontend Vite dev server
브라우저 → final_nginx → final_backend → final_db/final_redis
```

운영:

```text
브라우저 → final_nginx → frontend dist 정적 파일
브라우저 → final_nginx → final_backend → final_db/final_redis
```
