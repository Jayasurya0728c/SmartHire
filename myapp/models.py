from django.contrib.auth.models import User
from django.db import models

# Create your models here.
class Company(models.Model):
    Company_name=models.CharField(max_length=200)
    Company_id=models.CharField(max_length=100)
    Email=models.CharField(max_length=50)
    phone=models.CharField(max_length=50)
    License=models.CharField(max_length=100)
    Post=models.CharField(max_length=100)
    City=models.CharField(max_length=200)
    State=models.CharField(max_length=200)
    Pincode=models.CharField(max_length=100)
    Photo=models.CharField(max_length=100)
    About=models.CharField(max_length=500) # Increased length
    Status=models.CharField(max_length=100)
    AUTHUSER=models.OneToOneField(User,on_delete=models.CASCADE)


class Vacancy(models.Model):
    COMPANY=models.ForeignKey(Company,on_delete=models.CASCADE)
    Position=models.CharField(max_length=200)
    Number_of_vacancies =models.CharField(max_length=200)
    Date = models.DateField()
    Description=models.CharField(max_length=500) # Increased length

class Users(models.Model):
    Name=models.CharField(max_length=100)
    Email=models.CharField(max_length=50)
    Phone=models.CharField(max_length=100)
    Post=models.CharField(max_length=100)
    Place=models.CharField(max_length=200)
    State=models.CharField(max_length=200)
    Pincode=models.CharField(max_length=100)
    Photo=models.CharField(max_length=100)
    DOB=models.CharField(max_length=100)
    Gender=models.CharField(max_length=100,default='')
    CV=models.CharField(max_length=100)
    AUTHUSER=models.OneToOneField(User,on_delete=models.CASCADE)

class Chat(models.Model):
    FROM=models.ForeignKey(User,on_delete=models.CASCADE,related_name="fromc")
    TO=models.ForeignKey(User,on_delete=models.CASCADE,related_name="toc")
    Date=models.DateField()
    Time=models.TextField()
    Message=models.CharField(max_length=500) # Increased length

class Feedback(models.Model):
    USERS=models.ForeignKey(Users,on_delete=models.CASCADE)
    COMPANY=models.ForeignKey(Company,on_delete=models.CASCADE)
    # Changed to TextField to allow long user feedback
    Feedback=models.TextField()
    Date=models.DateField()

class Complaint(models.Model):
    USERS=models.ForeignKey(Users,on_delete=models.CASCADE)
    # --- FIXED: Changed to TextField to stop the 'Data too long' error ---
    Complaint=models.TextField()
    Date=models.DateField()
    Reply=models.TextField(default="Pending") # Changed to TextField for long replies
    Status=models.CharField(max_length=200)

class Vacancy_request(models.Model):
    Date=models.DateField()
    Status=models.CharField(max_length=100)
    VACANCY=models.ForeignKey(Vacancy,on_delete=models.CASCADE)
    USERS=models.ForeignKey(Users,on_delete=models.CASCADE)

class Test(models.Model):
    VACANCY = models.ForeignKey(Vacancy, on_delete=models.CASCADE, null=True)
    Name = models.CharField(max_length=50)
    Date = models.DateField()
    Time = models.TextField()

class Questions2(models.Model):
    questions=models.CharField(max_length=500) # Increased length
    type=models.CharField(max_length=100,default="")
    option1=models.CharField(max_length=200)
    option2=models.CharField(max_length=200)
    option3=models.CharField(max_length=200)
    option4=models.CharField(max_length=200)
    Answer=models.CharField(max_length=500)
    TEST=models.ForeignKey(Test,on_delete=models.CASCADE)

class Schedule(models.Model):
    TEST=models.ForeignKey(Test,on_delete=models.CASCADE)
    Starttime=models.TimeField()
    Endtime=models.TimeField()
    Date=models.DateField()

class Result(models.Model):
    USERS=models.ForeignKey(Users,on_delete=models.CASCADE)
    Mark=models.CharField(max_length=50)
    QUESTIONS=models.ForeignKey(Questions2,on_delete=models.CASCADE)
    Answer = models.TextField(max_length=5000)
    acoustic_score = models.FloatField(default=0.0)
    ai_score = models.FloatField(default=0.0)
    overall_score = models.FloatField(default=0.0)

class Proctoractivity(models.Model):
    Date=models.DateField()
    SCHEDULE=models.ForeignKey(Schedule,on_delete=models.CASCADE)
    USERS=models.ForeignKey(Users,on_delete=models.CASCADE)
    Type=models.CharField(max_length=200)
    photo=models.CharField(max_length=200)
    time=models.CharField(max_length=100)

class Shortlist(models.Model):
    USERS=models.ForeignKey(Users,on_delete=models.CASCADE)
    VACCANCY_REQ=models.ForeignKey(Vacancy_request,on_delete=models.CASCADE)
    Date=models.DateField()
    Status=models.CharField(max_length=100)