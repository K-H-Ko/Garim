from fastapi import Body, Query, status, Cookie
from fastapi.responses import JSONResponse

from services import admin as admin_service
from services import auth as auth_service
from services import admin_analytics as admin_analytics_service
from utils.database import get_db
from fastapi import Depends
from sqlalchemy.orm import Session


def _json_error(error: Exception):
    status_code = 400 if isinstance(error, ValueError) else 500
    return JSONResponse({"message": str(error)}, status_code=status_code)


def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    role: str = Query(None),
    status: str = Query(None),
):
    try:
        data = admin_service.get_users_list(page, limit, role, status)
        return JSONResponse(
            {"data": data, "message": "사용자 목록 조회"},
            status_code=200,
        )
    except Exception as e:
        return JSONResponse(
            {"message": str(e)},
            status_code=500,
        )


def get_policy_settings():
    try:
        data = admin_service.get_admin_policies()
        return JSONResponse(
            {"data": data, "message": "Admin policy settings loaded."},
            status_code=200,
        )
    except Exception as e:
        return JSONResponse(
            {"message": str(e)},
            status_code=500,
        )


def update_policy_settings(payload: dict = Body(...), access_token: str | None = Cookie(default=None)):
    try:
        user_id = None
        if access_token:
            try:
                current_user = auth_service.authenticate_access_token(access_token)
                user_id = current_user.get("id")
            except Exception:
                pass

        policies = payload.get("policies", payload)
        data = admin_service.update_admin_policies(policies, updated_by=user_id)
        return JSONResponse(
            {"data": data, "message": "Admin policy settings saved."},
            status_code=200,
        )
    except Exception as e:
        return JSONResponse(
            {"message": str(e)},
            status_code=500,
        )


def list_subscription_plans(
    q: str = Query(None),
    include_deleted: bool = Query(False),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    try:
        result = admin_service.list_subscription_plans(q, include_deleted, status, page, limit)
        return JSONResponse(
            {
                "data": result["data"],
                "total": result["total"],
                "page": result["page"],
                "limit": result["limit"],
                "message": "Subscription plans loaded.",
            },
            status_code=200,
        )
    except Exception as e:
        return _json_error(e)


def create_subscription_plan(payload: dict = Body(...)):
    try:
        data = admin_service.create_subscription_plan(payload)
        return JSONResponse(
            {"data": data, "message": "Subscription plan created."},
            status_code=status.HTTP_201_CREATED,
        )
    except Exception as e:
        return _json_error(e)


def update_subscription_plan(plan_id: str, payload: dict = Body(...)):
    try:
        data = admin_service.update_subscription_plan(plan_id, payload)
        return JSONResponse(
            {"data": data, "message": "Subscription plan updated."},
            status_code=200,
        )
    except Exception as e:
        return _json_error(e)


def delete_subscription_plan(plan_id: str):
    try:
        data = admin_service.delete_subscription_plan(plan_id)
        return JSONResponse(
            {"data": data, "message": "Subscription plan deleted."},
            status_code=200,
        )
    except Exception as e:
        return _json_error(e)


def list_credit_plans(
    q: str = Query(None),
    include_deleted: bool = Query(False),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    try:
        result = admin_service.list_credit_plans(q, include_deleted, status, page, limit)
        return JSONResponse(
            {
                "data": result["data"],
                "total": result["total"],
                "page": result["page"],
                "limit": result["limit"],
                "message": "Credit plans loaded.",
            },
            status_code=200,
        )
    except Exception as e:
        return _json_error(e)


def create_credit_plan(payload: dict = Body(...)):
    try:
        data = admin_service.create_credit_plan(payload)
        return JSONResponse(
            {"data": data, "message": "Credit plan created."},
            status_code=status.HTTP_201_CREATED,
        )
    except Exception as e:
        return _json_error(e)


def update_credit_plan(credit_plan_id: str, payload: dict = Body(...)):
    try:
        data = admin_service.update_credit_plan(credit_plan_id, payload)
        return JSONResponse(
            {"data": data, "message": "Credit plan updated."},
            status_code=200,
        )
    except Exception as e:
        return _json_error(e)


def delete_credit_plan(credit_plan_id: str):
    try:
        data = admin_service.delete_credit_plan(credit_plan_id)
        return JSONResponse(
            {"data": data, "message": "Credit plan deleted."},
            status_code=200,
        )
    except Exception as e:
        return _json_error(e)


def list_admin_subscriptions(
    q: str = Query(None),
    search_key: str = Query("email"),
    plan_code: str = Query(None),
    subscription_status: str = Query(None),
    auto_renew: str = Query(None),
    cancel_scheduled: str = Query(None),
    billing_failed: str = Query(None),
    scheduled_change: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
):
    try:
        result = admin_service.get_admin_subscriptions_list(
            q=q,
            search_key=search_key,
            plan_code=plan_code,
            subscription_status=subscription_status,
            auto_renew=auto_renew,
            cancel_scheduled=cancel_scheduled,
            billing_failed=billing_failed,
            scheduled_change=scheduled_change,
            page=page,
            limit=limit,
        )
        return JSONResponse(
            {
                "data": result["data"],
                "summary": result["summary"],
                "total": result["total"],
                "page": result["page"],
                "limit": result["limit"],
                "message": "Admin subscriptions loaded successfully.",
            },
            status_code=200,
        )
    except Exception as e:
        return _json_error(e)


def get_admin_subscription_detail(user_id: str):
    try:
        data = admin_service.get_admin_subscription_detail(user_id)
        return JSONResponse(
            {"data": data, "message": "Admin subscription detail loaded successfully."},
            status_code=200,
        )
    except ValueError as ve:
        return JSONResponse({"message": str(ve)}, status_code=404)
    except Exception as e:
        return _json_error(e)


def list_payments(
    product_type: str = Query(None),
    status: str = Query(None),
    q: str = Query(None),
    search_key: str = Query("email"),
    date_from: str = Query(None),
    date_to: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
):
    try:
        result = admin_service.get_payments_list(
            product_type=product_type,
            status=status,
            q=q,
            search_key=search_key,
            date_from=date_from,
            date_to=date_to,
            page=page,
            limit=limit,
        )
        return JSONResponse(
            {
                "data": result["data"],
                "summary": result["summary"],
                "total": result["total"],
                "page": result["page"],
                "limit": result["limit"],
                "message": "Payments list loaded successfully.",
            },
            status_code=200,
        )
    except Exception as e:
        return _json_error(e)


def get_payment_detail(payment_id: str):
    try:
        data = admin_service.get_payment_detail(payment_id)
        return JSONResponse(
            {"data": data, "message": "Payment detail loaded successfully."},
            status_code=200,
        )
    except ValueError as ve:
        return JSONResponse({"message": str(ve)}, status_code=404)
    except Exception as e:
        return _json_error(e)


def refund_payment(payment_id: str, payload: dict = Body(default={}), access_token: str | None = Cookie(default=None)):
    """관리자용 결제 환불 처리 — 환불 사유(refund_reason) + 크레딧 차감 포함."""
    try:
        user_id = None
        if access_token:
            try:
                current_user = auth_service.authenticate_access_token(access_token)
                user_id = current_user.get("id")
            except Exception:
                pass

        refund_reason = (payload.get("refund_reason") or "").strip() or None
        data = admin_service.refund_payment(payment_id, user_id, refund_reason)
        return JSONResponse(
            {"data": data, "message": "환불 처리가 완료되었습니다."},
            status_code=200,
        )
    except ValueError as ve:
        return JSONResponse({"message": str(ve)}, status_code=400)
    except Exception as e:
        return _json_error(e)


def cancel_admin_subscription(user_id: str, subscription_id: str, payload: dict = Body(default={})):
    """관리자용 구독 강제 취소 — 취소 사유(cancel_reason) + 이전 구독 복원 로직 포함."""
    try:
        cancel_reason = (payload.get("cancel_reason") or "").strip() or None
        data = admin_service.cancel_subscription_for_user(user_id, subscription_id, cancel_reason)
        return JSONResponse(
            {"data": data, "message": data.get("message", "구독이 취소되었습니다.")},
            status_code=200,
        )
    except ValueError as ve:
        return JSONResponse({"message": str(ve)}, status_code=400)
    except Exception as e:
        return _json_error(e)


# =========================================================================
# 관리자 - 사용자 모니터링 핸들러
# =========================================================================

def get_monitoring_overview():
    """사용자 모니터링 상단 메트릭 조회."""
    try:
        data = admin_service.get_monitoring_overview()
        return JSONResponse(
            {"data": data, "message": "Monitoring overview loaded."},
            status_code=200,
        )
    except Exception as e:
        return _json_error(e)


def get_monitoring_activities(
    limit: int = Query(50, ge=1, le=200),
    status: str = Query(None),
):
    """실시간 활동 중인 사용자 목록 조회."""
    try:
        data = admin_service.get_monitoring_activities(limit=limit, status_filter=status)
        return JSONResponse(
            {"data": data, "message": "Monitoring activities loaded."},
            status_code=200,
        )
    except Exception as e:
        return _json_error(e)


# =========================================================================
# 관리자 - 컴플라이언스 핸들러
# =========================================================================

def get_compliance_overview():
    """컴플라이언스 자동삭제 탭 데이터 조회."""
    try:
        data = admin_service.get_compliance_overview()
        return JSONResponse({"data": data, "message": "Compliance overview loaded."}, status_code=200)
    except Exception as e:
        return _json_error(e)


def search_compliance(
    q: str = Query(None),
    type: str = Query("job_id"),
):
    """처리 이력 검색 (job_id / user_id / watermark)."""
    try:
        data = admin_service.search_compliance(q or "", search_type=type)
        return JSONResponse({"data": data, "message": "Search completed."}, status_code=200)
    except Exception as e:
        return _json_error(e)


def get_compliance_consent(q: str = Query(None)):
    """약관 동의 이력 조회 (email 또는 user_id)."""
    try:
        data = admin_service.get_consent_history(q or "")
        return JSONResponse({"data": data, "message": "Consent history loaded."}, status_code=200)
    except Exception as e:
        return _json_error(e)


def get_compliance_reports(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """신고·수사 응답 이력 조회."""
    try:
        data = admin_service.get_compliance_reports(page=page, limit=limit)
        return JSONResponse({"data": data, "message": "Reports loaded."}, status_code=200)
    except Exception as e:
        return _json_error(e)


# =========================================================================
# 관리자 - 처리 큐 핸들러
# =========================================================================

def get_queue_overview():
    """처리 큐 현황 조회 (메트릭 + 작업목록 + 워커 + 차트 데이터)."""
    try:
        data = admin_service.get_queue_overview()
        return JSONResponse(
            {"data": data, "message": "Queue overview loaded."},
            status_code=200,
        )
    except Exception as e:
        return _json_error(e)


def cancel_monitoring_job(job_id: str, access_token: str | None = Cookie(default=None)):
    """진행 중 작업 강제 취소 (관리자)."""
    try:
        user_id = None
        if access_token:
            try:
                current_user = auth_service.authenticate_access_token(access_token)
                user_id = current_user.get("id")
            except Exception:
                pass

        data = admin_service.cancel_monitoring_job(job_id, admin_user_id=user_id)
        return JSONResponse(
            {"data": data, "message": "작업 취소가 요청되었습니다."},
            status_code=200,
        )
    except ValueError as ve:
        return JSONResponse({"message": str(ve)}, status_code=404)
    except Exception as e:
        return _json_error(e)


# =========================================================================
# 관리자 - 분석 핸들러
# =========================================================================

def get_analytics(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    """관리자 분석 데이터 조회 (지표, 차트, 요금제, 실패유형)."""
    try:
        data = admin_analytics_service.get_analytics_data(db, days=days)
        return JSONResponse({"data": data, "message": "Analytics data loaded."}, status_code=200)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _json_error(e)
