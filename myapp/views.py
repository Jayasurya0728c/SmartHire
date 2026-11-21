from datetime import datetime
import face_recognition
import smtplib
from email.mime.text import MIMEText
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import User, Group
from django.core.files.storage import FileSystemStorage
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt

import threading
import ssl
import os
import json
import librosa
import numpy as np
from google import genai
import csv
import time  # <-- NEW: Added for our retry delay

# Create a global lock for our heavy AI models
ai_lock = threading.Lock()

# Disable SSL verification for Gemini/API calls
ssl._create_default_https_context = ssl._create_unverified_context

from SMART_HIRE import settings
from myapp.models import *
from .photo_processing import process_exam_photo


# ==========================================
# SAFE AI HELPER (Handles 503 Busy Errors!)
# ==========================================
def safe_gemini_request(client, model, contents, retries=3):
    """Safely calls Gemini and automatically retries if the server is busy."""
    for attempt in range(retries):
        try:
            return client.models.generate_content(model=model, contents=contents)
        except Exception as e:
            error_msg = str(e)
            # Check if it's a server busy/unavailable error
            if '503' in error_msg or '429' in error_msg or 'UNAVAILABLE' in error_msg:
                if attempt < retries - 1:
                    sleep_time = 2 ** attempt  # Waits 1s, then 2s, then 4s...
                    print(f"⚠️ Gemini API Busy! Retrying in {sleep_time} seconds... (Attempt {attempt+1}/{retries})")
                    time.sleep(sleep_time)
                    continue
            # If it's a different error or we are out of retries, raise it
            raise e


# ==========================================
# ADMIN & COMPANY VIEWS (Standard Logic)
# ==========================================

def login_get(request):
    return render(request, 'login_index.html')


def login_post(request):
    username = request.POST['email']
    password = request.POST['pass']
    user = authenticate(username=username, password=password)
    if user is not None:
        login(request, user)
        if user.groups.filter(name="Admin").exists():
            messages.success(request, 'login successfully')
            return redirect('/myapp/ahome/')
        elif user.groups.filter(name="Company").exists():
            data = Company.objects.get(AUTHUSER_id=user.id)
            if data.Status == 'Approved':
                messages.success(request, 'login successfully')
                return redirect('/myapp/company_index_get/')
            else:
                return redirect('/myapp/login_get/')
        else:
            return redirect('/myapp/login_get/')
    else:
        return redirect('/myapp/login_get/')


def log_out(request):
    logout(request)
    return redirect('/myapp/login_get/')


def ahome(request):
    # Calculate live metrics for the Admin Dashboard
    total_candidates = Users.objects.count()
    approved_companies = Company.objects.filter(Status='Approved').count()
    active_exams = Test.objects.count()
    placements = Vacancy_request.objects.filter(Status='Placed').count()

    context = {
        'total_candidates': total_candidates,
        'approved_companies': approved_companies,
        'active_exams': active_exams,
        'placements': placements,
    }
    return render(request, 'Admin/ahome.html', context)


def view_companies(request):
    data = Company.objects.filter(Status='pending')
    return render(request, 'admin/view_company.html', {'data': data})


def admin_approve_company(request, id):
    Company.objects.filter(id=id).update(Status='Approved')
    return redirect('/myapp/view_approved_companies/')


def admin_reject_company(request, id):
    Company.objects.filter(id=id).update(Status='Rejected')
    return redirect('/myapp/view_rejected_companies/')


def view_approved_companies(request):
    data = Company.objects.filter(Status='Approved')
    return render(request, 'admin/viewapprovedcompanies.html', {'data': data})


def view_rejected_companies(request):
    data = Company.objects.filter(Status='Rejected')
    return render(request, 'admin/viewrejectedcompanies.html', {'data': data})


def view_complaints(request):
    data = Complaint.objects.all()
    return render(request, 'admin/viewcomplaints.html', {'data': data})


def view_feedback(request):
    data = Feedback.objects.all()
    return render(request, 'admin/viewfeedback.html', {'data': data})


def view_users(request):
    data = Users.objects.all()
    return render(request, 'admin/viewusers.html', {'data': data})


def view_placed_users(request):
    data = Vacancy_request.objects.filter(Status='Placed')
    return render(request, 'admin/viewplacedusers.html', {'data': data})


def view_vacancy(request):
    data = Vacancy.objects.all()
    return render(request, 'admin/viewvacancy.html', {'data': data})


def sent_reply_get(request, id):
    data = Complaint.objects.get(id=id)
    return render(request, 'admin/sentreply.html', {'data': data})


def sent_reply__post(request):
    reply = request.POST['reply']
    id = request.POST['id']
    data = Complaint.objects.get(id=id)
    data.Reply = reply
    data.Status = 'replied'
    data.save()
    return redirect('/myapp/view_complaints/')


def change_password_get(request):
    return render(request, 'admin/changepassword.html')


def change_password_post(request):
    currentpassword = request.POST['currentpassword']
    newpassword = request.POST['newpassword']
    confirmpassword = request.POST['confirmpassword']
    user = request.user
    if check_password(currentpassword, request.user.password):
        if newpassword == confirmpassword:
            user.set_password(newpassword)
            user.save()
            return redirect('/myapp/login_get/')
        else:
            return redirect('/myapp/change_password_get/')
    else:
        return redirect('/myapp/change_password_get/')


def company_signup_get(request):
    return render(request, 'company/signup.html')


def company_signup_post(request):
    Company_name = request.POST['Company_name']
    Company_id = request.POST['Company_id']
    Email = request.POST['Email']
    phone = request.POST['phone']
    License = request.POST['License']
    Post = request.POST['Post']
    City = request.POST['City']
    State = request.POST['State']
    Pincode = request.POST['Pincode']
    Photo = request.FILES['Photo']
    About = request.POST['About']
    password = request.POST['password']
    cpassword = request.POST['password2']

    if password == cpassword:
        user = User.objects.create_user(username=Email, password=password)
        user.groups.add(Group.objects.get(name='Company'))
        user.save()
        fs = FileSystemStorage()
        date = datetime.now().strftime('%Y%m%d%H%M%S') + '.jpg'
        fs.save(date, Photo)
        path = fs.url(date)
        a = Company()
        a.Company_name = Company_name
        a.Company_id = Company_id
        a.Email = Email
        a.phone = phone
        a.License = License
        a.Post = Post
        a.City = City
        a.State = State
        a.Pincode = Pincode
        a.Photo = path
        a.About = About
        a.AUTHUSER = user
        a.Status = 'pending'
        a.save()
        return redirect('/myapp/login_get/')
    else:
        return redirect('/myapp/company_signup_get/')


def company_index_get(request):
    # Get the logged-in company
    company_obj = Company.objects.get(AUTHUSER_id=request.user.id)

    # 1. Total Applications (Count of all vacancy requests for this company)
    applications = Vacancy_request.objects.filter(VACANCY__COMPANY=company_obj)
    total_applications = applications.count()

    # 2. Placements (Count of requests marked as 'Placed')
    placements = applications.filter(Status='Placed').count()

    # 3. Pending Reviews (Count of requests marked as 'pending')
    pending_reviews = applications.filter(Status='pending').count()

    # 4. AI Screened Percentage (Calculates how many have been auto-processed)
    if total_applications > 0:
        screened_count = total_applications - pending_reviews
        ai_screened_pct = int((screened_count / total_applications) * 100)
    else:
        ai_screened_pct = 0

    # Package all real data to send to the HTML
    context = {
        'email': company_obj.Email,
        'phone': company_obj.phone,
        'City': company_obj.City,
        'total_applications': total_applications,
        'ai_screened_pct': ai_screened_pct,
        'pending_reviews': pending_reviews,
        'placements': placements,
    }

    return render(request, 'company/company_index.html', context)


def company_view_profile(request):
    data = Company.objects.get(AUTHUSER_id=request.user.id)
    return render(request, 'company/view_profile.html', {'data': data})


def company_edit_profile_get(request, id):
    data = Company.objects.get(id=id)
    return render(request, 'company/edit_profile.html', {'data': data})


def company_edit_profile_post(request):
    Company_name = request.POST['Company_name']
    Company_id = request.POST['Company_id']
    Email = request.POST['Email']
    phone = request.POST['phone']
    License = request.POST['License']
    Post = request.POST['Post']
    City = request.POST['City']
    State = request.POST['State']
    Pincode = request.POST['Pincode']
    About = request.POST['About']
    id = request.POST['id']
    a = Company.objects.get(id=id)
    if 'Photo' in request.FILES:
        Photo = request.FILES['Photo']
        fs = FileSystemStorage()
        date = datetime.now().strftime('%Y%m%d%H%M%S') + '.jpg'
        fs.save(date, Photo)
        path = fs.url(date)
        a.Photo = path
        a.save()
    a.Company_name = Company_name
    a.Company_id = Company_id
    a.Email = Email
    a.phone = phone
    a.License = License
    a.Post = Post
    a.City = City
    a.State = State
    a.Pincode = Pincode
    a.About = About
    a.save()
    return HttpResponse(
        "<script>alert('Profile updated successfully!');window.location.href = '/myapp/company_view_profile/#a';</script>")


def company_add_questions_get(request):
    return render(request, 'company/add_questions.html')


def company_add_questions_post(request):
    questions = request.POST['questions']
    option1 = request.POST['option1']
    option2 = request.POST['option2']
    option3 = request.POST['option3']
    option4 = request.POST['option4']
    Answer = request.POST['Answer']
    a = Questions()
    a.questions = questions
    a.option1 = option1
    a.option2 = option2
    a.option3 = option3
    a.option4 = option4
    a.Answer = Answer
    a.save()
    return redirect('/myapp/company_add_questions_get/#a')


def company_edit_questions_get(request, id):
    data = Questions.objects.get(id=id)
    return render(request, 'company/edit_questions.html', {'data': data})


def company_edit_questions_post(request):
    questions = request.POST['questions']
    option1 = request.POST['option1']
    option2 = request.POST['option2']
    option3 = request.POST['option3']
    option4 = request.POST['option4']
    Answer = request.POST['Answer']
    id = request.POST['id']
    a = Questions.objects.get(id=id)
    a.questions = questions
    a.option1 = option1
    a.option2 = option2
    a.option3 = option3
    a.option4 = option4
    a.Answer = Answer
    a.save()
    return redirect('/myapp/company_view_questions/#a')


def company_view_questions(request):
    data = Questions.objects.all()
    return render(request, 'company/view_questions.html', {'data': data})


def company_delete_questions(request, id):
    Questions.objects.get(id=id).delete()
    return redirect('/myapp/company_view_questions/#a')


def company_view_questions2(request, id):
    request.session['tid'] = id
    data = Questions2.objects.filter(TEST_id=id)
    return render(request, 'company/view_questions2.html', {'data': data})


def company_add_questions2_get(request, id):
    return render(request, 'company/add_questions2.html', {'id': id})


def company_add_questions2_post(request):
    questions = request.POST['questions']
    option1 = request.POST['option1']
    option2 = request.POST['option2']
    option3 = request.POST['option3']
    option4 = request.POST['option4']
    Answer = request.POST['Answer']
    type = request.POST['type']
    id = request.POST['id']
    if type == "Normal":
        a = Questions2()
        a.type = type
        a.questions = questions
        a.option1 = option1
        a.option2 = option2
        a.option3 = option3
        a.option4 = option4
        a.Answer = Answer
        a.TEST_id = id
        a.save()
    else:
        a = Questions2()
        a.type = type
        a.questions = questions
        a.option1 = ""
        a.option2 = ""
        a.option3 = ""
        a.option4 = ""
        a.Answer = Answer
        a.TEST_id = id
        a.save()
    return redirect(f'/myapp/company_view_questions2/{id}#a')


def company_edit_questions2_get(request, id):
    data = Questions2.objects.get(id=id)
    return render(request, 'company/edit_questions2.html', {'data': data})


def company_edit_questions2_post(request):
    questions = request.POST['questions']
    option1 = request.POST['option1']
    option2 = request.POST['option2']
    option3 = request.POST['option3']
    option4 = request.POST['option4']
    Answer = request.POST['Answer']
    id = request.POST['id']
    a = Questions2.objects.get(id=id)
    a.questions = questions
    a.option1 = option1
    a.option2 = option2
    a.option3 = option3
    a.option4 = option4
    a.Answer = Answer
    a.save()
    return redirect(f'/myapp/company_view_questions2/{request.session["tid"]}#a')


def company_delete_questions2(request, id):
    Questions2.objects.get(id=id).delete()
    return redirect(f'/myapp/company_view_questions2/{request.session["tid"]}#a')


def company_add_schedule_get(request, id):
    data = Test.objects.get(id=id)
    return render(request, 'company/add_schedule.html', {'data': data})


def company_add_schedule_post(request):
    date = request.POST['Date']
    Starttime = request.POST['Starttime']
    Endtime = request.POST['Endtime']
    id = request.POST['id']  # This is the Test ID

    a = Schedule()
    a.Date = date
    a.Starttime = Starttime
    a.Endtime = Endtime
    a.TEST_id = id
    a.save()

    return redirect(f'/myapp/company_add_questions2_get/{id}')


def company_edit_schedule_get(request, id):
    data = Schedule.objects.get(id=id)
    return render(request, 'company/edit_schedule.html', {'data': data})


def company_edit_schedule_post(request):
    date = request.POST['Date']
    Starttime = request.POST['stime']
    Endtime = request.POST['time']
    Test = request.POST['Test']
    id = request.POST['id']
    a = Schedule.objects.get(id=id)
    a.Date = date
    a.Starttime = Starttime
    a.Endtime = Endtime
    a.TEST_id = Test
    a.save()
    return redirect(f'/myapp/company_view_schedule/{a.TEST_id}')


def company_view_schedule(request, id):
    data = Schedule.objects.filter(TEST_id=id)
    return render(request, 'company/view_schedule.html', {'data': data})


def company_delete_schedule(request, id):
    try:
        schedule_to_delete = Schedule.objects.get(id=id)
        test_id = schedule_to_delete.TEST_id
        schedule_to_delete.delete()
        return redirect(f'/myapp/company_view_schedule/{test_id}')
    except Schedule.DoesNotExist:
        return redirect('/myapp/company_view_vacancy/')


def company_add_test_get(request, vid):
    return render(request, 'company/add_test.html', {'vid': vid})


def company_add_test_post(request):
    if request.method == 'POST':
        v_id = request.POST.get('vid')
        t_name = request.POST.get('Name') or request.POST.get('name')

        now = datetime.now()
        t_date = now.strftime('%Y-%m-%d')
        t_time = now.strftime('%H:%M:%S')

        Test.objects.create(VACANCY_id=v_id, Name=t_name, Date=t_date, Time=t_time)

        thread = threading.Thread(target=send_exam_schedule_emails, args=(v_id, t_name, t_date, t_time))
        thread.start()

        return HttpResponse(
            '''<script>alert("Test Added & Emails Sent to Candidates!");window.location="/myapp/company_view_vacancy/"</script>''')


def company_edit_test_get(request, id):
    data = Test.objects.get(id=id)
    return render(request, 'company/edit_test.html', {'data': data})


def company_edit_test_post(request):
    if request.method == 'POST':
        test_id = request.POST.get('id')
        name = request.POST.get('Name') or request.POST.get('name')
        date = request.POST.get('Date') or request.POST.get('date')
        time = request.POST.get('Time') or request.POST.get('time')
        a = Test.objects.get(id=test_id)
        a.Name = name
        a.Date = date
        a.Time = time
        a.save()
        return redirect(f'/myapp/company_view_test/{a.VACANCY_id}')


def company_view_test(request, vid):
    data = Test.objects.filter(VACANCY_id=vid)
    return render(request, 'company/view_test.html', {'data': data, 'vid': vid})


def company_add_vacancy_get(request):
    return render(request, 'company/add_vacancy.html')


def company_add_vacancy_post(request):
    Position = request.POST['Position']
    Number_of_vacancies = request.POST['Number_of_vacancies']
    Description = request.POST['Description']

    a = Vacancy()
    a.Position = Position
    a.Number_of_vacancies = Number_of_vacancies
    a.Date = datetime.now().strftime('%Y-%m-%d')
    a.Description = Description
    a.COMPANY = Company.objects.get(AUTHUSER_id=request.user.id)
    a.save()

    return redirect('/myapp/company_view_vacancy/')


def company_edit_vacancy_get(request, id):
    data = Vacancy.objects.get(id=id)
    return render(request, 'company/edit_vacancy.html', {'data': data})


def company_edit_vacancy_post(request):
    Position = request.POST['Position']
    Number_of_vacancies = request.POST['Number_of_vacancies']
    Date = request.POST['Date']
    Description = request.POST['Description']
    id = request.POST['id']
    a = Vacancy.objects.get(id=id)
    a.Position = Position
    a.Number_of_vacancies = Number_of_vacancies
    a.Date = Date
    a.Description = Description
    a.COMPANY = Company.objects.get(AUTHUSER_id=request.user.id)
    a.save()
    return redirect('/myapp/company_view_vacancy/')


def company_delete_vacancy(request, id):
    Vacancy.objects.get(id=id).delete()
    return redirect('/myapp/company_view_vacancy/')


def company_view_vacancy(request):
    data = Vacancy.objects.filter(COMPANY__AUTHUSER_id=request.user)
    return render(request, 'company/view_vacancy.html', {'data': data})


def company_change_password_get(request):
    return render(request, 'company/change_password.html')


def company_change_password_post(request):
    currentpassword = request.POST['currentpassword']
    newpassword = request.POST['newpassword']
    confirmpassword = request.POST['confirmpassword']
    user = request.user
    if check_password(currentpassword, request.user.password):
        if newpassword == confirmpassword:
            user.set_password(newpassword)
            user.save()
            return redirect('/myapp/login_get/')
        else:
            return redirect('/myapp/company_change_password_get/')
    else:
        return redirect('/myapp/company_change_password_get/')


def company_view_shortlisted(request, id):
    # Depending on your Shortlist model, this might also need fixing if it uses VACCANCY_REQ
    data = Shortlist.objects.filter(VACCANCY_REQ_id=id)
    return render(request, 'company/view_shortlisted.html', {'data': data})


def company_view_feedback(request):
    data = Feedback.objects.filter(COMPANY__AUTHUSER_id=request.user.id)
    return render(request, 'company/viewfeedback.html', {'data': data})


# ==========================================
# RESTORED AI PROCTORING & ANALYSIS
# ==========================================

def analyze_with_gemini(proctor_activities, avg_mark):
    try:
        activity_summary = []
        for activity in proctor_activities[:20]:
            activity_summary.append(f"{activity.Type} at {activity.time}")

        activities_text = "\n".join(activity_summary) if activity_summary else "No activities recorded"

        prompt = f"""
        Analyze this student's exam behavior based on their proctor activity log and marks.
        Exam Marks: {avg_mark}/100
        Proctor Activities:
        {activities_text}
        Based on the activities, determine:
        1. Focus Level (Focused, Distracted, or Active)
        2. Overall Score (0-100) combining marks and behavior
        3. Brief reason for the score
        Return ONLY a valid JSON object in this exact format:
        {{
            "focus_level": "Focused",
            "overall_score": 85,
            "reason": "Brief explanation here"
        }}
        """

        client = genai.Client(api_key='AIzaSyAxzwbZouYSStwhtedYBql5_iDbdVpXEtU')
        response = safe_gemini_request(client, model='gemini-2.5-flash', contents=prompt)

        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean_text)
        return result

    except Exception as e:
        print(f"Gemini API Error: {e}")
        return fallback_analysis(proctor_activities, avg_mark)


def fallback_analysis(proctor_activities, avg_mark):
    if proctor_activities:
        total = proctor_activities.count()
        distracted = 0
        focused = 0
        for act in proctor_activities:
            act_type = act.Type.lower()
            if any(word in act_type for word in ['left', 'phone', 'away', 'multiple', 'distracted']):
                distracted += 1
            elif any(word in act_type for word in ['screen', 'focused', 'writing', 'reading']):
                focused += 1
        if total > 0:
            focus_ratio = (focused - distracted) / total
            if focus_ratio > 0.3:
                focus_level = "Focused"
            elif focus_ratio < -0.3:
                focus_level = "Distracted"
            else:
                focus_level = "Active"
            behavior_score = 50 + (focus_ratio * 50)
            overall_score = (avg_mark * 0.7) + (behavior_score * 0.3)
        else:
            focus_level = "Unknown"
            overall_score = avg_mark
    else:
        focus_level = "No Data"
        overall_score = avg_mark

    return {
        "focus_level": focus_level,
        "overall_score": round(overall_score, 2),
        "reason": "Based on keyword analysis (fallback mode)"
    }


def company_user_list(request, vid, uid):
    users = Users.objects.filter(id=uid)
    # 🔥 FIX: Changed VACCANCY_REQ to VACANCY_id to match model
    test = Test.objects.filter(VACANCY_id=vid).first()

    user_data = []
    if test:
        for user in users:
            activities = Proctoractivity.objects.filter(USERS_id=uid, SCHEDULE__TEST=test)
            results = Result.objects.filter(USERS_id=uid, QUESTIONS__TEST=test)
            marks = [float(r.Mark) for r in results if r.Mark]
            avg_mark = sum(marks) / len(marks) if marks else 0
            ai_result = analyze_with_gemini(activities, avg_mark)
            user_data.append({
                'id': user.id,
                'Name': user.Name,
                'Email': user.Email,
                'Phone': user.Phone,
                'Post': user.Post,
                'Place': user.Place,
                'State': user.State,
                'Pincode': user.Pincode,
                'Photo': user.Photo,
                'DOB': user.DOB,
                'CV': user.CV,
                'ai_focus_level': ai_result.get('focus_level', 'Unknown'),
                'ai_overall_score': ai_result.get('overall_score', avg_mark),
                'ai_reason': ai_result.get('reason', 'Analysis completed'),
                'avg_mark': round(avg_mark, 2),
                'total_activities': activities.count(),
            })
    user_data = sorted(user_data, key=lambda x: float(x['ai_overall_score']), reverse=True)
    context = {
        'data': user_data,
        'vid': vid
    }
    return render(request, 'company/view_users.html', context)


def company_add_shortlist(request, vid, uid):
    obj = Shortlist()
    obj.USERS = Users.objects.get(id=uid)
    obj.Date = datetime.now().today()
    obj.Status = 'Shortlisted'
    obj.VACCANCY_REQ = Vacancy_request.objects.get(id=vid)
    obj.save()
    return redirect("/myapp/company_view_shortlisted/#a")


def company_view_activity(request, vid, uid):
    data = Users.objects.filter(id=uid)
    try:
        # First see if vid is a Test ID
        test = Test.objects.get(id=vid)
    except Test.DoesNotExist:
        # 🔥 FIX: If it's a Vacancy ID from Placed Candidates, filter by VACANCY_id
        test = Test.objects.filter(VACANCY_id=vid).first()

    # Safety check so it doesn't crash if no test exists for the vacancy
    if not test:
        return HttpResponse("<script>alert('No test activity found for this vacancy.');window.history.back();</script>")

    rslt = Result.objects.filter(
        USERS_id=uid,
        QUESTIONS__TEST=test
    )

    act = Proctoractivity.objects.filter(
        USERS_id=uid,
        SCHEDULE__TEST=test
    )

    headr = act.filter(Type='Looking Right').count()
    headl = act.filter(Type='Looking Left').count()
    eyel = act.filter(Type='Eye Looking left').count()
    eyer = act.filter(Type='Eye Looking right').count()
    invalid_face = act.filter(Type='invalid person').count()
    no_face = act.filter(Type='No Face Detected').count()
    multi_face = act.filter(Type='Multiple Person Detected').count()
    obj_phone = act.filter(Type='Object Detected: Only Phone detected').count()
    obj_lap = act.filter(Type='Object Detected: Only Laptop detected').count()
    obj_both = act.filter(Type='Both Phone and Laptop detected').count()

    audio_results = rslt.filter(QUESTIONS__type='Audio')
    total_audio = audio_results.count()

    if total_audio > 0:
        ai_score = sum(r.ai_score for r in audio_results) / total_audio
        acoustic_score = sum(r.acoustic_score for r in audio_results) / total_audio
        overall_score = sum(r.overall_score for r in audio_results) / total_audio
    else:
        ai_score = 0.0
        acoustic_score = 0.0
        overall_score = 0.0

    context = {
        'data': data,
        'vid': vid,
        'results': rslt,
        'activities': act.order_by('-id'),
        'headr': headr, 'headl': headl,
        'eyel': eyel, 'eyer': eyer,
        'invalid_face': invalid_face, 'no_face': no_face, 'multi_face': multi_face,
        'obj_phone': obj_phone, 'obj_lap': obj_lap, 'obj_both': obj_both,
        'ai_score': round(ai_score, 1),
        'acoustic_score': round(acoustic_score, 1),
        'overall_score': round(overall_score, 1),
    }

    return render(request, 'company/view activity.html', context)


def company_add_questions_csv_post(request):
    if request.method == 'POST':
        test_id = request.POST.get('id')
        csv_file = request.FILES['csv_file']
        decoded_file = csv_file.read().decode('utf-8').splitlines()
        reader = csv.DictReader(decoded_file)
        for row in reader:
            Questions2.objects.create(
                TEST_id=test_id,
                questions=row['questions'],
                type=row['type'],
                option1=row['option1'],
                option2=row['option2'],
                option3=row['option3'],
                option4=row['option4'],
                Answer=row['Answer']
            )
        return HttpResponse(
            '''<script>alert("Questions Uploaded Successfully");window.location="/myapp/company_view_vacancy/"</script>''')


def view_vacancy_request(request):
    a = Vacancy_request.objects.filter(VACANCY__COMPANY__AUTHUSER_id=request.user.id)
    return render(request, 'company/user_applications.html', {'data': a})


def approve_vacancy_request(request, id):
    Vacancy_request.objects.filter(id=id).update(Status="Approved")
    return redirect('/myapp/view_vacancy_request/')


def reject_vacancy_request(request, id):
    Vacancy_request.objects.filter(id=id).update(Status="Rejected")
    return redirect('/myapp/view_vacancy_request/')


# ==========================================
# FLUTTER API
# ==========================================

def flutt_login(request):
    username = request.POST['email']
    password = request.POST['pass']
    user = authenticate(username=username, password=password)
    if user is not None:
        login(request, user)
        if user.groups.filter(name="User").exists():
            return JsonResponse({"status": "ok", 'lid': str(user.id)})
        else:
            return JsonResponse({"status": "no"})
    else:
        return JsonResponse({"status": "no"})


def user_signup_post(request):
    Name = request.POST['Name']
    Email = request.POST['Email']
    Phone = request.POST['phone']
    Post = request.POST['Post']
    Place = request.POST['Place']
    State = request.POST['State']
    Pincode = request.POST['Pincode']
    Photo = request.FILES['Photo']
    Gender = request.POST['Gender']
    DOB = request.POST['DOB']
    CV = request.FILES['CV']
    password = request.POST['password']

    fs = FileSystemStorage()
    date = datetime.now().strftime('%Y%m%d%H%M%S') + '.jpg'
    fs.save(date, Photo)
    path = fs.url(date)

    fs1 = FileSystemStorage()
    date1 = datetime.now().strftime('%Y%m%d%H%M%S') + '.pdf'
    fs1.save(date1, CV)
    path1 = fs1.url(date1)

    user = User.objects.create_user(username=Email, password=password)
    user.groups.add(Group.objects.get(name='User'))
    user.save()

    a = Users()
    a.Name = Name
    a.Email = Email
    a.Phone = Phone
    a.Post = Post
    a.Place = Place
    a.State = State
    a.Pincode = Pincode
    a.Photo = path
    a.Gender = Gender
    a.DOB = DOB
    a.CV = path1
    a.AUTHUSER = user
    a.save()

    return JsonResponse({'status': 'ok'})


def user_viewprofile(request):
    lid = request.POST['lid']
    a = Users.objects.get(AUTHUSER=lid)
    return JsonResponse({
        'status': 'ok',
        'Name': a.Name,
        'Email': a.Email,
        'Phone': a.Phone,
        'Post': a.Post,
        'Place': a.Place,
        'State': a.State,
        'Pincode': a.Pincode,
        'Photo': a.Photo,
        'DOB': a.DOB,
        'Gender': a.Gender,
        'CV': a.CV
    })


def user_editprofile(request):
    Name = request.POST['Name']
    Email = request.POST['Email']
    Phone = request.POST['phone']
    Post = request.POST['Post']
    Place = request.POST['Place']
    State = request.POST['State']
    Pincode = request.POST['Pincode']
    Gender = request.POST['Gender']
    DOB = request.POST['DOB']
    lid = request.POST['lid']

    a = Users.objects.get(AUTHUSER=lid)

    if 'Email' in request.POST:
        user = User.objects.get(id=lid)
        user.username = Email
        user.save()

    if 'Photo' in request.FILES:
        Photo = request.FILES['Photo']
        fs = FileSystemStorage()
        date = datetime.now().strftime('%Y%m%d%H%M%S') + '.jpg'
        fs.save(date, Photo)
        path = fs.url(date)
        a.Photo = path
        a.save()

    if 'CV' in request.FILES:
        CV = request.FILES['CV']
        fs1 = FileSystemStorage()
        date1 = datetime.now().strftime('%Y%m%d%H%M%S') + '.pdf'
        fs1.save(date1, CV)
        path1 = fs1.url(date1)
        a.CV = path1
        a.save()

    a.Name = Name
    a.Email = Email
    a.Phone = Phone
    a.Post = Post
    a.Place = Place
    a.State = State
    a.Pincode = Pincode
    a.Gender = Gender
    a.DOB = DOB
    a.save()

    return JsonResponse({'status': 'ok'})


def app_changepassword(request):
    current = request.POST['current']
    newp = request.POST['new']
    confirm = request.POST['confirm']
    lid = request.POST['lid']
    user = User.objects.get(id=lid)
    if user.check_password(current):
        if newp == confirm:
            user.set_password(newp)
            user.save()
            logout(request)
            return JsonResponse({'status': 'ok'})
        else:
            return JsonResponse({'status': 'no'})
    else:
        return JsonResponse({'status': 'no'})


@csrf_exempt
def sent_complaint(request):
    try:
        complaint = request.POST.get('complaint')
        lid = request.POST.get('lid')

        student = Users.objects.get(AUTHUSER_id=lid)

        obj = Complaint()
        obj.Date = datetime.now()
        obj.Complaint = complaint
        obj.Status = 'Pending'
        obj.Reply = 'Pending'
        obj.USERS = student
        obj.save()

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


def user_view_complaint(request):
    lid = request.POST['lid']
    l = []
    a = Complaint.objects.filter(USERS__AUTHUSER=lid)
    for i in a:
        l.append({
            'id': i.id,
            'Date': i.Date,
            'Complaint': i.Complaint,
            'Status': i.Status,
            'Reply': i.Reply,
        })
    return JsonResponse({'status': 'ok', 'data': l})


def user_view_company(request):
    l = []
    a = Company.objects.all()
    for i in a:
        l.append({
            'id': i.id,
            'Company_name': i.Company_name,
            'Company_id': i.Company_id,
            'phone': i.phone,
            'Post': i.Post,
            'City': i.City,
            'State': i.State,
            'Pincode': i.Pincode,
            'Photo': i.Photo,
            'About': i.About,
        })
    return JsonResponse({'status': 'ok', 'data': l})


@csrf_exempt
def user_view_test(request):
    try:
        lid = request.POST.get('lid')
        user = Users.objects.get(AUTHUSER_id=lid)

        approved_requests = Vacancy_request.objects.filter(USERS=user, Status__in=['Approved', 'Placed'])

        approved_vacancy_ids = [req.VACANCY.id for req in approved_requests]
        tests = Test.objects.filter(VACANCY_id__in=approved_vacancy_ids)

        test_list = []
        for t in tests:
            test_list.append({
                'id': t.id,
                'Name': t.Name,
                'Date': str(t.Date),
                'Time': str(t.Time)
            })

        return JsonResponse({'status': 'ok', 'data': test_list})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


def user_view_vacancy(request):
    cid = request.POST['cid']
    lid = request.POST['lid']
    l = []
    a = Vacancy.objects.filter(COMPANY_id=cid)
    for i in a:
        k = "no"
        if Vacancy_request.objects.filter(USERS=Users.objects.get(AUTHUSER=lid), VACANCY_id=i.id).exists():
            k = "yes"
        l.append({
            'id': i.id,
            'Position': i.Position,
            'cid': i.COMPANY.id,
            'Number_of_vacancies': i.Number_of_vacancies,
            'Date': i.Date,
            'Description': i.Description,
            'k': k,
        })
    return JsonResponse({'status': 'ok', 'data': l})


@csrf_exempt
def user_vacancy_apply(request):
    try:
        lid = request.POST['lid']
        vid = request.POST['vid']

        user = Users.objects.get(AUTHUSER_id=lid)
        vacancy = Vacancy.objects.get(id=vid)

        final_status = "pending"
        ai_reason = "Profile mismatch"

        try:
            filename = user.CV.replace('/media/', '')
            cv_path = os.path.join(settings.MEDIA_ROOT, filename)

            client = genai.Client(api_key="AIzaSyBtWqyMPqvUFiVpTjWGYb1t27VvUEuYNzE")
            cv_file = client.files.upload(file=cv_path)

            prompt = f"""
            You are an AI HR Screener. 
            Job Position: "{vacancy.Position}"
            Job Description: "{vacancy.Description}"

            Read the attached resume. Does this candidate have the minimum skills or background required for this specific job?
            Be fair but strict. 

            Return ONLY valid JSON in this exact format without markdown:
            {{
                "is_match": true,
                "reason": "Brief explanation"
            }}
            """

            response = safe_gemini_request(client, model='gemini-2.5-flash', contents=[prompt, cv_file])

            try:
                client.files.delete(name=cv_file.name)
            except:
                pass

            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_text)

            print(f"--- AI GATEKEEPER RESULT for {user.Name}: {result} ---")

            if result.get("is_match") == False:
                final_status = "Rejected"
                ai_reason = result.get("reason", "Resume does not match the job requirements.")
            else:
                final_status = "Approved"
                ai_reason = result.get("reason", "Resume matches the job requirements perfectly.")

        except Exception as ai_err:
            print(f"AI Gatekeeper Error (Falling back to pending): {ai_err}")
            final_status = "pending"

        a = Vacancy_request()
        a.Date = datetime.now()
        a.Status = final_status
        a.USERS = user
        a.VACANCY = vacancy
        a.save()

        if final_status == "Rejected":
            print(f"--> PREPARING TO SEND REJECTION EMAIL TO: {user.Email}")
            try:
                subject = f"Application Update: {vacancy.Position} at {vacancy.COMPANY.Company_name}"
                message = f"Dear {user.Name},\n\nThank you for applying for the {vacancy.Position} role.\n\nOur automated AI screening system has reviewed your resume against the specific job requirements. Unfortunately, we are unable to move forward with your application at this time.\n\nFeedback from screening:\n'{ai_reason}'\n\nWe wish you the best in your job search.\n\nBest Regards,\nSMART_HIRE Team"

                msg = MIMEText(message)
                msg['Subject'] = subject
                msg['From'] = settings.EMAIL_HOST_USER
                msg['To'] = user.Email

                server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
                server.starttls()
                server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                server.send_message(msg)
                server.quit()
            except Exception as e:
                print(f"--> REJECTION EMAIL FAILED TO SEND: {e}")

        elif final_status == "Approved":
            print(f"--> PREPARING TO SEND APPROVAL EMAIL TO: {user.Email}")
            try:
                subject = f"Application Approved! Next Steps for {vacancy.Position}"
                message = f"Dear {user.Name},\n\nGood news! Our AI screening system has reviewed your resume and found it to be a great match for the {vacancy.Position} role at {vacancy.COMPANY.Company_name}.\n\nFeedback from screening:\n'{ai_reason}'\n\nYou can now log in to the SMART_HIRE app to schedule and attend your AI-proctored interview.\n\nBest of luck!\n- SMART_HIRE Team"

                msg = MIMEText(message)
                msg['Subject'] = subject
                msg['From'] = settings.EMAIL_HOST_USER
                msg['To'] = user.Email

                server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
                server.starttls()
                server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                server.send_message(msg)
                server.quit()
            except Exception as e:
                print(f"--> APPROVAL EMAIL FAILED TO SEND: {e}")

        return JsonResponse({'status': 'ok'})


    except Exception as e:
        print(f"Apply Error: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)})


def user_view_schedule(request):
    tid = request.POST['tid']
    lid = request.POST['lid']
    l = []
    schedules = Schedule.objects.filter(TEST_id=tid)

    for i in schedules:
        if Result.objects.filter(USERS__AUTHUSER=lid, QUESTIONS__TEST=i.TEST.id).exists():
            st = 'no'
        else:
            st = 'yes'

        l.append({
            'id': i.id,
            'test_name': i.TEST.Name,
            'Starttime': i.Starttime,
            'Endtime': i.Endtime,
            'Date': i.Date,
            'TEST': i.TEST.id,
            'st': st
        })

    return JsonResponse({'status': 'ok', 'data': l})


def user_view_approved_request(request):
    lid = request.POST['lid']
    l = []

    a = Vacancy_request.objects.filter(USERS__AUTHUSER_id=lid, Status__in=["Approved", "Placed"])

    for i in a:
        l.append({
            'id': i.id,
            'Status': i.Status,
            'Date': i.Date,
            'Company_name': i.VACANCY.COMPANY.Company_name,
            'cid': i.VACANCY.COMPANY.AUTHUSER.id,
            'Position': i.VACANCY.Position,
        })
    return JsonResponse({'status': 'ok', 'data': l})


def user_sent_feedback(request):
    feedback_text = request.POST['Feedback']
    cid = request.POST['cid']
    lid = request.POST['lid']

    obj = Feedback()
    obj.Date = datetime.now().today()
    obj.Feedback = feedback_text
    obj.COMPANY_id = cid
    obj.USERS = Users.objects.get(AUTHUSER=lid)
    obj.save()

    return JsonResponse({'status': 'ok'})


def user_view_result(request):
    tid = request.POST['tid']
    lid = request.POST.get('lid')
    l = []

    a = Result.objects.filter(QUESTIONS__TEST_id=tid, USERS__AUTHUSER_id=lid)

    for i in a:
        l.append({
            'id': i.id,
            'Test': i.QUESTIONS.TEST.Name,
            'Date': i.QUESTIONS.TEST.Date,
            'Mark': str(i.Mark),
            'Question': i.QUESTIONS.questions,
            'type': i.QUESTIONS.type,
        })
    return JsonResponse({'status': 'ok', 'data': l})


def user_view_shortlist(request):
    tid = request.POST['tid']
    l = []
    a = Result.objects.filter(TEST_id=tid)
    for i in a:
        l.append({
            'id': i.id,
            'Test': i.TEST.Name,
            'Date': i.TEST.Date,
            'Mark': i.Mark,
        })
    return JsonResponse({'status': 'ok', 'data': l})


def chat1(request, id):
    request.session["userid"] = id
    cid = str(request.session["userid"])
    request.session["new"] = cid
    qry = Users.objects.get(AUTHUSER=cid)

    return render(request, "company/Chat.html", {'photo': qry.Photo, 'name': qry.Name, 'toid': cid})


def chat_view(request):
    fromid = request.user.id
    toid = request.session["userid"]
    qry = Users.objects.get(AUTHUSER=request.session["userid"])
    from django.db.models import Q

    res = Chat.objects.filter(Q(FROM_id=fromid, TO_id=toid) | Q(FROM_id=toid, TO_id=fromid)).order_by('id')
    l = []

    for i in res:
        l.append({"id": i.id, "message": i.Message, "to": i.TO_id, "date": i.Date, "time": i.Time, "from": i.FROM_id})

    return JsonResponse({'photo': qry.Photo, "data": l, 'name': qry.Name, 'toid': request.session["userid"]})


def chat_send(request, msg):
    lid = request.user.id
    toid = request.session["userid"]
    message = msg

    d = datetime.now().date()
    t = datetime.now().time()
    chatobt = Chat()
    chatobt.Message = message
    chatobt.TO_id = toid
    chatobt.FROM_id = lid
    chatobt.Date = d
    chatobt.Time = t
    chatobt.save()

    return JsonResponse({"status": "ok"})


def User_sendchat(request):
    FROM_id = request.POST['from_id']
    TOID_id = request.POST['to_id']
    msg = request.POST['message']

    c = Chat()
    c.FROM_id = FROM_id
    c.TO_id = TOID_id
    c.Message = msg
    c.Time = datetime.now()
    c.Date = datetime.now()
    c.save()
    return JsonResponse({'status': "ok"})


def User_viewchat(request):
    fromid = request.POST["from_id"]
    toid = request.POST["to_id"]
    from django.db.models import Q

    res = Chat.objects.filter(Q(FROM_id=fromid, TO_id=toid) | Q(FROM_id=toid, TO_id=fromid)).order_by('id')
    l = []

    for i in res:
        l.append({"id": i.id, "msg": i.Message, "from": i.FROM_id, "date": i.Date, "time": i.Time, "to": i.TO_id})

    return JsonResponse({"status": "ok", 'data': l})


# ==========================================
# RECENT CHATS API FOR FLUTTER
# ==========================================
@csrf_exempt
def user_recent_chats(request):
    try:
        lid = request.POST.get('lid')

        approved_apps = Vacancy_request.objects.filter(
            USERS__AUTHUSER_id=lid,
            Status__in=['Approved', 'Placed']
        )

        chat_data = []
        seen_companies = set()

        for app in approved_apps:
            company_id = app.VACANCY.COMPANY.AUTHUSER.id

            if company_id not in seen_companies:
                chat_data.append({
                    'cid': company_id,
                    'company_name': app.VACANCY.COMPANY.Company_name,
                    'last_message': 'Tap to view conversation'
                })
                seen_companies.add(company_id)

        return JsonResponse({'status': 'ok', 'data': chat_data})

    except Exception as e:
        print("Error in user_recent_chats:", str(e))
        return JsonResponse({'status': 'error', 'message': str(e)})


def company_view_user_details(request, vid, uid):
    # 🔥 FIX: Changed VACCANCY_REQ to VACANCY_id to match model
    test = Test.objects.filter(VACANCY_id=vid).first()
    if test:
        rslt = Result.objects.filter(USERS_id=uid, QUESTIONS__TEST=test)
        act = Proctoractivity.objects.filter(USERS_id=uid, SCHEDULE__TEST=test)
    else:
        rslt = []
        act = []

    context = {
        'results': rslt,
        'activities': act
    }
    return render(request, 'company/view_result.html', context)


def user_viewquestions2_get(request):
    test_id = request.POST['tid']
    lid = request.POST.get('lid')

    questions = Questions2.objects.filter(TEST_id=test_id)
    data = []

    for q in questions:
        res = Result.objects.filter(QUESTIONS=q, USERS__AUTHUSER_id=lid).first()
        data.append({
            "id": q.id,
            "question": q.questions,
            "option1": q.option1,
            "option2": q.option2,
            "option3": q.option3,
            "option4": q.option4,
            "correctanswer": q.Answer,
            "type": q.type,
            "Mark": str(res.Mark) if res else "None",
        })

    return JsonResponse({"status": "ok", "data": data})


def user_submit_answer(request):
    test_id = request.POST['test_id']
    question_id = request.POST['question_id']
    selected = request.POST['selected_answer']
    correct = request.POST['correct_answer']

    mark = 1 if selected == correct else 0

    Result.objects.create(
        TEST_id=test_id,
        QUESTIONS_id=question_id,
        Mark=mark
    )

    return JsonResponse({"status": "ok"})


# ==========================================
# RESTORED PROCTORING & AUDIO VERIFICATION
# ==========================================

@csrf_exempt
def verify_face(request):
    photo = request.FILES['photo']
    test_id = request.POST['tid']
    eid = request.POST['eid']
    lid = request.POST['lid']

    student = Users.objects.get(AUTHUSER=lid)

    fs = FileSystemStorage()
    filename = fs.save(datetime.now().strftime("%Y%m%d-%H%M%S") + ".jpg", photo)

    image_path = fs.path(filename)

    with ai_lock:
        result = process_exam_photo(image_path, student, eid)

    if result == "invalid person" or result == "multiple person":
        return JsonResponse({"status": "invalid"})
    else:
        return JsonResponse({"status": "ok"})


def back_action_required(request):
    sid = request.POST["sid"]
    eid = request.POST["eid"]

    Proctoractivity.objects.create(
        USERS=Users.objects.get(AUTHUSER=sid),
        SCHEDULE=Schedule.objects.get(id=eid),
        Date=datetime.today(),
        Type="trying to back the screen",
        photo="",
        time=datetime.now().time()
    )
    return JsonResponse({'status': 'ok'})


def noice_Detection(request):
    sid = request.POST["sid"]
    eid = request.POST["eid"]

    Proctoractivity.objects.create(
        USERS=Users.objects.get(AUTHUSER=sid),
        SCHEDULE=Schedule.objects.get(id=eid),
        Date=datetime.today(),
        Type="Noise detected",
        photo="",
        time=datetime.now().time()
    )
    return JsonResponse({'status': 'ok'})


def appswitching(request):
    sid = request.POST["sid"]
    eid = request.POST["eid"]

    Proctoractivity.objects.create(
        USERS=Users.objects.get(AUTHUSER=sid),
        SCHEDULE=Schedule.objects.get(id=eid),
        Date=datetime.today(),
        Type="App switched",
        photo="",
        time=datetime.now().time()
    )
    return JsonResponse({'status': 'ok'})


def analyze_grammar(text):
    client = genai.Client(api_key="AIzaSyDs5HOuyh1QBQ0aMc1cXhvLwqrFyObvQV4")
    prompt = f"Analyze the grammar of this spoken interview answer. Text: '{text}'. Return JSON with grammar_score, corrected_sentence, feedback"

    response = safe_gemini_request(client, model="gemini-2.5-flash", contents=prompt)
    return response.text


def analyze_confidence(audio_path):
    y, sr = librosa.load(audio_path)
    energy = np.mean(librosa.feature.rms(y=y))
    pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
    pitch_values = pitches[pitches > 0]
    pitch = np.mean(pitch_values) if len(pitch_values) > 0 else 0
    intervals = librosa.effects.split(y, top_db=20)
    pause_count = len(intervals)
    duration = librosa.get_duration(y=y, sr=sr)

    confidence_score = 0
    if energy > 0.02: confidence_score += 30
    if pitch > 120: confidence_score += 20
    if pause_count < 10: confidence_score += 30
    if duration > 2: confidence_score += 20

    return {
        "energy": float(energy),
        "pitch": float(pitch),
        "pauses": pause_count,
        "duration": duration,
        "confidence": confidence_score
    }


def evaluate_audio_answer(audio_path, correct_answer):
    client = genai.Client(api_key="AIzaSyBtWqyMPqvUFiVpTjWGYb1t27VvUEuYNzE")
    audio_file = client.files.upload(file=audio_path)
    prompt = f"Listen to this audio. Correct Concept: {correct_answer}. Transcribe verbatim, check if meaning matches, check grammar. Return ONLY raw JSON."

    response = safe_gemini_request(client, model='gemini-2.5-flash', contents=[audio_file, prompt])

    text = response.text
    start_idx = text.find('{')
    end_idx = text.rfind('}')

    if start_idx != -1 and end_idx != -1:
        clean = text[start_idx:end_idx + 1]
    else:
        clean = text.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(clean)
    except:
        result = {"transcript": "Transcript failed.", "answer_correct": False, "grammar_correct": False,
                  "confidence": 0}

    try:
        client.files.delete(name=audio_file.name)
    except:
        pass

    return result


# --- NEW BACKGROUND TASK FOR FAST SUBMISSION ---
def background_audio_analysis(path, q_obj_id, u_obj_id):
    try:
        q_obj = Questions2.objects.get(id=q_obj_id)
        u_obj = Users.objects.get(id=u_obj_id)

        transcript = ""
        ai_score = 0
        acoustic_score = 0
        is_correct = False
        overall = 0

        # Gemini Audio Analysis
        try:
            client = genai.Client(api_key="AIzaSyBtWqyMPqvUFiVpTjWGYb1t27VvUEuYNzE")
            audio_file = client.files.upload(file=path)
            prompt = f"Transcribe exactly. Compare transcription to '{q_obj.Answer}'. Return ONLY JSON: {{\"transcript\": \"...\", \"answer_correct\": true/false, \"confidence\": 0-100}}"

            response = safe_gemini_request(client, model="gemini-2.5-flash", contents=[prompt, audio_file])

            data = json.loads(response.text.replace('```json', '').replace('```', '').strip())

            transcript = data.get('transcript', '')
            ai_score = data.get('confidence', 0)
            is_correct = data.get('answer_correct', False)
            try:
                client.files.delete(name=audio_file.name)
            except:
                pass
        except Exception as ai_err:
            print(f"Gemini Audio Failed: {ai_err}")
            transcript = "Review audio manually."

        # Librosa Acoustic Score
        try:
            y, sr = librosa.load(path, sr=16000)
            if len(y) > 0:
                energy = np.sqrt(np.mean(y ** 2))
                if energy > 0.01: acoustic_score += 40
                if len(y) / sr > 1.5: acoustic_score += 30
        except:
            pass

        acoustic_score = min(acoustic_score + 30, 100)
        overall = (ai_score + acoustic_score) / 2

        # Save to DB quietly in the background
        obj = Result.objects.filter(QUESTIONS=q_obj, USERS=u_obj).first()
        if not obj:
            obj = Result(QUESTIONS=q_obj, USERS=u_obj)

        obj.Answer = transcript
        obj.ai_score = ai_score
        obj.acoustic_score = acoustic_score
        obj.overall_score = overall
        obj.Mark = "1" if is_correct else "0"
        obj.save()
        print(f"✅ Background Audio AI Finished for {u_obj.Name}!")

    except Exception as e:
        print(f"Background Audio Analysis Error: {e}")


# --- UPDATED FAST SUBMIT FUNCTION ---
@csrf_exempt
def user_addmark(request):
    try:
        qid = request.POST.get('qid')
        lid = request.POST.get('lid')
        mcq_answer = request.POST.get('answer', '').strip()
        audio = request.FILES.get('audio')

        q_obj = Questions2.objects.get(id=qid)
        u_obj = Users.objects.get(AUTHUSER_id=lid)

        question_type = str(q_obj.type).strip().lower()

        if question_type == 'audio':
            if not audio:
                return JsonResponse({'status': 'error', 'message': 'No Audio Received'})

            # Save the file instantly
            filename = f"{u_obj.id}_{q_obj.id}.aac"
            path = os.path.join(settings.MEDIA_ROOT, filename)

            with open(path, 'wb+') as destination:
                for chunk in audio.chunks():
                    destination.write(chunk)

            # 🔥 START THE HEAVY AI IN THE BACKGROUND
            thread = threading.Thread(target=background_audio_analysis, args=(path, q_obj.id, u_obj.id))
            thread.start()

            # 🔥 RETURN "OK" TO FLUTTER INSTANTLY SO IT MOVES TO NEXT QUESTION
            return JsonResponse({'status': 'ok', 'score': 0})

        else:
            # Normal MCQ logic
            transcript = mcq_answer
            if mcq_answer.lower() == str(q_obj.Answer).lower().strip():
                is_correct = True
                ai_score = 100
                overall = 100
            else:
                is_correct = False
                ai_score = 0
                overall = 0

            obj = Result.objects.filter(QUESTIONS=q_obj, USERS=u_obj).first()
            if not obj:
                obj = Result(QUESTIONS=q_obj, USERS=u_obj)

            obj.Answer = transcript
            obj.ai_score = ai_score
            obj.acoustic_score = 0
            obj.overall_score = overall
            obj.Mark = "1" if is_correct else "0"
            obj.save()

            return JsonResponse({'status': 'ok', 'score': overall})

    except Exception as e:
        print(f"Error: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)})


def view_activity(request):
    sid = request.POST.get('sid')
    lid = request.POST.get('lid')

    if not sid or not lid:
        return JsonResponse({"status": "error", "message": "Missing sid or lid"})

    queryset = Proctoractivity.objects.filter(
        USERS__AUTHUSER=lid,
        SCHEDULE=sid
    )

    activities_list = [
        {"id": s.id, "Date": s.Date, "Type": s.Type, "photo": str(s.photo), "time": s.time}
        for s in queryset
    ]

    headr = queryset.filter(Type='Looking Right').count()
    headl = queryset.filter(Type='Looking Left').count()
    eyel = queryset.filter(Type='Eye Looking left').count()
    eyer = queryset.filter(Type='Eye Looking right').count()
    invalid_face = queryset.filter(Type='invalid person').count()
    no_face = queryset.filter(Type='No Face Detected').count()
    multi_face = queryset.filter(Type='Multiple Person Detected').count()
    obj_phone = queryset.filter(Type='Object Detected: Only Phone detected').count()
    obj_lap = queryset.filter(Type='Object Detected: Only Laptop detected').count()
    obj_both = queryset.filter(Type='Both Phone and Laptop detected').count()

    user_results = Result.objects.filter(USERS__AUTHUSER=lid, QUESTIONS__type='Audio')
    total_audio = user_results.count()
    if total_audio > 0:
        ai_score = sum(r.ai_score for r in user_results) / total_audio
        acoustic_score = sum(r.acoustic_score for r in user_results) / total_audio
        overall_score = sum(r.overall_score for r in user_results) / total_audio
    else:
        ai_score = 0.0
        acoustic_score = 0.0
        overall_score = 0.0

    return JsonResponse({
        "status": "ok", "data": activities_list,
        "headr": headr, "headl": headl, "eyel": eyel, "eyer": eyer,
        "invalid_face": invalid_face, "no_face": no_face, "multi_face": multi_face,
        "obj_phone": obj_phone, "obj_both": obj_both, "obj_lap": obj_lap,
        "acoustic_score": acoustic_score, "ai_score": ai_score, "overall_score": overall_score,
    })


def app_forgot_passweord(request):
    email = request.POST['email']
    if User.objects.filter(username=email).exists():
        u = User.objects.get(username=email)
        import random
        psw = random.randint(000000, 999999)
        u.set_password(str(psw))
        u.save()
        return JsonResponse({'status': 'ok'})
    else:
        return JsonResponse({'status': 'no'})


def company_view_test_results(request, tid):
    all_results = Result.objects.filter(QUESTIONS__TEST_id=tid).select_related('USERS')
    unique_students = []
    seen_user_ids = set()
    for r in all_results:
        if r.USERS_id not in seen_user_ids:
            unique_students.append(r)
            seen_user_ids.add(r.USERS_id)
    context = {'results': unique_students, 'tid': tid}
    return render(request, 'company/view_test_results.html', context)


@csrf_exempt
def update_manual_mark(request):
    if request.method == 'POST':
        try:
            rid = request.POST.get('rid')
            new_mark = request.POST.get('mark')
            res = Result.objects.get(id=rid)
            res.Mark = new_mark
            res.save()
            return JsonResponse({'status': 'ok'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'invalid'})


def company_exam_list(request):
    tests = Test.objects.filter(VACANCY__COMPANY__AUTHUSER=request.user).distinct()
    return render(request, 'company/exam_list_shortlist.html', {'data': tests})


def company_ranked_candidates(request, tid):
    test = Test.objects.get(id=tid)
    all_results = Result.objects.filter(QUESTIONS__TEST_id=tid)
    users_dict = {}
    for r in all_results:
        uid = r.USERS.id
        if uid not in users_dict:
            users_dict[uid] = {'user': r.USERS, 'total_mcq': 0, 'correct_mcq': 0, 'total_audio': 0,
                               'audio_score_sum': 0}
        if str(r.QUESTIONS.type).lower() != 'audio':
            users_dict[uid]['total_mcq'] += 1
            if str(r.Mark) == "1":
                users_dict[uid]['correct_mcq'] += 1
        else:
            users_dict[uid]['total_audio'] += 1
            audio_score = getattr(r, 'overall_score', 0)
            users_dict[uid]['audio_score_sum'] += float(audio_score) if audio_score else 0

    ranked_list = []
    for uid, data in users_dict.items():
        user = data['user']
        mcq_percent = (data['correct_mcq'] / data['total_mcq'] * 100) if data['total_mcq'] > 0 else 0
        audio_percent = (data['audio_score_sum'] / data['total_audio']) if data['total_audio'] > 0 else 0
        if data['total_mcq'] > 0 and data['total_audio'] > 0:
            base_score = (mcq_percent + audio_percent) / 2
        elif data['total_mcq'] > 0:
            base_score = mcq_percent
        else:
            base_score = audio_percent
        violations_count = Proctoractivity.objects.filter(USERS=user, SCHEDULE__TEST=test).count()
        penalty = violations_count * 5
        final_score = base_score - penalty
        if final_score < 0: final_score = 0
        ranked_list.append(
            {'user': user, 'base_score': round(base_score, 1), 'violations': violations_count, 'penalty': penalty,
             'final_score': round(final_score, 1)})

    ranked_list = sorted(ranked_list, key=lambda x: x['final_score'], reverse=True)
    return render(request, 'company/ranked_candidates.html', {'data': ranked_list, 'test': test})


def company_delete_test(request, id):
    test_to_delete = Test.objects.get(id=id)
    vacancy_id = test_to_delete.VACANCY_id
    test_to_delete.delete()
    return redirect(f'/myapp/company_view_test/{vacancy_id}')


def company_place_students(request, tid):
    if request.method == 'POST':
        num_students = int(request.POST.get('num_students', 0))
        test = Test.objects.get(id=tid)
        all_results = Result.objects.filter(QUESTIONS__TEST_id=tid)
        users_dict = {}
        for r in all_results:
            uid = r.USERS.id
            if uid not in users_dict:
                users_dict[uid] = {'user': r.USERS, 'total_mcq': 0, 'correct_mcq': 0, 'total_audio': 0,
                                   'audio_score_sum': 0}
            if str(r.QUESTIONS.type).lower() != 'audio':
                users_dict[uid]['total_mcq'] += 1
                if str(r.Mark) == "1":
                    users_dict[uid]['correct_mcq'] += 1
            else:
                users_dict[uid]['total_audio'] += 1
                audio_score = getattr(r, 'overall_score', 0)
                users_dict[uid]['audio_score_sum'] += float(audio_score) if audio_score else 0

        ranked_list = []
        for uid, data in users_dict.items():
            user = data['user']
            mcq_percent = (data['correct_mcq'] / data['total_mcq'] * 100) if data['total_mcq'] > 0 else 0
            audio_percent = (data['audio_score_sum'] / data['total_audio']) if data['total_audio'] > 0 else 0
            if data['total_mcq'] > 0 and data['total_audio'] > 0:
                base_score = (mcq_percent + audio_percent) / 2
            elif data['total_mcq'] > 0:
                base_score = mcq_percent
            else:
                base_score = audio_percent
            violations_count = Proctoractivity.objects.filter(USERS=user, SCHEDULE__TEST=test).count()
            final_score = base_score - (violations_count * 5)
            if final_score < 0: final_score = 0
            ranked_list.append({'user': user, 'final_score': round(final_score, 1)})

        ranked_list = sorted(ranked_list, key=lambda x: x['final_score'], reverse=True)
        top_students = ranked_list[:num_students]

        for item in top_students:
            u = item['user']
            Vacancy_request.objects.filter(VACANCY=test.VACANCY, USERS=u).update(Status='Placed')
            try:
                subject = 'Congratulations! You are Hired 🎉'
                message = f"Dear {u.Name},\n\nCongratulations! You have been successfully placed for the position of {test.VACANCY.Position} at {test.VACANCY.COMPANY.Company_name}.\n\nYour final AI-Proctored Exam Score was {item['final_score']}%.\nThe company will contact you shortly with the next steps.\n\nWelcome aboard!\n- SMART_HIRE Team"
                msg = MIMEText(message)
                msg['Subject'] = subject
                msg['From'] = settings.EMAIL_HOST_USER
                msg['To'] = u.Email
                server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
                server.starttls()
                server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                server.send_message(msg)
                server.quit()
            except Exception as e:
                print(f"DEBUG: Email failed to send to {u.Email}: {e}")

        return HttpResponse(
            f'''<script>alert("Successfully Placed {len(top_students)} candidates! Emails have been sent.");window.location="/myapp/company_ranked_candidates/{tid}"</script>''')


@csrf_exempt
def check_user_notifications(request):
    try:
        lid = request.POST.get('lid')
        placements = Vacancy_request.objects.filter(USERS__AUTHUSER_id=lid, Status='Placed')
        notifications = []
        for p in placements:
            notifications.append({
                'title': 'You got the Job! 🎉',
                'message': f'Congratulations! You have been placed at {p.VACANCY.COMPANY.Company_name} as a {p.VACANCY.Position}.'
            })
        return JsonResponse({'status': 'ok', 'data': notifications})
    except Exception as e:
        return JsonResponse({'status': 'error'})


def download_placed_candidates(request, tid):
    test = Test.objects.get(id=tid)
    placed_students = Vacancy_request.objects.filter(VACANCY=test.VACANCY, Status='Placed')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="Hired_Candidates_{test.Name}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Sl No.', 'Candidate Name', 'Email', 'Phone', 'Gender', 'DOB', 'Location', 'Job Position'])
    for index, req in enumerate(placed_students, start=1):
        u = req.USERS
        full_address = f"{u.Place}, {u.State} - {u.Pincode}"
        writer.writerow([index, u.Name, u.Email, u.Phone, u.Gender, u.DOB, full_address, req.VACANCY.Position])
    return response


def update_audio_mark(request, result_id, new_mark):
    result = Result.objects.get(id=result_id)
    result.Mark = new_mark
    result.save()
    return redirect(request.META.get('HTTP_REFERER', '/'))


# ==========================================
# AI COPILOT: QUESTION GENERATOR
# ==========================================
def company_generate_ai_questions_get(request, id):
    return render(request, 'company/generate_ai_questions.html', {'tid': id})


def company_generate_ai_questions_post(request):
    if request.method == 'POST':
        tid = request.POST.get('tid')
        description = request.POST.get('description')
        num_questions = request.POST.get('num_questions', 5)

        try:
            client = genai.Client(api_key="AIzaSyBtWqyMPqvUFiVpTjWGYb1t27VvUEuYNzE")

            prompt = f"""
            You are an expert technical recruiter and exam creator. 
            Read this job requirement: "{description}"

            Generate exactly {num_questions} interview questions for this role. Make them a mix of MCQ ("Normal") and spoken ("Audio") questions.

            Return ONLY a raw JSON array. Do NOT include markdown formatting like ```json.

            Format strictly like this:
            [
              {{
                "type": "Normal",
                "questions": "What is the primary use of Django?",
                "option1": "Web development",
                "option2": "Data analysis",
                "option3": "Game dev",
                "option4": "OS creation",
                "Answer": "Web development"
              }},
              {{
                "type": "Audio",
                "questions": "Explain how REST APIs work.",
                "option1": "",
                "option2": "",
                "option3": "",
                "option4": "",
                "Answer": "Client-server architecture communicating over HTTP using standard methods like GET and POST."
              }}
            ]
            """

            response = safe_gemini_request(client, model='gemini-2.5-flash', contents=prompt)

            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            questions_data = json.loads(clean_text)

            for q in questions_data:
                Questions2.objects.create(
                    TEST_id=tid,
                    type=q.get('type', 'Normal'),
                    questions=q.get('questions', ''),
                    option1=q.get('option1', ''),
                    option2=q.get('option2', ''),
                    option3=q.get('option3', ''),
                    option4=q.get('option4', ''),
                    Answer=q.get('Answer', '')
                )

            return HttpResponse(
                f'''<script>alert("Successfully generated {num_questions} AI questions!");window.location="/myapp/company_view_questions2/{tid}#a"</script>''')

        except Exception as e:
            print(f"AI Generation Error: {e}")
            return HttpResponse(
                f'''<script>alert("Error generating questions. Please try again.");window.history.back();</script>''')


# ==========================================
# AI COPILOT: RESUME VS REALITY INSIGHTS
# ==========================================
def generate_candidate_ai_report(request, uid, tid):
    try:
        student = Users.objects.get(id=uid)
        test = Test.objects.get(id=tid)
        results = Result.objects.filter(USERS=student, QUESTIONS__TEST=test)

        qa_text = ""
        for r in results:
            qa_text += f"Question: {r.QUESTIONS.questions}\nAnswer Given: {r.Answer}\n\n"

        if not qa_text.strip():
            qa_text = "The candidate did not submit any valid answers."

        filename = student.CV.replace('/media/', '')
        cv_path = os.path.join(settings.MEDIA_ROOT, filename)

        client = genai.Client(api_key="AIzaSyBtWqyMPqvUFiVpTjWGYb1t27VvUEuYNzE")
        cv_file = client.files.upload(file=cv_path)

        prompt = f"""
        You are an expert technical interviewer and behavioral analyst.
        I am providing you with the candidate's uploaded resume (the document) and the exact answers they gave during their technical interview.

        Interview Transcripts:
        {qa_text}

        Task:
        1. Compare their spoken/written answers against the skills and experience claimed in their resume.
        2. Do they actually sound like they know what they claimed? Are they exaggerating?
        3. Identify their top 3 soft skills based on how they answered.

        Return ONLY a raw JSON format exactly like this, with no markdown formatting:
        {{
            "consistency_score": 85,
            "analysis": "Brief paragraph explaining if their answers match their resume claims.",
            "soft_skills": ["Skill 1", "Skill 2", "Skill 3"],
            "red_flags": "Any exaggerations or concerns found (or 'None' if perfectly honest)."
        }}
        """

        response = safe_gemini_request(client, model='gemini-2.5-flash', contents=[prompt, cv_file])

        try:
            client.files.delete(name=cv_file.name)
        except:
            pass

        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        report_data = json.loads(clean_text)

        context = {
            'student': student,
            'test': test,
            'report': report_data
        }

        return render(request, 'company/ai_report.html', context)

    except Exception as e:
        print(f"AI Report Error: {e}")
        return HttpResponse(
            f'''<script>alert("Error generating AI report. Ensure the user has uploaded a valid CV.");window.history.back();</script>''')


def send_exam_schedule_emails(v_id, t_name, t_date, t_time):
    """Runs in the background to send exam schedule emails without freezing the server."""
    try:
        approved_candidates = Vacancy_request.objects.filter(VACANCY_id=v_id, Status='Approved')
        vacancy_obj = Vacancy.objects.get(id=v_id)
        company_name = vacancy_obj.COMPANY.Company_name
        position = vacancy_obj.Position

        for req in approved_candidates:
            user = req.USERS
            try:
                subject = f"Exam Scheduled: {position} at {company_name}"
                message = f"Dear {user.Name},\n\nGood news! An AI-Proctored Exam has been scheduled for your application for the {position} role at {company_name}.\n\nExam Details:\n- Exam Name: {t_name}\n- Date: {t_date}\n- Time: {t_time}\n\nPlease log in to the SMART_HIRE app to view the questions and attend the exam.\n\nBest of luck!\n- SMART_HIRE Team"

                msg = MIMEText(message)
                msg['Subject'] = subject
                msg['From'] = settings.EMAIL_HOST_USER
                msg['To'] = user.Email

                server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
                server.starttls()
                server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                server.send_message(msg)
                server.quit()

                print(f"✅ Exam schedule email sent to {user.Email}")
            except Exception as e:
                print(f"❌ Failed to send exam email to {user.Email}: {e}")

    except Exception as e:
        print(f"Error in background email thread: {e}")


def company_message_list(request):
    approved_apps = Vacancy_request.objects.filter(
        VACANCY__COMPANY__AUTHUSER=request.user,
        Status__in=['Approved', 'Placed']
    )

    chat_users = []
    seen_users = set()

    for app in approved_apps:
        uid = app.USERS.AUTHUSER.id
        if uid not in seen_users:
            chat_users.append({
                'auth_id': uid,
                'name': app.USERS.Name,
                'photo': app.USERS.Photo,
                'position': app.VACANCY.Position,
                'status': app.Status
            })
            seen_users.add(uid)

    return render(request, 'company/message_list.html', {'data': chat_users})