import uvicorn, os, logging, sys
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().with_name(".env"))

from fastapi import FastAPI, APIRouter
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from routes import payment

from core.logger import setup_logging
from routes import oauth, post, setting, uploads, admin, analysis, worker, subscription, report, notification

################## 초기 세팅 ######################
## 로거 기본 세팅
setup_logging()

logger = logging.getLogger(__name__)

logger.info("backend server is running...")

# local_worker 경로를 sys.path에 추가 (내부 모듈 import용)
_LOCAL_WORKER_DIR = Path(__file__).resolve().parent / "local_worker"
if str(_LOCAL_WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(_LOCAL_WORKER_DIR))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """서버 시작 시 로컬 워커와 파일 만료 삭제 스케줄러를 백그라운드 스레드로 자동 실행"""
    try:
        from core.worker_event import WORKER_EVENT
        from local_worker import start_background_worker
        start_background_worker(wake_event=WORKER_EVENT)
        logger.info("✅ local_worker 백그라운드 스레드 시작 (이벤트 기반)")
    except Exception as e:
        logger.warning(f"⚠️  local_worker 시작 실패 (서버는 정상 실행): {e}")
    try:
        from services.file_cleanup import start_cleanup_scheduler
        start_cleanup_scheduler()
    except Exception as e:
        logger.warning(f"⚠️  파일 만료 삭제 스케줄러 시작 실패 (서버는 정상 실행): {e}")
    yield
    # 서버 종료 시 daemon=True 스레드는 자동 종료됨


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://garim.shop",
        "http://www.garim.shop",
        "https://garim.shop",
        "https://www.garim.shop"
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(post.router, prefix="/posts")
api_v1.include_router(uploads.router, prefix="/uploads")
api_v1.include_router(oauth.router, prefix="/auth")
api_v1.include_router(setting.router, prefix="/settings")
api_v1.include_router(admin.router, prefix="/admin")
api_v1.include_router(analysis.router, prefix="/analysis")
api_v1.include_router(worker.router, prefix="/worker")
api_v1.include_router(payment.router, prefix="/payment")
api_v1.include_router(subscription.router, prefix="/subscriptions")
api_v1.include_router(report.router, prefix="/reports")
api_v1.include_router(notification.router, prefix="/notifications")

app.include_router(api_v1)

if __name__ == "__main__":
    uvicorn.run(
        "main:app",          # 모듈:앱 경로
        host=os.getenv("HOST"), 
        port=int(os.getenv("PORT")),
        reload=True,
    )
