from fastapi import APIRouter

from controllers import analysis

router = APIRouter(tags=["analysis"])
router.add_api_route("/jobs", analysis.create_job_handler, methods=["POST"])
router.add_api_route("/jobs/{job_id}", analysis.get_job_handler, methods=["GET"])
router.add_api_route("/jobs/{job_id}", analysis.delete_job_handler, methods=["DELETE"])
router.add_api_route("/jobs/{job_id}/cancel", analysis.cancel_job_handler, methods=["POST"])

# 파이프라인 연동 신규 라우터
router.add_api_route("/jobs/{job_id}/detections", analysis.get_job_detections_handler, methods=["GET"])
router.add_api_route("/jobs/{job_id}/result", analysis.get_job_result_handler, methods=["GET"])
router.add_api_route("/jobs/{job_id}/selections", analysis.save_selections_handler, methods=["PUT"])
router.add_api_route("/jobs/{job_id}/selections", analysis.reset_selections_handler, methods=["DELETE"])
router.add_api_route("/jobs/{job_id}/mask-preview", analysis.create_mask_preview_handler, methods=["POST"])
router.add_api_route("/jobs/{job_id}/mask-preview", analysis.delete_mask_preview_handler, methods=["DELETE"])
router.add_api_route("/jobs/{job_id}/mask-final", analysis.create_mask_final_handler, methods=["POST"])
router.add_api_route("/jobs/{job_id}/result-file", analysis.get_result_file_handler, methods=["GET"])
# 상세보기 파일 서빙: GET /analysis/jobs/{id}/detail-file?file_type=image|video
router.add_api_route("/jobs/{job_id}/detail-file", analysis.get_detail_file_handler, methods=["GET"])
# 상세보기 크레딧 차감: POST /analysis/jobs/{id}/detail-access
router.add_api_route("/jobs/{job_id}/detail-access", analysis.detail_access_handler, methods=["POST"])
# 처리 완료 파일 다운로드: GET /analysis/jobs/{id}/download
router.add_api_route("/jobs/{job_id}/download", analysis.download_handler, methods=["GET"])
# 영상 구간 다운로드: GET /analysis/jobs/{id}/trim?start=0&end=30
router.add_api_route("/jobs/{job_id}/trim", analysis.trim_download_handler, methods=["GET"])

# 대시보드 및 히스토리
router.add_api_route("/dashboard", analysis.get_dashboard_handler, methods=["GET"])
router.add_api_route("/history", analysis.get_history_handler, methods=["GET"])
router.add_api_route("/uploads/{upload_id}", analysis.delete_upload_handler, methods=["DELETE"])
router.add_api_route("/uploads/{upload_id}/thumbnail", analysis.get_thumbnail_handler, methods=["GET"])
