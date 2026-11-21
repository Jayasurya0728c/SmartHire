# utils/photo_processing.py

import datetime
import face_recognition

from myapp.models import *

import cv2
import mediapipe as mp
import numpy as np
import cv2

from myapp.static.gaze_tracking import GazeTracking

model_path = r"C:\project\SMART_HIRE\SMART_HIRE\myapp\face_landmarker.task"  # downloaded or provided .task model

        # Create the FaceLandmarker task
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

base_options = python.BaseOptions(model_asset_path=model_path)
options = vision.FaceLandmarkerOptions(
    base_options=base_options,
    output_face_blendshapes=True,
    output_facial_transformation_matrixes=True,
    num_faces=1
)
face_landmarker = vision.FaceLandmarker.create_from_options(options)

# from myapp.views import emotionrec, hand
from ultralytics import YOLO

# Load model
model = YOLO("yolov8n.pt")

# Detect only laptop and phone

def process_exam_photo(imgpaths, student, eid):
    photo_path = student.Photo.replace("/media/", "")
    known_path = f"C:/project/SMART_HIRE/SMART_HIRE/media/{photo_path}"

    known_img = face_recognition.load_image_file(known_path)
    known_encoding = face_recognition.face_encodings(known_img)[0]
    frame = cv2.imread(imgpaths)

    # ==========================================================
    # 1. RUN OBJECT DETECTION FIRST!
    # (Do this before face checks so they can't hide behind a phone)
    # ==========================================================

    # Added conf=0.15 to make it SUPER sensitive to catching phones
    results = model(imgpaths, classes=[63, 67], conf=0.15)
    names = model.names

    phone_detected = False
    laptop_detected = False

    for r in results:
        for cls in r.boxes.cls:
            label = names[int(cls)]
            if label == "cell phone":
                phone_detected = True
            elif label == "laptop":
                laptop_detected = True

    dob = "no"
    if phone_detected and laptop_detected:
        dob = "Both Phone and Laptop detected"  # Matches views.py exactly
    elif phone_detected:
        dob = "Object Detected: Only Phone detected"  # Matches views.py exactly
    elif laptop_detected:
        dob = "Object Detected: Only Laptop detected"  # Matches views.py exactly

    if dob != "no":
        print(f"AI CAUGHT AN OBJECT: {dob}")
        Proctoractivity.objects.create(
            USERS=student,
            SCHEDULE=Schedule.objects.get(id=eid),
            Date=datetime.datetime.today(),
            Type=dob,
            photo=imgpaths,
            time=datetime.datetime.now().time()
        )

    # ==========================================================
    # 2. RUN FACE RECOGNITION
    # ==========================================================
    unknown = face_recognition.face_encodings(frame)
    print("Detected Faces:", len(unknown))

    if len(unknown) != 1:
        title = "Multiple Person Detected" if len(unknown) > 1 else "No Face Detected"
        Proctoractivity.objects.create(
            USERS=student,
            SCHEDULE=Schedule.objects.get(id=eid),
            Date=datetime.datetime.today(),
            Type=title,
            photo=imgpaths,
            time=datetime.datetime.now().time()
        )
        return "multiple person"  # Exits here if face is bad

    if len(unknown) == 1:
        match = face_recognition.compare_faces([known_encoding], unknown[0])[0]
        if not match:
            Proctoractivity.objects.create(
                USERS=student,
                SCHEDULE=Schedule.objects.get(id=eid),
                Date=datetime.datetime.today(),
                Type="invalid person",
                photo=imgpaths,
                time=datetime.datetime.now().time()
            )
            return "invalid person"  # Exits here if wrong person

    # ==========================================================
    # 3. RUN MEDIAPIPE HEAD POSE
    # ==========================================================
    face_3d = []
    mp_image = mp.Image.create_from_file(imgpaths)
    mp_results = face_landmarker.detect(mp_image)

    img_h, img_w, _ = frame.shape
    face_2d = []
    direction = "Forward"

    if mp_results.face_landmarks:
        for face_landmarks in mp_results.face_landmarks:
            for idx, lm in enumerate(face_landmarks):
                if idx in [33, 263, 1, 61, 291, 199]:
                    x, y = int(lm.x * img_w), int(lm.y * img_h)
                    face_2d.append([x, y])
                    face_3d.append([x, y, lm.z])

        face_2d = np.array(face_2d, dtype=np.float64)
        face_3d = np.array(face_3d, dtype=np.float64)

        focal_length = 1 * img_w
        cam_matrix = np.array([[focal_length, 0, img_w / 2],
                               [0, focal_length, img_h / 2],
                               [0, 0, 1]])
        dist_matrix = np.zeros((4, 1), dtype=np.float64)

        success, rot_vec, trans_vec = cv2.solvePnP(face_3d, face_2d, cam_matrix, dist_matrix)
        rmat, _ = cv2.Rodrigues(rot_vec)
        angles, *_ = cv2.RQDecomp3x3(rmat)
        x_angle = angles[0] * 360
        y_angle = angles[1] * 360

        if y_angle < 3:
            direction = "Looking Left"
        elif y_angle > 5:
            direction = "Looking Right"
        elif x_angle < -5:
            direction = "Looking Down"

    # Optimization: Only save to database if they are actually cheating (not looking forward)
    if direction != "Forward":
        Proctoractivity.objects.create(
            USERS=student,
            SCHEDULE=Schedule.objects.get(id=eid),
            Date=datetime.datetime.today(),
            Type=direction,
            photo=imgpaths,
            time=datetime.datetime.now().time()
        )

    # ==========================================================
    # 4. RUN GAZE TRACKING
    # ==========================================================
    gaze = GazeTracking()
    gaze.refresh(frame)
    text = "center"

    if gaze.is_right():
        text = "Eye Looking right"
    elif gaze.is_left():
        text = "Eye Looking left"

    if text != "center":
        Proctoractivity.objects.create(
            USERS=student,
            SCHEDULE=Schedule.objects.get(id=eid),
            Date=datetime.datetime.today(),
            Type=text,
            photo=imgpaths,
            time=datetime.datetime.now().time()
        )

    return "ok"

