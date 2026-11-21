"""SMART_HIRE URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    [https://docs.djangoproject.com/en/3.0/topics/http/urls/](https://docs.djangoproject.com/en/3.0/topics/http/urls/)
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from myapp import views
from myapp.views import company_edit_schedule_post, company_delete_vacancy, company_delete_test

urlpatterns = [
    path('login_get/', views.login_get),
    path('login_post/',views.login_post),
    path('log_out/',views.log_out),
    path('ahome/',views.ahome),
    path('view_companies/',views.view_companies),
    path('view_approved_companies/',views.view_approved_companies),
    path('view_rejected_companies/',views.view_rejected_companies),
    path('view_complaints/',views.view_complaints),
    path('view_feedback/',views.view_feedback),
    path('view_users/',views.view_users),
    path('view_placed_users/',views.view_placed_users),
    path('view_vacancy/',views.view_vacancy),
    path('sent_reply_get/<id>',views.sent_reply_get),
    path('sent_reply__post/',views.sent_reply__post),
    path('change_password_get/',views.change_password_get),
    path('change_password_post/', views.change_password_post),
    path('admin_approve_company/<id>',views.admin_approve_company),
    path('admin_reject_company/<id>', views.admin_reject_company),

    #company
    path('company_signup_get/',views.company_signup_get),
    path('company_signup_post/',views.company_signup_post),
    path('company_view_profile/',views.company_view_profile),
    path('company_edit_profile_get/<id>',views.company_edit_profile_get),
    path('company_edit_profile_post/',views.company_edit_profile_post),
    path('company_add_questions_get/',views.company_add_questions_get),
    path('company_add_questions_post/',views.company_add_questions_post),
    path('company_edit_questions_get/<id>',views.company_edit_questions_get),
    path('company_edit_questions_post/', views.company_edit_questions_post),
    path('company_view_questions/',views.company_view_questions),
    path('company_add_questions2_get/<id>',views.company_add_questions2_get),
    path('company_add_questions2_post/',views.company_add_questions2_post),
    path('company_view_questions2/<id>',views.company_view_questions2),
    path('company_edit_questions2_get/<id>',views.company_edit_questions2_get),
    path('company_edit_questions2_post/',views.company_edit_questions2_post),
    path('company_delete_questions2/<id>',views.company_delete_questions2),

    path('company_add_schedule_get/<id>',views.company_add_schedule_get),
    path('company_add_schedule_post/',views.company_add_schedule_post),
    path('company_edit_schedule_get/<id>',views.company_edit_schedule_get),
    path('company_edit_schedule_post/',views.company_edit_schedule_post),
    path('company_view_schedule/<id>',views.company_view_schedule),
    path('company_delete_schedule/<id>',views.company_delete_schedule),
    path('company_add_test_get/<vid>',views.company_add_test_get),
    path('company_add_test_post/',views.company_add_test_post),
    path('company_edit_test_get/<id>',views.company_edit_test_get),
    path('company_edit_test_post/',views.company_edit_test_post),
    path('company_delete_test/<id>',company_delete_test),
    path('company_view_test/<vid>',views.company_view_test),
    path('company_add_vacancy_get/',views.company_add_vacancy_get),
    path('company_add_vacancy_post/',views.company_add_vacancy_post),
    path('company_edit_vacancy_get/<id>',views.company_edit_vacancy_get),
    path('company_edit_vacancy_post/',views.company_edit_vacancy_post),
    path('company_view_vacancy/',views.company_view_vacancy),
    path('company_delete_vacancy/<id>',company_delete_vacancy),
    path('company_change_password_get/',views.company_change_password_get),
    path('company_change_password_post/',views.company_change_password_post),
    path('company_view_shortlisted/<id>',views.company_view_shortlisted),
    path('company_view_feedback/',views.company_view_feedback),
    path('company_index_get/',views.company_index_get),
    path('company_view_activity/<vid>/<uid>',views.company_view_activity),
    path('company_delete_questions/<id>',views.company_delete_questions),
    path('view_vacancy_request/',views.view_vacancy_request),
    path('approve_vacancy_request/<id>',views.approve_vacancy_request),
    path('reject_vacancy_request/<id>',views.reject_vacancy_request),
    path('company_user_list/<vid>/<uid>',views.company_user_list),
    path('company_add_shortlist/<vid>/<uid>',views.company_add_shortlist),
    path('company_view_test_results/<tid>/', views.company_view_test_results, name='company_view_test_results'),
    path('company_view_activity/<vid>/<uid>/', views.company_view_activity, name='company_view_activity'),
    path('company_add_questions_csv_post/', views.company_add_questions_csv_post, name='company_add_questions_csv_post'),
    path('update_manual_mark/', views.update_manual_mark, name='update_manual_mark'),
    path('company_exam_list/', views.company_exam_list, name='company_exam_list'),
    path('company_ranked_candidates/<int:tid>/', views.company_ranked_candidates, name='company_ranked_candidates'),
    path('company_add_test_get/<int:id>/', views.company_add_test_get),
    path('company_place_students/<int:tid>/', views.company_place_students),
    path('check_user_notifications/', views.check_user_notifications),
path('user_recent_chats/', views.user_recent_chats, name='user_recent_chats'),
path('company_message_list/', views.company_message_list, name='company_message_list'),


    # This is the exact route you need for the download button to work!
    path('download_placed_candidates/<int:tid>/', views.download_placed_candidates, name='download_placed_candidates'),

    path('update_audio_mark/<int:result_id>/<str:new_mark>/', views.update_audio_mark),
    path('company_generate_ai_questions_get/<int:id>', views.company_generate_ai_questions_get),
    path('company_generate_ai_questions_post/', views.company_generate_ai_questions_post),
    path('generate_candidate_ai_report/<int:uid>/<int:tid>/', views.generate_candidate_ai_report),

    #User
    path('flutt_login/',views.flutt_login),
    path('user_signup_post/',views.user_signup_post),
    path('user_viewprofile/',views.user_viewprofile),
    path('user_editprofile/',views.user_editprofile),
    path('app_changepassword/',views.app_changepassword),
    path('sent_complaint/',views.sent_complaint),
    path('user_view_complaint/',views.user_view_complaint),
    path('user_viewquestions2_get/',views.user_viewquestions2_get),
    path('user_submit_answer/',views.user_submit_answer),
    path('user_view_company/',views.user_view_company),
    path('user_view_vacancy/',views.user_view_vacancy),
    path('user_vacancy_apply/', views.user_vacancy_apply),
    path('user_view_test/', views.user_view_test),
    path('user_view_schedule/', views.user_view_schedule),
    path('user_sent_feedback/', views.user_sent_feedback),
    path('user_view_result/', views.user_view_result),
    path('verify_face/', views.verify_face),
    path('user_view_approved_request/', views.user_view_approved_request),
    path('user_view_shortlist/', views.user_view_shortlist),
    path('User_sendchat/', views.User_sendchat),
    path('User_viewchat/', views.User_viewchat),
    path('chat1/<id>', views.chat1),
    path('chat_view/', views.chat_view),
    path('chat_send/<msg>', views.chat_send),
    path('appswitching/', views.appswitching),
    path('noice_Detection/', views.noice_Detection),
    path('back_action_required/', views.back_action_required),
    path('user_addmark/', views.user_addmark),
    path('view_activity/', views.view_activity),
    path('app_forgot_passweord/', views.app_forgot_passweord),
]