import pandas as pd

from models import setting
from utils.database import engine


def get_setting(user_id):
    with engine.connect() as conn:
        row = setting.get_setting_query(conn, user_id)

    if not row:
        return None

    data = dict(row._mapping)
    
    data["user_id"] = str(data["user_id"])

    data["created_at"] = (
        pd.to_datetime(data["created_at"])
        .strftime("%Y-%m-%d %H:%M:%S")
    )

    if data["updated_at"]:
        data["updated_at"] = (
            pd.to_datetime(data["updated_at"])
            .strftime("%Y-%m-%d %H:%M:%S")
        )

    return data


def get_or_create_setting(user_id):
    with engine.begin() as conn:
        row = setting.get_setting_query(conn, user_id)
        if not row:
            setting.create_setting_query(conn, user_id)
            row = setting.get_setting_query(conn, user_id)

    if not row:
        return None

    result = dict(row._mapping)
    result["user_id"] = str(result["user_id"])

    if result.get("created_at"):
        result["created_at"] = result["created_at"].strftime("%Y-%m-%d %H:%M:%S")

    if result.get("updated_at"):
        result["updated_at"] = result["updated_at"].strftime("%Y-%m-%d %H:%M:%S")

    return result


def update_setting(
    user_id,
    email_notification,
    browser_notification,
    data_usage_consent,
):
    with engine.begin() as conn:

        row = setting.get_setting_query(conn, user_id)


        if not row:
            setting.create_setting_query(
                conn,
                user_id
            )

        setting.update_setting_query(
            conn,
            user_id,
            email_notification,
            browser_notification,
            data_usage_consent,
        )

        row = setting.get_setting_query(
            conn,
            user_id
        )

    result = dict(row._mapping)

    result["user_id"] = str(result["user_id"])

    if result.get("created_at"):
        result["created_at"] = result[
            "created_at"
        ].strftime("%Y-%m-%d %H:%M:%S")

    if result.get("updated_at"):
        result["updated_at"] = result[
            "updated_at"
        ].strftime("%Y-%m-%d %H:%M:%S")

    return result
