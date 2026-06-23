from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
import pytz

KST = pytz.timezone("Asia/Seoul")

def get_analytics_data(db: Session, days: int = 30):
    now = datetime.now(KST)
    start_date = now - timedelta(days=days)
    prev_start_date = start_date - timedelta(days=days)

    # 1. 주요 지표 (현재 기간)
    current_metrics = db.execute(text("""
        SELECT 
            (SELECT COUNT(*) FROM analysis_jobs WHERE created_at >= :start_date) as total_jobs,
            (SELECT COUNT(*) FROM users WHERE created_at >= :start_date) as new_users,
            (SELECT AVG(duration_seconds) FROM analysis_jobs WHERE created_at >= :start_date AND status = 'completed') as avg_duration,
            (SELECT COUNT(*) FROM analysis_jobs WHERE created_at >= :start_date AND status = 'completed') as success_jobs,
            (SELECT COUNT(*) FROM analysis_jobs WHERE created_at >= :start_date AND status IN ('completed', 'failed')) as finished_jobs
    """), {"start_date": start_date}).fetchone()

    # 2. 주요 지표 (이전 기간) - 증감률 계산용
    prev_metrics = db.execute(text("""
        SELECT 
            (SELECT COUNT(*) FROM analysis_jobs WHERE created_at >= :prev_start_date AND created_at < :start_date) as prev_total_jobs,
            (SELECT COUNT(*) FROM users WHERE created_at >= :prev_start_date AND created_at < :start_date) as prev_new_users,
            (SELECT AVG(duration_seconds) FROM analysis_jobs WHERE created_at >= :prev_start_date AND created_at < :start_date AND status = 'completed') as prev_avg_duration,
            (SELECT COUNT(*) FROM analysis_jobs WHERE created_at >= :prev_start_date AND created_at < :start_date AND status = 'completed') as prev_success_jobs,
            (SELECT COUNT(*) FROM analysis_jobs WHERE created_at >= :prev_start_date AND created_at < :start_date AND status IN ('completed', 'failed')) as prev_finished_jobs
    """), {"start_date": start_date, "prev_start_date": prev_start_date}).fetchone()

    # 지표 가공
    total_jobs = current_metrics.total_jobs or 0
    prev_total_jobs = prev_metrics.prev_total_jobs or 0
    jobs_delta = round(((total_jobs - prev_total_jobs) / prev_total_jobs * 100) if prev_total_jobs > 0 else 100, 1) if total_jobs > 0 else 0

    new_users = current_metrics.new_users or 0
    prev_new_users = prev_metrics.prev_new_users or 0
    users_delta = round(((new_users - prev_new_users) / prev_new_users * 100) if prev_new_users > 0 else 100, 1) if new_users > 0 else 0

    avg_duration = round(current_metrics.avg_duration or 0, 1)
    prev_avg_duration = round(prev_metrics.prev_avg_duration or 0, 1)
    duration_delta = round(avg_duration - prev_avg_duration, 1)

    success_rate = round((current_metrics.success_jobs / current_metrics.finished_jobs * 100), 1) if current_metrics.finished_jobs > 0 else 0
    prev_success_rate = round((prev_metrics.prev_success_jobs / prev_metrics.prev_finished_jobs * 100), 1) if prev_metrics.prev_finished_jobs > 0 else 0
    success_delta = round(success_rate - prev_success_rate, 1)

    metrics = {
        "jobs": {"value": total_jobs, "delta": jobs_delta},
        "users": {"value": new_users, "delta": users_delta},
        "duration": {"value": avg_duration, "delta": duration_delta},
        "success_rate": {"value": success_rate, "delta": success_delta}
    }

    # 3. 일별 처리 건수 (차트용)
    daily_jobs_rs = db.execute(text("""
        SELECT DATE(created_at) as date, COUNT(*) as count 
        FROM analysis_jobs 
        WHERE created_at >= :start_date 
        GROUP BY DATE(created_at) 
        ORDER BY DATE(created_at)
    """), {"start_date": start_date}).fetchall()
    daily_jobs = [{"date": str(r.date), "count": r.count} for r in daily_jobs_rs]

    # 4. 제공자별 가입 비율
    providers_rs = db.execute(text("""
        SELECT provider, COUNT(*) as count 
        FROM oauth_accounts 
        WHERE linked_at >= :start_date 
        GROUP BY provider
    """), {"start_date": start_date}).fetchall()
    
    total_oauth = sum(r.count for r in providers_rs)
    providers = []
    for r in providers_rs:
        providers.append({
            "provider": r.provider.capitalize() if r.provider else "Unknown",
            "count": r.count,
            "pct": round((r.count / total_oauth * 100), 1) if total_oauth > 0 else 0
        })

    # 5. 요금제별 사용 현황
    # 구독이 없는 사용자는 Free로 간주, 구독이 있는 사용자는 해당 plan_name으로 간주
    # 서브쿼리로 사용자의 현재 요금제를 매핑한 후 집계
    plans_rs = db.execute(text("""
        WITH user_plans AS (
            SELECT 
                u.user_id,
                COALESCE(p.plan_name, 'Free') as plan_name
            FROM users u
            LEFT JOIN subscriptions s ON u.user_id = s.user_id AND s.status = 'active'
            LEFT JOIN plans p ON s.plan_id = p.plan_id
        )
        SELECT 
            up.plan_name,
            COUNT(DISTINCT up.user_id) as users_count,
            COUNT(j.job_id) as jobs_count,
            AVG(upl.file_size) as avg_size
        FROM user_plans up
        LEFT JOIN analysis_jobs j ON up.user_id = j.user_id AND j.created_at >= :start_date
        LEFT JOIN uploads upl ON j.upload_id = upl.upload_id
        GROUP BY up.plan_name
    """), {"start_date": start_date}).fetchall()

    total_plan_users = sum(r.users_count for r in plans_rs)
    plans = []
    for r in plans_rs:
        plans.append({
            "plan": r.plan_name,
            "users": f"{r.users_count:,}",
            "jobs": f"{r.jobs_count:,}",
            "avgSize": f"{round((r.avg_size or 0) / (1024*1024), 1)} MB" if r.avg_size else "0 MB",
            "pct": f"{round((r.users_count / total_plan_users * 100), 1) if total_plan_users > 0 else 0}%"
        })

    # 6. 처리 실패 유형
    errors_rs = db.execute(text("""
        SELECT 
            COALESCE(error_message, '기타 알 수 없는 오류') as error_type,
            COUNT(*) as count
        FROM analysis_jobs
        WHERE created_at >= :start_date AND status = 'failed'
        GROUP BY error_message
        ORDER BY count DESC
    """), {"start_date": start_date}).fetchall()

    total_errors = sum(r.count for r in errors_rs)
    errors = []
    for r in errors_rs:
        # 에러 메시지가 길면 앞부분만 자르기 (유형화)
        short_msg = r.error_type.split(':')[0] if ':' in r.error_type else r.error_type
        if len(short_msg) > 30:
            short_msg = short_msg[:30] + "..."
            
        # 동일한 short_msg가 이미 있으면 합산
        existing = next((e for e in errors if e["type"] == short_msg), None)
        if existing:
            existing["count"] += r.count
            existing["pct_val"] = round((existing["count"] / total_errors * 100), 1)
            existing["pct"] = f"{existing['pct_val']}%"
        else:
            errors.append({
                "type": short_msg,
                "count": r.count,
                "pct_val": round((r.count / total_errors * 100), 1) if total_errors > 0 else 0,
                "pct": f"{round((r.count / total_errors * 100), 1) if total_errors > 0 else 0}%"
            })
            
    # 에러는 퍼센트 없이 단순 dict 리스트로 반환 후 포맷팅
    errors_formatted = [{"type": e["type"], "count": f"{e['count']:,}", "pct": e["pct"]} for e in errors]

    return {
        "metrics": metrics,
        "daily_jobs": daily_jobs,
        "providers": providers,
        "plans": plans,
        "errors": errors_formatted
    }
