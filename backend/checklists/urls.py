from django.urls import path

from . import views

urlpatterns = [
    path("today/", views.today, name="checklists-today"),
    path("runs/", views.Runs.as_view(), name="checklist-runs"),
    path("runs/<int:pk>/", views.run_detail, name="checklist-run"),
    path("runs/<int:pk>/answers/<int:answer_id>/", views.answer, name="checklist-answer"),
    path("runs/<int:pk>/submit/", views.submit, name="checklist-submit"),
    path("runs/<int:pk>/review/", views.review, name="checklist-review"),
    path("compliance/", views.compliance, name="checklist-compliance"),
    path("templates/", views.Templates.as_view(), name="checklist-templates"),
    path("templates/<int:pk>/", views.template_detail, name="checklist-template"),
    path("sops/", views.Sops.as_view(), name="sops"),
    path("sops/<int:pk>/", views.sop_detail, name="sop"),
]
