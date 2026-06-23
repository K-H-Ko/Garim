from sqlalchemy import text

from utils.database import engine


def create_post_query(conn, title, content):
    result = conn.execute(
        text("""
            INSERT INTO posts (title, content, created_at, updated_at)
            VALUES (:title, :content, NOW(), NULL)
        """),
        {"title": title, "content": content},
    )
    return result.lastrowid


def get_post_by_id_query(conn, post_id):
    return conn.execute(
        text("""
            SELECT post_id, title, content, created_at, updated_at
            FROM posts
            WHERE post_id = :post_id
        """),
        {"post_id": post_id},
    ).fetchone()


def get_posts_query(conn, size, offset):
    return conn.execute(
        text("""
            SELECT post_id, title, content, created_at, updated_at
            FROM posts
            ORDER BY post_id DESC
            LIMIT :size OFFSET :offset
        """),
        {"size": size, "offset": offset},
    ).fetchall()


def exists_post_query(conn, post_id):
    return conn.execute(
        text("""
            SELECT post_id
            FROM posts
            WHERE post_id = :post_id
        """),
        {"post_id": post_id},
    ).fetchone()


def update_post_query(conn, post_id, title, content):
    conn.execute(
        text("""
            UPDATE posts
            SET title = :title,
                content = :content,
                updated_at = NOW()
            WHERE post_id = :post_id
        """),
        {
            "post_id": post_id,
            "title": title,
            "content": content,
        },
    )


def delete_post_query(conn, post_id):
    conn.execute(
        text("""
            DELETE FROM posts
            WHERE post_id = :post_id
        """),
        {"post_id": post_id},
    )