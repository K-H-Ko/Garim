from fastapi import APIRouter

from controllers import oauth


router = APIRouter(tags=["auth"])
router.add_api_route("/oauth/{provider}", oauth.start_oauth, methods=["GET"])
router.add_api_route("/oauth/{provider}/callback", oauth.oauth_callback, methods=["GET"])
router.add_api_route("/refresh", oauth.refresh, methods=["POST"])
router.add_api_route("/status", oauth.get_status, methods=["GET"])
router.add_api_route("/me", oauth.get_me, methods=["GET"])
router.add_api_route("/me", oauth.delete_me, methods=["DELETE"])
router.add_api_route("/logout", oauth.logout, methods=["POST"])
router.add_api_route("/consents", oauth.get_consents, methods=["GET"])
router.add_api_route("/consents", oauth.save_consents, methods=["POST"])
router.add_api_route("/sessions/{session_id}", oauth.delete_session, methods=["DELETE"])
router.add_api_route("/sessions", oauth.delete_sessions, methods=["DELETE"])
router.add_api_route("/admin/users/{user_id}/status", oauth.update_user_status, methods=["PATCH"])
router.add_api_route("/{provider}/start", oauth.start_oauth, methods=["GET"])
router.add_api_route("/{provider}/callback", oauth.oauth_callback, methods=["GET"])
