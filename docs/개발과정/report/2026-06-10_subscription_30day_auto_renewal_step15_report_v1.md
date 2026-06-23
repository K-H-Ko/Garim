# 구독 30일 자동결제 Step 15 테스트 리포트

- 작성일: 2026-06-10
- 대상 범위: `subscription_30day_auto_renewal_final_v2_with_model_guide.md`의 STEP 15
- 최종 결과: 통과

## 검증 명령

```bash
C:\anaconda\envs\codex_test\python.exe -m pytest backend/tests/test_admin_subscription_check.py backend/tests/test_admin_payment_check.py backend/tests/test_payment.py backend/tests/test_subscription.py
cmd /c npm.cmd run build
```

## 요약

- 백엔드 테스트 결과: `61 passed`
- 프론트 빌드 결과: 성공
- 확인된 경고:
  - 기존 FastAPI `example` deprecation 경고
  - 기존 Starlette TestClient cookie deprecation 경고
  - Vite 프로덕션 빌드 chunk size 경고

## 필수 테스트 케이스 커버리지

| Step 15 케이스 | 대응 테스트 | 결과 |
|---|---|---|
| 15.1 Free -> Pro | `test_acceptance_free_to_pro_confirm_payment_creates_30day_subscription` | 통과 |
| 15.2 Free -> Studio | `test_acceptance_free_to_studio_confirm_payment_creates_30day_subscription` | 통과 |
| 15.3 Pro -> Studio 업그레이드 + Pro 잔여 기간 이월 | `test_service_confirm_payment_applies_upgrade_carryover`, `test_apply_upgrade_with_carryover_creates_upper_and_extends_lower` | 통과 |
| 15.4 업그레이드 후 하위 플랜 중복 자동결제 방지 | `test_apply_upgrade_with_carryover_creates_upper_and_extends_lower` | 통과 |
| 15.5 Studio -> Pro 다운그레이드 예약 | `test_schedule_downgrade_creates_scheduled_plan_change`, `test_change_plan_route_schedules_downgrade` | 통과 |
| 15.6 다운그레이드 예약 적용 | `test_run_scheduled_downgrades_success_creates_subscription_and_applies_change` | 통과 |
| 15.7 다운그레이드 예약 취소 | `test_cancel_scheduled_plan_change_marks_downgrade_cancelled`, `test_cancel_plan_change_route_cancels_scheduled_downgrade` | 통과 |
| 15.8 Studio -> Free 변경 | `test_schedule_cancel_to_free_updates_subscription_and_creates_plan_change`, `test_change_plan_route_schedules_cancel_to_free` | 통과 |
| 15.9 구독 취소 철회 | `test_resume_subscription_restores_auto_renew_and_cancels_cancel_to_free`, `test_resume_subscription_route_restores_cancellation` | 통과 |
| 15.10 자동결제 성공 | `test_run_subscription_renewals_success_creates_payment_and_extends_subscription` | 통과 |
| 15.11 자동결제 실패 | `test_run_subscription_renewals_records_missing_billing_key`, `test_run_subscription_renewals_charge_failure_records_failed_attempt` | 통과 |
| 15.12 모든 유료 플랜 만료 후 Free 적용 | `test_resolve_current_plan_falls_back_to_free_when_no_valid_subscription` | 통과 |

## 추가 확인 범위

- 현재 적용 플랜 우선순위 계산: `test_resolve_current_plan_uses_valid_active_subscription_rank_order`
- 관리자 구독 관리 화면 API 검증: `backend/tests/test_admin_subscription_check.py`
- 사용자 Billing 화면 API 검증: `test_service_get_my_payment_info_returns_current_plan_code`
- Billing Key 없음/결제 실패 시 예약 다운그레이드 실패 처리:
  - `test_run_scheduled_downgrades_missing_billing_key_marks_failed`
  - `test_run_scheduled_downgrades_charge_failure_marks_plan_change_failed`

## 비고

- STEP 15는 테스트 및 리포트 작성 범위로만 진행했습니다.
- 강제 취소, 강제 플랜 변경 같은 관리자 액션은 추가하지 않았습니다.
- STEP 14 후속으로 발견된 관리자 구독 화면 SQL 컬럼 오류는 수정 후 다시 검증했습니다.
- 관리자 구독 화면 반영 이후에도 프론트 빌드는 정상 통과했습니다.
