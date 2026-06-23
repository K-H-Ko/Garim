from uuid import UUID

from fastapi import Body, Cookie, Path, status
from fastapi.responses import JSONResponse

from services import auth, setting, users, redis_store


def delete_my_account(access_token: str | None = Cookie(default=None)):
    current_user = auth.authenticate_access_token(access_token)
    users.mark_user_deleted(current_user["id"])
    redis_store.delete_session(current_user["session_id"])

    response = JSONResponse(
        {"message": "계정 삭제 신청이 완료되었습니다."},
        status_code=status.HTTP_200_OK,
    )
    auth.delete_auth_cookies(response)
    return response


def get_my_setting(access_token: str | None = Cookie(default=None)):
    current_user = auth.authenticate_access_token(access_token)
    data = setting.get_or_create_setting(current_user["id"])
    return JSONResponse(
        {
            "data": data,
            "message": "환경설정 조회",
        },
        status_code=status.HTTP_200_OK,
    )


def get_my_login_histories(access_token: str | None = Cookie(default=None)):
    current_user = auth.authenticate_access_token(access_token)
    histories = users.get_login_histories(current_user["id"], limit=5)
    return JSONResponse(
        {
            "data": histories,
            "message": "최근 로그인 이력 조회 성공",
        },
        status_code=status.HTTP_200_OK,
    )


def update_my_setting(
    payload: dict = Body(...),
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    data = setting.update_setting(
        current_user["id"],
        bool(payload.get("email_notification")),
        bool(payload.get("browser_notification")),
        bool(payload.get("data_usage_consent")),
    )
    return JSONResponse(
        {
            "data": data,
            "message": "환경설정 수정 완료",
        },
        status_code=status.HTTP_200_OK,
    )


async def get_setting(
    user_id: UUID = Path(
        ...,
        description="유저 ID"
    )
):
    try:
        data = setting.get_setting(user_id)

        if not data:
            return JSONResponse(
                {"message": "설정 정보가 없습니다."},
                status_code=status.HTTP_404_NOT_FOUND
            )

        return JSONResponse(
            {
                "data": data,
                "message": "환경설정 조회"
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            {"message": "조회 실패 " + str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


async def update_setting(
    user_id: UUID = Path(
        ...,
        description="유저 ID"
    ),

    email_notification: bool = Body(
        ...,
        example=True,
        description="이메일 알림 여부"
    ),

    browser_notification: bool = Body(
        ...,
        example=True,
        description="브라우저 알림 여부"
    ),

    data_usage_consent: bool = Body(
        ...,
        example=False,
        description="학습 데이터 활용 동의 여부"
    )
):
    try:
        data = setting.update_setting(
            user_id,
            email_notification,
            browser_notification,
            data_usage_consent,
        )

        return JSONResponse(
            {
                "data": data,
                "message": "환경설정 수정 완료"
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            {"message": "수정 실패 " + str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
