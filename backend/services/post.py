import pandas as pd

from models import post
from utils.database import engine

def create_post(title, content):
    with engine.begin() as conn:
        post_id = post.create_post_query(conn, title, content)
        row = post.get_post_by_id_query(conn, post_id)
    return dict(row._mapping)

def get_posts(page=1, size=10):
    offset = (page - 1) * size

    with engine.connect() as conn:
        rows = post.get_posts_query(conn, size, offset)

    df = pd.DataFrame(
        rows,
        columns=[
            "post_id",
            "title",
            "content",
            "created_at",
            "updated_at",
        ],
    )

    if not df.empty:
        df["created_at"] = (
            pd.to_datetime(df["created_at"])
            .dt.strftime("%Y-%m-%d %H:%M:%S")
        )

        df["updated_at"] = (
            pd.to_datetime(df["updated_at"])
            .dt.strftime("%Y-%m-%d %H:%M:%S")
        )

        df = df.where(pd.notnull(df), None)

    return df.to_dict(orient="records")

def get_post(post_id):
    with engine.connect() as conn:
        row = post.get_post_by_id_query(conn, post_id)

    if not row:
        return None

    return dict(row._mapping)


def exists_post(post_id):
    with engine.connect() as conn:
        row = post.exists_post_query(conn, post_id)

    return row is not None


def update_post(post_id, title, content):
    with engine.begin() as conn:
        post.update_post_query(conn, post_id, title, content)
        row = post.get_post_by_id_query(conn, post_id)

    return dict(row._mapping)


def delete_post(post_id):
    with engine.begin() as conn:
        post.delete_post_query(conn, post_id)