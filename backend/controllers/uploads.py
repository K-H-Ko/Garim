from fastapi import Cookie, File, Header, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from services import auth, uploads

VALID_MEDIA_TYPES = {"video", "image", "audio"}


class InitUploadRequest(BaseModel):
    original_filename: str
    content_type: str
    file_size: int
    media_type: str
    chunk_size: int
    total_chunks: int

    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, v):
        if v not in VALID_MEDIA_TYPES:
            raise ValueError("media_type은 video, image, audio 중 하나여야 합니다.")
        return v

    @field_validator("file_size", "chunk_size", "total_chunks")
    @classmethod
    def validate_positive(cls, v):
        if v <= 0:
            raise ValueError("0보다 큰 값이어야 합니다.")
        return v


def init_upload_handler(
    body: InitUploadRequest,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = uploads.init_upload(
            user_id=str(current_user["id"]),
            original_filename=body.original_filename,
            content_type=body.content_type,
            file_size=body.file_size,
            media_type=body.media_type,
            chunk_size=body.chunk_size,
            total_chunks=body.total_chunks,
        )
        return JSONResponse(result, status_code=status.HTTP_201_CREATED)
    except Exception as exc:
        return JSONResponse(
            {"message": f"업로드 초기화에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def upload_chunk_handler(
    upload_id: str,
    chunk_index: int,
    file: UploadFile = File(...),
    x_chunk_hash: str | None = Header(default=None, alias="X-Chunk-Hash"),
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = uploads.save_chunk(
            upload_id=upload_id,
            user_id=str(current_user["id"]),
            chunk_index=chunk_index,
            chunk_file=file,
            chunk_hash=x_chunk_hash,
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return JSONResponse(
            {"message": f"chunk 업로드에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def complete_upload_handler(
    upload_id: str,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = uploads.complete_upload(
            upload_id=upload_id,
            user_id=str(current_user["id"]),
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return JSONResponse(
            {"message": f"chunk 병합에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def get_upload_status_handler(
    upload_id: str,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = uploads.get_upload_status(
            upload_id=upload_id,
            user_id=str(current_user["id"]),
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"상태 조회에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def cancel_upload_handler(
    upload_id: str,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = uploads.cancel_upload(
            upload_id=upload_id,
            user_id=str(current_user["id"]),
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return JSONResponse(
            {"message": f"upload cancel failed: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


async def create_upload(file: UploadFile = File(...)):
    try:
        data = uploads.save_upload_file(file)
        return JSONResponse(data, status_code=status.HTTP_201_CREATED)
    except Exception as exc:
        return JSONResponse(
            {"message": f"파일 업로드에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
