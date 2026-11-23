from rest_framework.routers import SimpleRouter

from .views import CampaignViewSet, CreativeViewSet


router = SimpleRouter()
router.register("", CampaignViewSet, basename="campaign")
router.register(r"(?P<campaign_pk>[^/.]+)/creatives", CreativeViewSet, basename="campaign-creatives")

urlpatterns = router.urls
