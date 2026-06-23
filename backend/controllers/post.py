from fastapi import Body, Path, Query, status
from fastapi.responses import JSONResponse

from services import post
async def create_post(
    title: str = Body(..., example="FastAPI 게시글 제목", description="게시글 제목"),
    content: str = Body(..., example="게시글 내용입니다.", description="게시글 내용")
):
    """
    게시글을 생성합니다.
    """
    try:
        res = post.create_post(title, content)
        res = f"게시글 생성: {title}"
        return JSONResponse(
            {"message": res},
            status_code=status.HTTP_201_CREATED
        )
    except Exception as e:
        return JSONResponse(
            {"message": "생성 실패 " + str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


async def get_posts(
    page: int = Query(1, ge=1, description="페이지 번호 (1부터 시작)", example=1),
    size: int = Query(10, ge=1, description="페이지당 게시글 수", example=10)
):
    try:
        data = post.get_posts(page, size)
        return JSONResponse(
            {
                "page": page,
                "size": size,
                "data": data,
                "message": "게시글 목록 조회"
            },
            status_code=status.HTTP_200_OK
        )
    except Exception as e:
        return JSONResponse(
            {"message": "조회 실패 " + str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

async def get_post(
    post_id: int = Path(..., ge=1, description="게시글 ID", example=1)
):
    try:
        data = post.get_post(post_id)
        return JSONResponse(
            {
                "data": data,
                "message": f"{post_id}번 게시글 조회"
            },
            status_code=status.HTTP_200_OK
        )
    except ValueError as e:
        return JSONResponse(
            {"message": str(e)},
            status_code=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return JSONResponse(
            {"message": "단건 조회 실패 " + str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
async def update_post(
    post_id: int = Path(..., ge=1, description="게시글 ID", example=1),
    title: str = Body(..., example="수정된 제목", description="수정할 게시글 제목"),
    content: str = Body(..., example="수정된 내용", description="수정할 게시글 내용")
):
    """
    게시글을 수정합니다.
    """
    try:
        data = post.update_post(post_id, title, content)
        return JSONResponse(
            {
                "data": data,
                "message": f"{post_id}번 게시글 수정"
            },
            status_code=status.HTTP_200_OK
        )
    except ValueError as e:
        return JSONResponse(
            {"message": str(e)},
            status_code=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return JSONResponse(
            {"message": "수정 실패 " + str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
async def delete_post(
    post_id: int = Path(..., ge=1, description="게시글 ID", example=1)
):
    """
    게시글을 삭제합니다.
    """
    try:
        data = post.delete_post(post_id)
        return JSONResponse(
            {
                "data": data,
                "message": f"{post_id}번 게시글 삭제"
            },
            status_code=status.HTTP_200_OK
        )
    except ValueError as e:
        return JSONResponse(
            {"message": str(e)},
            status_code=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return JSONResponse(
            {"message": "삭제 실패 " + str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
