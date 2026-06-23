from fastapi import APIRouter

from controllers import admin

router = APIRouter(tags=["admin"])

router.add_api_route("/users", admin.list_users, methods=["GET"])
router.add_api_route("/policy", admin.get_policy_settings, methods=["GET"])
router.add_api_route("/policy", admin.update_policy_settings, methods=["PUT"])
router.add_api_route("/plans", admin.list_subscription_plans, methods=["GET"])
router.add_api_route("/plans", admin.create_subscription_plan, methods=["POST"])
router.add_api_route("/plans/{plan_id}", admin.update_subscription_plan, methods=["PUT"])
router.add_api_route("/plans/{plan_id}", admin.delete_subscription_plan, methods=["DELETE"])
router.add_api_route("/credit-plans", admin.list_credit_plans, methods=["GET"])
router.add_api_route("/credit-plans", admin.create_credit_plan, methods=["POST"])
router.add_api_route("/credit-plans/{credit_plan_id}", admin.update_credit_plan, methods=["PUT"])
router.add_api_route("/credit-plans/{credit_plan_id}", admin.delete_credit_plan, methods=["DELETE"])
router.add_api_route("/subscriptions", admin.list_admin_subscriptions, methods=["GET"])
router.add_api_route("/subscriptions/{user_id}", admin.get_admin_subscription_detail, methods=["GET"])
router.add_api_route("/subscriptions/{user_id}/{subscription_id}", admin.cancel_admin_subscription, methods=["DELETE"])
router.add_api_route("/payments", admin.list_payments, methods=["GET"])
router.add_api_route("/payments/{payment_id}", admin.get_payment_detail, methods=["GET"])
router.add_api_route("/payments/{payment_id}/refund", admin.refund_payment, methods=["POST"])

# 회원 관리
router.add_api_route("/monitoring/overview", admin.get_monitoring_overview, methods=["GET"])
router.add_api_route("/monitoring/activities", admin.get_monitoring_activities, methods=["GET"])
router.add_api_route("/monitoring/jobs/{job_id}/cancel", admin.cancel_monitoring_job, methods=["POST"])

# 대기열 현황
router.add_api_route("/queue/overview", admin.get_queue_overview, methods=["GET"])

# 파일 관리
router.add_api_route("/compliance/overview", admin.get_compliance_overview, methods=["GET"])
router.add_api_route("/compliance/search",   admin.search_compliance,       methods=["GET"])
router.add_api_route("/compliance/consent",  admin.get_compliance_consent,  methods=["GET"])
router.add_api_route("/compliance/reports",  admin.get_compliance_reports,  methods=["GET"])

# 분석
router.add_api_route("/analytics", admin.get_analytics, methods=["GET"])
