from django.urls import path

from .views import AdjustBudgetView, BudgetHistoryView

urlpatterns = [
    path("campaigns/<uuid:campaign_id>/adjust-budget/", AdjustBudgetView.as_view(), name="adjust-budget"),
    path("campaigns/<uuid:campaign_id>/budget-history/", BudgetHistoryView.as_view(), name="budget-history"),
]
