from fastapi import APIRouter

from controllers import uploads

router = APIRouter(tags=["uploads"])
router.add_api_route("/init", uploads.init_upload_handler, methods=["POST"])
router.add_api_route("/{upload_id}/chunks/{chunk_index}", uploads.upload_chunk_handler, methods=["POST"])
router.add_api_route("/{upload_id}/complete", uploads.complete_upload_handler, methods=["POST"])
router.add_api_route("/{upload_id}/status", uploads.get_upload_status_handler, methods=["GET"])
router.add_api_route("/{upload_id}/cancel", uploads.cancel_upload_handler, methods=["POST"])
router.add_api_route("", uploads.create_upload, methods=["POST"])
