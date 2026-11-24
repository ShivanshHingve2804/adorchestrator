from django.urls import path

from .views import AnalyzeCreativeView, CreativeFeatureListView, LatestWeeklySummaryView

urlpatterns = [
    path("creatives/<uuid:creative_id>/analyze/", AnalyzeCreativeView.as_view(), name="analyze-creative"),
    path("creatives/<uuid:creative_id>/features/", CreativeFeatureListView.as_view(), name="creative-features"),
    path("summaries/latest/", LatestWeeklySummaryView.as_view(), name="latest-weekly-summary"),
]
