import hashlib
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from utils.database import SessionLocal

CHUNK_UPLOAD_EXPIRE_HOURS = int(os.getenv("CHUNK_UPLOAD_EXPIRE_HOURS", "24"))


def get_upload_dir():
    return Path(os.getenv("UPLOAD_DIR", "storage/uploads")).resolve()


def get_temp_base_dir():
    return Path(os.getenv("TEMP_DIR", "storage/temp")).resolve()


def sanitize_filename(filename):
    return Path(filename or "upload.bin").name


def _is_expired(expires_at) -> bool:
    if not expires_at:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def _mark_upload_status(db, upload_id: str, upload_status: str) -> None:
    db.execute(
        text("""
            UPDATE uploads
            SET status = :status,
                updated_at = now()
            WHERE upload_id = :upload_id
        """),
        {"upload_id": upload_id, "status": upload_status},
    )


# ── 허용 포맷 정의 ──────────────────────────────────────────────────────
# 대분류(media_type) → 실제로 허용하는 파일 확장자(filetype 라이브러리 기준) 목록.
# filetype.guess()가 반환하는 kind.extension 값과 매칭한다.
# (예: jpeg 파일도 filetype은 'jpg'로 반환)
ALLOWED_TYPES = {
    "image": {"jpg", "png", "webp"},
    "video": {"mp4", "avi", "mov", "mkv", "m4v", "webm"},
}


def _verify_real_media_type(db, upload_id: str, final_path, declared_media_type: str) -> str:
    """병합된 실제 파일의 매직 바이트를 읽어 진짜 미디어 타입을 판별·검증한다.

    - 확장자가 아니라 파일 시그니처(매직 바이트)로 판별하므로,
      영상을 .jpg로 위조해 올려도 실제 형식을 정확히 잡아낸다.
    - 신고값(declared_media_type)과 실제 대분류가 다르거나,
      허용 목록 밖 포맷이면 업로드를 거부(ValueError)하고 병합 파일을 정리한다.

    반환: 검증을 통과한 실제 미디어 대분류 ('image' | 'video')
    """
    import filetype  # 지연 import — 업로드 경로에서만 필요

    # 거부 시 병합 파일 삭제 + 상태 'failed' 마킹 후 예외 발생시키는 내부 헬퍼
    def _reject(message: str):
        try:
            Path(final_path).unlink(missing_ok=True)
        except Exception:
            pass
        _mark_upload_status(db, upload_id, "failed")
        db.commit()
        raise ValueError(message)

    # 1) 실제 파일 시그니처로 형식 추정
    kind = filetype.guess(str(final_path))
    if kind is None:
        # 시그니처를 인식할 수 없음 → 지원하지 않는/손상된 파일로 간주
        _reject("업로드한 파일의 형식을 인식할 수 없습니다. "
                "지원하는 이미지(jpg/png/webp) 또는 영상(mp4/avi/mov/mkv) 파일인지 확인 후 다시 업로드해주세요.")

    real_ext   = kind.extension              # 예: 'jpg', 'mp4'
    real_major = (kind.mime or "").split("/")[0].lower()  # 예: 'image', 'video'

    # 2) 허용 목록(대분류 + 확장자) 안에 드는지 확인
    if real_major not in ALLOWED_TYPES or real_ext not in ALLOWED_TYPES[real_major]:
        _reject(f"업로드한 파일이 실제로는 '{real_ext}' 형식으로 확인됩니다. "
                f"지원하지 않는 형식이므로 업로드를 거부합니다. "
                f"이미지(jpg/png/webp) 또는 영상(mp4/avi/mov/mkv) 파일로 다시 업로드해주세요.")

    # 3) 신고한 대분류와 실제 대분류가 일치하는지 확인 (영상↔이미지 위조 차단)
    if declared_media_type in ("image", "video") and declared_media_type != real_major:
        declared_label = "이미지" if declared_media_type == "image" else "영상"
        real_label     = "이미지" if real_major == "image" else "영상"
        _reject(f"{declared_label}으로 업로드하셨지만, 해당 파일의 실제 형식은 "
                f"'{real_ext}'({real_label})로 확인됩니다. "
                f"확장자만 변경된 파일은 처리할 수 없습니다. 올바른 파일로 다시 업로드해주세요.")

    # 통과: 검증된 실제 대분류 반환
    return real_major


def init_upload(
    user_id: str,
    original_filename: str,
    content_type: str,
    file_size: int,
    media_type: str,
    chunk_size: int,
    total_chunks: int,
) -> dict:
    upload_id = str(uuid4())
    original_name = sanitize_filename(original_filename)
    stored_filename = f"{upload_id}_{original_name}"
    stored_path = str(get_upload_dir() / stored_filename)
    temp_dir_path = str(get_temp_base_dir() / upload_id)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=CHUNK_UPLOAD_EXPIRE_HOURS)

    db = SessionLocal()
    try:
        db.execute(
            text("""
                INSERT INTO uploads (
                    upload_id, user_id, original_filename, stored_filename,
                    stored_path, content_type, file_size, media_type,
                    chunk_size, total_chunks, uploaded_chunks,
                    temp_dir_path, status, expires_at
                ) VALUES (
                    :upload_id, :user_id, :original_filename, :stored_filename,
                    :stored_path, :content_type, :file_size, :media_type,
                    :chunk_size, :total_chunks, 0,
                    :temp_dir_path, 'initialized', :expires_at
                )
            """),
            {
                "upload_id": upload_id,
                "user_id": user_id,
                "original_filename": original_name,
                "stored_filename": stored_filename,
                "stored_path": stored_path,
                "content_type": content_type,
                "file_size": file_size,
                "media_type": media_type,
                "chunk_size": chunk_size,
                "total_chunks": total_chunks,
                "temp_dir_path": temp_dir_path,
                "expires_at": expires_at,
            },
        )
        db.commit()
    finally:
        db.close()

    return {
        "upload_id": upload_id,
        "status": "initialized",
        "total_chunks": total_chunks,
        "chunk_size": chunk_size,
        "expires_at": expires_at.isoformat(),
    }


def save_chunk(
    upload_id: str,
    user_id: str,
    chunk_index: int,
    chunk_file,
    chunk_hash: str | None = None,
) -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text("""
                SELECT user_id, status, total_chunks, uploaded_chunks, temp_dir_path, expires_at
                FROM uploads
                WHERE upload_id = :upload_id
            """),
            {"upload_id": upload_id},
        ).fetchone()

        if not row:
            raise ValueError("업로드를 찾을 수 없습니다.")

        m = row._mapping
        if str(m["user_id"]) != user_id:
            raise PermissionError("접근 권한이 없습니다.")
        if _is_expired(m["expires_at"]):
            _mark_upload_status(db, upload_id, "expired")
            db.commit()
            raise ValueError("upload expired")
        if m["status"] not in ("initialized", "uploading"):
            raise ValueError(f"업로드할 수 없는 상태입니다: {m['status']}")
        if chunk_index < 0 or chunk_index >= m["total_chunks"]:
            raise ValueError(f"유효하지 않은 chunk_index입니다. (0 ~ {m['total_chunks'] - 1})")

        existing = db.execute(
            text("""
                SELECT upload_chunk_id FROM upload_chunks
                WHERE upload_id = :upload_id AND chunk_index = :chunk_index
            """),
            {"upload_id": upload_id, "chunk_index": chunk_index},
        ).fetchone()

        if existing:
            return {
                "upload_id": upload_id,
                "chunk_index": chunk_index,
                "status": "already_uploaded",
                "uploaded_chunks": m["uploaded_chunks"],
                "total_chunks": m["total_chunks"],
            }

        temp_dir = Path(m["temp_dir_path"])
        temp_dir.mkdir(parents=True, exist_ok=True)
        chunk_path = temp_dir / str(chunk_index)

        chunk_size = 0
        hasher = hashlib.sha256()
        with chunk_path.open("wb") as f:
            while data := chunk_file.file.read(1024 * 1024):
                chunk_size += len(data)
                hasher.update(data)
                f.write(data)

        computed_hash = hasher.hexdigest()
        if chunk_hash and computed_hash.lower() != chunk_hash.strip().lower():
            chunk_path.unlink(missing_ok=True)
            raise ValueError("chunk hash mismatch")

        inserted_chunk_id = db.execute(
            text("""
                INSERT INTO upload_chunks
                    (upload_chunk_id, upload_id, chunk_index, chunk_size, chunk_hash, storage_path, status)
                VALUES
                    (gen_random_uuid(), :upload_id, :chunk_index, :chunk_size, :chunk_hash, :storage_path, 'uploaded')
                ON CONFLICT (upload_id, chunk_index) DO NOTHING
                RETURNING upload_chunk_id
            """),
            {
                "upload_id": upload_id,
                "chunk_index": chunk_index,
                "chunk_size": chunk_size,
                "chunk_hash": chunk_hash or computed_hash,
                "storage_path": str(chunk_path),
            },
        ).scalar()

        if not inserted_chunk_id:
            chunk_path.unlink(missing_ok=True)
            db.commit()
            return {
                "upload_id": upload_id,
                "chunk_index": chunk_index,
                "status": "already_uploaded",
                "uploaded_chunks": m["uploaded_chunks"],
                "total_chunks": m["total_chunks"],
            }

        db.execute(
            text("""
                UPDATE uploads
                SET uploaded_chunks = uploaded_chunks + 1,
                    status = 'uploading',
                    updated_at = now()
                WHERE upload_id = :upload_id
            """),
            {"upload_id": upload_id},
        )

        db.commit()

        return {
            "upload_id": upload_id,
            "chunk_index": chunk_index,
            "status": "uploaded",
            "uploaded_chunks": m["uploaded_chunks"] + 1,
            "total_chunks": m["total_chunks"],
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_upload_status(upload_id: str, user_id: str) -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text("""
                SELECT user_id, status, total_chunks, uploaded_chunks,
                       expires_at, file_hash, stored_path
                FROM uploads
                WHERE upload_id = :upload_id
            """),
            {"upload_id": upload_id},
        ).fetchone()

        if not row:
            raise ValueError("업로드를 찾을 수 없습니다.")

        m = row._mapping
        if str(m["user_id"]) != user_id:
            raise PermissionError("접근 권한이 없습니다.")

        if _is_expired(m["expires_at"]) and m["status"] not in ("uploaded", "cancelled", "failed", "expired"):
            _mark_upload_status(db, upload_id, "expired")
            db.commit()
            m = dict(m)
            m["status"] = "expired"

        total = m["total_chunks"] or 0
        done = m["uploaded_chunks"] or 0
        progress = round(done / total * 100) if total > 0 else 0

        missing_chunks = []
        if m["status"] not in ("uploaded", "cancelled", "failed") and total > 0:
            uploaded_indices = {
                r._mapping["chunk_index"]
                for r in db.execute(
                    text("SELECT chunk_index FROM upload_chunks WHERE upload_id = :upload_id"),
                    {"upload_id": upload_id},
                ).fetchall()
            }
            missing_chunks = sorted(set(range(total)) - uploaded_indices)

        return {
            "upload_id": upload_id,
            "status": m["status"],
            "total_chunks": total,
            "uploaded_chunks": done,
            "progress": progress,
            "missing_chunks": missing_chunks,
            "expires_at": m["expires_at"].isoformat() if m["expires_at"] else None,
            "file_hash": m["file_hash"],
            "stored_path": m["stored_path"] if m["status"] == "uploaded" else None,
        }
    finally:
        db.close()


def complete_upload(upload_id: str, user_id: str) -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text("""
                SELECT user_id, status, total_chunks, uploaded_chunks,
                       temp_dir_path, stored_path, file_hash, expires_at, media_type
                FROM uploads
                WHERE upload_id = :upload_id
            """),
            {"upload_id": upload_id},
        ).fetchone()

        if not row:
            raise ValueError("업로드를 찾을 수 없습니다.")

        m = row._mapping
        if str(m["user_id"]) != user_id:
            raise PermissionError("접근 권한이 없습니다.")

        if _is_expired(m["expires_at"]) and m["status"] != "uploaded":
            _mark_upload_status(db, upload_id, "expired")
            db.commit()
            raise ValueError("upload expired")

        if m["status"] == "uploaded":
            return {
                "upload_id": upload_id,
                "status": "uploaded",
                "file_hash": m["file_hash"],
                "stored_path": m["stored_path"],
            }

        if m["status"] not in ("uploading",):
            raise ValueError(f"병합할 수 없는 상태입니다: {m['status']}")

        if m["uploaded_chunks"] != m["total_chunks"]:
            raise ValueError(
                f"모든 chunk가 업로드되지 않았습니다. "
                f"({m['uploaded_chunks']}/{m['total_chunks']})"
            )

        chunks = db.execute(
            text("""
                SELECT chunk_index, storage_path
                FROM upload_chunks
                WHERE upload_id = :upload_id
                ORDER BY chunk_index ASC
            """),
            {"upload_id": upload_id},
        ).fetchall()

        if len(chunks) != m["total_chunks"]:
            raise ValueError(
                f"upload_chunks 레코드 수가 일치하지 않습니다. "
                f"({len(chunks)}/{m['total_chunks']})"
            )

        final_path = Path(m["stored_path"])
        final_path.parent.mkdir(parents=True, exist_ok=True)

        hasher = hashlib.sha256()
        with final_path.open("wb") as out_f:
            for chunk_row in chunks:
                chunk_path = Path(chunk_row._mapping["storage_path"])
                with chunk_path.open("rb") as in_f:
                    while data := in_f.read(1024 * 1024):
                        hasher.update(data)
                        out_f.write(data)

        file_hash = hasher.hexdigest()

        # ── 실제 파일 타입 검증 (매직 바이트 기반) ──────────────────────
        # 확장자/신고값(media_type)만 믿으면 영상을 .jpg로 위조해 올릴 수 있다.
        # 병합된 실제 파일의 시그니처(매직 바이트)를 읽어 진짜 형식을 판별하고,
        # 신고값과 다르거나 허용 외 포맷이면 업로드를 거부한다.
        declared_media_type = (m.get("media_type") or "").lower()
        verified_media_type = _verify_real_media_type(
            db, upload_id, final_path, declared_media_type
        )
        # 통과 시 신고값 대신 '검증된 실제 타입'을 이후 로직/DB에 사용
        media_type = verified_media_type
        thumbnail_path = None
        if media_type.startswith("image"):
            thumbnail_path = str(final_path)
        elif media_type.startswith("video"):
            thumb_jpg = final_path.with_suffix(".jpg")
            try:
                import imageio_ffmpeg
                import subprocess as _sp
                ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
                cmd = [
                    ffmpeg, "-y",
                    "-i", str(final_path),
                    "-vframes", "1",
                    "-q:v", "2",
                    "-vf", "scale='min(640,iw)':min'(360,ih)':force_original_aspect_ratio=decrease",
                    str(thumb_jpg)
                ]
                _sp.run(cmd, capture_output=True)
                if thumb_jpg.exists():
                    thumbnail_path = str(thumb_jpg)
            except Exception:
                pass

        db.execute(
            text("""
                UPDATE uploads
                SET status = 'uploaded',
                    merged_file_path = :merged_file_path,
                    file_hash = :file_hash,
                    thumbnail_path = :thumbnail_path,
                    media_type = :media_type,
                    updated_at = now()
                WHERE upload_id = :upload_id
            """),
            {
                "upload_id": upload_id,
                "merged_file_path": str(final_path),
                "file_hash": file_hash,
                "thumbnail_path": thumbnail_path,
                # 신고값이 아닌, 매직 바이트로 검증된 실제 타입을 확정 저장
                "media_type": media_type,
            },
        )

        db.commit()

        shutil.rmtree(Path(m["temp_dir_path"]), ignore_errors=True)

        return {
            "upload_id": upload_id,
            "status": "uploaded",
            "file_hash": file_hash,
            "stored_path": str(final_path),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def cancel_upload(upload_id: str, user_id: str) -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text("""
                SELECT user_id, status, temp_dir_path
                FROM uploads
                WHERE upload_id = :upload_id
            """),
            {"upload_id": upload_id},
        ).fetchone()

        if not row:
            raise ValueError("?낅줈?쒕? 李얠쓣 ???놁뒿?덈떎.")

        m = row._mapping
        if str(m["user_id"]) != user_id:
            raise PermissionError("?묎렐 沅뚰븳???놁뒿?덈떎.")
        if m["status"] == "uploaded":
            raise ValueError("uploaded files cannot be cancelled")

        _mark_upload_status(db, upload_id, "cancelled")
        db.commit()
        if m["temp_dir_path"]:
            shutil.rmtree(Path(m["temp_dir_path"]), ignore_errors=True)

        return {"upload_id": upload_id, "status": "cancelled"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_upload_file(upload_file):
    upload_dir = get_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)

    original_name = sanitize_filename(upload_file.filename)
    upload_id = uuid4().hex
    stored_path = upload_dir / f"{upload_id}_{original_name}"

    size = 0
    with stored_path.open("wb") as buffer:
        while chunk := upload_file.file.read(1024 * 1024):
            size += len(chunk)
            buffer.write(chunk)

    return {
        "upload_id": upload_id,
        "filename": original_name,
        "content_type": upload_file.content_type or "application/octet-stream",
        "size": size,
        "stored_path": str(stored_path),
    }
