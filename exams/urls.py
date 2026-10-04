from django.urls import path

from exams import panel_views, views

urlpatterns = [
    path("accounts/register/", views.register, name="register"),
    path("accounts/profile/", views.complete_profile, name="complete_profile"),
    path("", views.exam_list, name="exam_list"),
    path("go/", views.post_login, name="post_login"),
    path("exams/<int:pk>/", views.take_exam, name="take_exam"),
    path("results/<int:pk>/", views.exam_result, name="exam_result"),
    path("certificates/<int:pk>/pdf/", views.certificate_pdf, name="certificate_pdf"),
    path("panel/", panel_views.dashboard, name="panel_dashboard"),
    path("panel/exams/", panel_views.exam_list, name="panel_exams"),
    path("panel/exams/new/", panel_views.exam_create, name="panel_exam_create"),
    path("panel/exams/<int:pk>/", panel_views.exam_detail, name="panel_exam_detail"),
    path("panel/exams/<int:pk>/settings/", panel_views.exam_settings, name="panel_exam_settings"),
    path("panel/exams/<int:pk>/marking/", panel_views.exam_marking, name="panel_exam_marking"),
    path("panel/exams/<int:pk>/participants/", panel_views.exam_participants, name="panel_exam_participants"),
    path(
        "panel/exams/<int:exam_pk>/submissions/<int:pk>/",
        panel_views.exam_submission_sheet,
        name="panel_exam_submission",
    ),
    path("panel/exams/<int:pk>/delete/", panel_views.exam_delete, name="panel_exam_delete"),
    path("panel/exams/<int:exam_pk>/questions/new/", panel_views.question_create, name="panel_question_create"),
    path(
        "panel/exams/<int:exam_pk>/questions/screenshot/",
        panel_views.question_screenshot,
        name="panel_question_screenshot",
    ),
    path(
        "panel/exams/<int:exam_pk>/questions/<int:pk>/",
        panel_views.question_edit,
        name="panel_question_edit",
    ),
    path(
        "panel/exams/<int:exam_pk>/questions/<int:pk>/delete/",
        panel_views.question_delete,
        name="panel_question_delete",
    ),
    path("panel/results/", panel_views.result_list, name="panel_results"),
    path("panel/certificates/", panel_views.certificate_list, name="panel_certificates"),
    path("panel/certificates/<int:pk>/", panel_views.certificate_view, name="panel_certificate_view"),
    path("panel/certificates/<int:pk>/pdf/", panel_views.certificate_pdf, name="panel_certificate_pdf"),
    path("panel/results/<int:pk>/certificate/", panel_views.certificate_issue, name="panel_certificate_issue"),
    path("panel/users/", panel_views.user_list, name="panel_users"),
    path("panel/settings/", panel_views.site_settings, name="panel_site_settings"),
    path("panel/password/", panel_views.password_change, name="panel_password"),
]
