import os
import logging

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# -----------------------------
# 1. DB 연결
# -----------------------------

logger = logging.getLogger(__name__)

DB_USER = os.getenv("DB_USER") or os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME") or os.getenv("POSTGRES_DB", "postgres")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# DB 객체 생성
engine = create_engine(
    DATABASE_URL
)

# 세션 관리 설정
SessionLocal = sessionmaker(
    autocommit=False, # 자동 커밋 설정
    autoflush=True,   # commit 이전 데이터를 db에 적용시킬지 여부 설정
    bind=engine
)

# -----------------------------
# 2. DB 세션 주입
# -----------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()