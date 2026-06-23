# 신고 접수 데이터를 DB에 저장하고 조회하는 SQL 쿼리 함수들을 모아둔 파일

from sqlalchemy import text

def create_abuse_report_query(conn, user_id, report_type, target_job_id, title, description):
    # 새로운 신고 데이터를 abuse_reports 테이블에 추가
    result = conn.execute(
        text("""
            INSERT INTO abuse_reports (
                reporter_user_id, report_type, target_job_id, title, description, status, created_at
            )
            VALUES (
                :user_id, :report_type, :target_job_id, :title, :description, 'received', NOW()
            )
            RETURNING report_id
        """),
        {
            "user_id": user_id,
            "report_type": report_type,
            "target_job_id": target_job_id,
            "title": title,
            "description": description,
        },
    ).fetchone()
    
    return str(result._mapping["report_id"] if hasattr(result, "_mapping") else result["report_id"])

def get_abuse_reports_query(conn, limit=50, offset=0):
    # 접수된 신고 목록을 최신순으로 조회
    return conn.execute(
        text("""
            SELECT report_id as id, reporter_user_id as user_id, report_type, target_job_id, title, description, status, created_at
            FROM abuse_reports
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"limit": limit, "offset": offset},
    ).fetchall()
