from fastapi import APIRouter

from controllers import setting

router = APIRouter(tags=["settings"])

router.add_api_route(
    "/me",
    setting.delete_my_account,
    methods=["DELETE"]
)

router.add_api_route(
    "/me",
    setting.get_my_setting,
    methods=["GET"]
)

router.add_api_route(
    "/me/login-histories",
    setting.get_my_login_histories,
    methods=["GET"]
)

router.add_api_route(
    "/me",
    setting.update_my_setting,
    methods=["PUT"]
)

router.add_api_route(
    "/{user_id}",
    setting.get_setting,
    methods=["GET"]
)

router.add_api_route(
    "/{user_id}",
    setting.update_setting,
    methods=["PUT"]
)

