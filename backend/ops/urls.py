from django.urls import path

from . import views

urlpatterns = [
    path("staffing/", views.staffing, name="staffing"),
    path("staffing/plan/", views.staffing_plan, name="staffing-plan"),
    path("employees/", views.Employees.as_view(), name="employees"),
    path("employees/<int:pk>/", views.employee_detail, name="employee"),
    path("complaints/", views.Complaints.as_view(), name="complaints"),
    path("equipment/", views.EquipmentView.as_view(), name="equipment"),
    path("issues/", views.Issues.as_view(), name="issues"),
    path("issues/<int:pk>/", views.issue_detail, name="issue"),
    path("handover/", views.Handover.as_view(), name="handover"),
    path("handover/<int:pk>/read/", views.handover_read, name="handover-read"),
    path("delivery-scores/", views.DeliveryScores.as_view(), name="delivery-scores"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/read/", views.notifications_read, name="notifications-read"),
]
