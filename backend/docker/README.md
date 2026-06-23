## Docker Compose (통합 환경) 사용법

DB, Redis뿐만 아니라 프론트엔드, 백엔드, Nginx까지 모두 통합되어 동작합니다.
명령어는 **프로젝트 최상위 폴더(`Human_Final_PJ-main`)**에서 실행해야 합니다.

1. **Docker Desktop 실행**
2. **컨테이너 빌드 및 백그라운드 실행**
   - `docker-compose -f docker-compose.dev.yml up -d --build`
   - 프론트, 백엔드, DB, Nginx 등 전체 서버를 한 번에 띄웁니다.
3. **특정 컨테이너 내부로 진입 (예: 백엔드)**
   - `docker exec -it final_backend bash`
   - (`final_frontend`, `final_db`, `final_redis`, `final_nginx` 등 이름 지정 가능)
4. **전체 컨테이너 종료 및 삭제**
   - `docker-compose -f docker-compose.dev.yml down`
   - 실행 중인 모든 컨테이너와 네트워크를 내리고 삭제합니다. (볼륨에 저장된 DB 데이터는 유지됨)

### 추가 유용한 명령어

- `docker ps` - 현재 실행되고 있는 컨테이너 목록 확인
- `docker ps -a` - 중지된 것을 포함하여 시스템에 존재하는 모든 컨테이너 확인
- `docker logs final_backend` - 백엔드 컨테이너의 로그 확인 (오류 추적 시 유용)
- `docker-compose -f docker-compose.dev.yml logs -f` - 실행 중인 전체 서비스 로그 실시간 확인
- `docker start [컨테이너명]` - 중지된 특정 컨테이너 실행
- `docker stop [컨테이너명]` - 실행 중인 특정 컨테이너 중지
