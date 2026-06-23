from fastapi import APIRouter

from controllers import post

router = APIRouter(tags=["posts"])
router.add_api_route("",post.create_post, methods=["POST"])
router.add_api_route("",post.get_posts, methods=["GET"])
router.add_api_route("/{post_id}",post.get_post, methods=["GET"])
router.add_api_route("/{post_id}",post.update_post, methods=["PUT"])
router.add_api_route("/{post_id}",post.delete_post, methods=["DELETE"])
