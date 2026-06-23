from fastapi import APIRouter

from controllers import worker

router = APIRouter(tags=["worker"])
router.add_api_route("/jobs/next", worker.get_next_job_handler, methods=["GET"])
router.add_api_route("/jobs/{job_id}/status", worker.get_job_status_handler, methods=["GET"])
router.add_api_route("/jobs/{job_id}/accept", worker.accept_job_handler, methods=["POST"])
router.add_api_route("/jobs/{job_id}/progress", worker.update_progress_handler, methods=["PUT"])
router.add_api_route("/jobs/{job_id}/complete", worker.complete_job_handler, methods=["POST"])
router.add_api_route("/jobs/{job_id}/cancelled", worker.cancelled_job_handler, methods=["POST"])
router.add_api_route("/jobs/{job_id}/fail", worker.fail_job_handler, methods=["POST"])
router.add_api_route("/files/{upload_id}/download", worker.download_file_handler, methods=["GET"])
router.add_api_route("/files/{upload_id}", worker.get_file_handler, methods=["GET"])
router.add_api_route("/heartbeat", worker.heartbeat_handler, methods=["POST"])
router.add_api_route("/jobs/{job_id}/results/stt", worker.save_stt_result_handler, methods=["POST"])
router.add_api_route("/jobs/{job_id}/results/pii", worker.save_pii_result_handler, methods=["POST"])
router.add_api_route("/jobs/{job_id}/results/artifact", worker.save_artifact_handler, methods=["POST"])
router.add_api_route("/jobs/{job_id}/results/processed-file", worker.save_processed_file_handler, methods=["POST"])
# 로컬 워커가 코랩 STT 결과를 merger 전에 조회하는 엔드포인트
router.add_api_route("/jobs/{job_id}/results/audio-pii", worker.get_audio_pii_handler, methods=["GET"])
router.add_api_route("/uploads/{upload_id}/stt-job", worker.get_stt_job_id_handler, methods=["GET"])
# 로컬 워커가 mask job 처리 시 사용자가 선택한 bbox 목록 조회
router.add_api_route("/jobs/{job_id}/selected-detections", worker.get_selected_detections_handler, methods=["GET"])
# Colab mask 워커 전용: result_json + selected_pii_ids 조회
router.add_api_route("/jobs/{job_id}/mask-context", worker.get_mask_context_handler, methods=["GET"])
# Colab mask 워커 전용: 처리 완료 파일 multipart 업로드 수신
router.add_api_route("/jobs/{job_id}/results/upload-file", worker.upload_processed_file_handler, methods=["POST"])
