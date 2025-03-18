from fastapi import FastAPI, Request, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import os
import json
from typing import List, Optional
import shutil
import uuid
from pydantic import BaseModel
import logging
import wave

# Import from our modules
from .auth.auth import (
    authenticate_user, create_access_token, get_current_user, 
    get_current_doctor, get_current_patient, create_user, create_patient,
    get_db, get_patient_by_id, verify_password
)
from .models.database import User, Patient, Recording, Transcription, Report, Entity
from .models.init_db import initialize_database, reset_database
from medical_transcription.transcription.whisper_transcriber import WhisperTranscriber
from medical_transcription.ner.medical_ner import MedicalNER
from medical_transcription.summarization.text_summarizer import TextSummarizer
from medical_transcription.report_generation.report_generator import ReportGenerator

# Create FastAPI app
app = FastAPI(title="Medical Transcription System")

# Mount static files
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Configure templates
templates = Jinja2Templates(directory="web/templates")

# Initialize processing components
transcriber = WhisperTranscriber()
ner = MedicalNER()
summarizer = TextSummarizer()
report_generator = ReportGenerator()

# Create directories for uploads and recordings
os.makedirs("uploads", exist_ok=True)
os.makedirs("recordings", exist_ok=True)
os.makedirs("reports", exist_ok=True)

# Initialize database with dummy users
try:
    initialize_database()
except Exception as e:
    logging.error(f"Error initializing database: {str(e)}")
    logging.info("Attempting to reset the database...")
    try:
        reset_database()
        logging.info("Database reset successfully")
    except Exception as reset_error:
        logging.error(f"Failed to reset database: {str(reset_error)}")
        logging.error("You may need to manually delete the app.db file and restart")

# Pydantic models for request/response validation
class Token(BaseModel):
    access_token: str
    token_type: str
    user_role: str

class PatientCreate(BaseModel):
    name: str
    age: int
    sex: str
    date_of_birth: str
    mobile_number: str

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: str
    role: str

# Define an admin-only dependency
async def get_current_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can access this resource"
        )
    return current_user

# Routes
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    print(f"Login attempt for username: {form_data.username}")
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        print(f"Authentication failed for user: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    # Log successful login
    print(f"Login successful for user: {user.username}, role: {user.role}")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_role": user.role,
        "username": user.username
    }

@app.post("/patient-login")
async def patient_login(patient_id: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    print(f"Patient login attempt for ID: {patient_id}")
    
    # Find patient by ID
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        print(f"Patient not found with ID: {patient_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid patient ID",
        )
    
    # Get user associated with patient
    if not patient.user_id:
        print(f"No user account found for patient: {patient_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
        )
    
    user = db.query(User).filter(User.id == patient.user_id).first()
    if not user:
        print(f"User not found for patient: {patient_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
        )
    
    # Verify password
    if not verify_password(password, user.hashed_password):
        print(f"Invalid password for patient: {patient_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    print(f"Patient login successful: {patient_id}, username: {user.username}")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_role": "patient",
        "username": user.username,
        "patient_id": patient_id
    }

@app.post("/register")
async def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    # Check if username exists
    db_user = db.query(User).filter(User.username == user_data.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # Check if email exists
    db_user = db.query(User).filter(User.email == user_data.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    user = create_user(
        db=db,
        username=user_data.username,
        email=user_data.email,
        password=user_data.password,
        full_name=user_data.full_name,
        role=user_data.role
    )
    
    return {"message": "User created successfully"}

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: User = Depends(get_current_user)):
    try:
        print(f"Dashboard access - User: {current_user.username}, Role: {current_user.role}")
        
        if current_user.role == "doctor":
            return templates.TemplateResponse(
                "doctor_dashboard.html", 
                {"request": request, "user": current_user}
            )
        else:
            print(f"Patient dashboard access - Patient lookup for user_id: {current_user.id}")
            db = next(get_db())
            patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
            if not patient:
                print(f"Warning: No patient found for user_id: {current_user.id}")
                    
            return templates.TemplateResponse(
                "patient_dashboard.html", 
                {"request": request, "user": current_user, "patient": patient}
            )
    except Exception as e:
        print(f"Error accessing dashboard: {str(e)}")
        # If authentication failed, redirect to login page
        return RedirectResponse(url="/", status_code=303)

@app.post("/add-patient")
async def add_patient(
    patient_data: PatientCreate,
    current_user: User = Depends(get_current_doctor),
    db: Session = Depends(get_db)
):
    try:
        # Parse date of birth
        dob = datetime.strptime(patient_data.date_of_birth, "%Y-%m-%d")
        
        # Create patient
        patient, password = create_patient(
            db=db,
            name=patient_data.name,
            age=patient_data.age,
            sex=patient_data.sex,
            date_of_birth=dob,
            mobile_number=patient_data.mobile_number,
            doctor_id=current_user.id
        )
        
        return {
            "message": "Patient added successfully",
            "patient_id": patient.patient_id,
            "password": password
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/patients", response_class=HTMLResponse)
async def list_patients(
    request: Request,
    current_user: User = Depends(get_current_doctor),
    db: Session = Depends(get_db)
):
    patients = db.query(Patient).filter(Patient.doctor_id == current_user.id).all()
    
    # Check if the request wants JSON (for API calls) or HTML (for page loads)
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header:
        # Return JSON for API calls
        return JSONResponse(content={
            "patients": [
                {
                    "id": patient.id,
                    "patient_id": patient.patient_id,
                    "name": patient.name,
                    "age": patient.age,
                    "sex": patient.sex,
                    "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
                    "mobile_number": patient.mobile_number,
                    "created_at": patient.created_at.isoformat() if patient.created_at else None
                }
                for patient in patients
            ]
        })
    
    # Return HTML for page loads
    return templates.TemplateResponse("patients.html", {
        "request": request,
        "user": current_user,
        "patients": patients
    })

@app.get("/patient/{patient_id}", response_class=HTMLResponse)
async def patient_details(
    request: Request,
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Check authorization
    if current_user.role == "doctor" and patient.doctor_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this patient")
    elif current_user.role == "patient" and patient.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this patient")
    
    # Get recordings
    recordings = db.query(Recording).filter(Recording.patient_id == patient.id).all()
    
    return templates.TemplateResponse("patient_detail.html", {
        "request": request,
        "user": current_user,
        "patient": patient,
        "recordings": recordings
    })

@app.post("/record-audio")
async def record_audio(
    patient_id: str = Form(...),
    audio_file: UploadFile = File(...),
    current_user: User = Depends(get_current_doctor),
    db: Session = Depends(get_db)
):
    try:
        # Get patient
        patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        
        # Check authorization
        if patient.doctor_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized for this patient")
        
        # Save audio file
        file_extension = os.path.splitext(audio_file.filename)[1]
        if file_extension.lower() != '.wav':
            raise HTTPException(status_code=400, detail="Only .wav files are supported")
        
        filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join("recordings", filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(audio_file.file, buffer)
        
        # Create recording record
        recording = Recording(
            patient_id=patient.id,
            doctor_id=current_user.id,
            filename=audio_file.filename,
            file_path=file_path,
            duration=0  # Will be updated after processing
        )
        db.add(recording)
        db.commit()
        db.refresh(recording)
        
        # Process the audio file (transcription)
        try:
            transcription_text = transcriber.transcribe(file_path)
            
            # Update recording duration (estimate based on file size)
            with wave.open(file_path, 'rb') as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = frames / float(rate)
                recording.duration = int(duration)
                db.commit()
            
            # Create transcription
            transcription = Transcription(
                recording_id=recording.id,
                text=transcription_text
            )
            db.add(transcription)
            db.commit()
            db.refresh(transcription)
            
            # Generate report
            try:
                summary = summarizer.summarize(transcription_text)
                
                # Extract medical entities with NER
                entities = ner.extract_entities(transcription_text)
                
                # Format entities for report
                medications = []
                tests = []
                symptoms = []
                causes = []
                precautions = []
                
                for entity in entities:
                    if entity['type'] == 'MEDICATION':
                        medications.append(entity['text'])
                    elif entity['type'] == 'TEST':
                        tests.append(entity['text'])
                    elif entity['type'] == 'SYMPTOM':
                        symptoms.append(entity['text'])
                    elif entity['type'] == 'CAUSE':
                        causes.append(entity['text'])
                    elif entity['type'] == 'PRECAUTION':
                        precautions.append(entity['text'])
                
                # Generate full report
                report_text = report_generator.generate_report(
                    transcription_text,
                    summary,
                    patient_name=patient.name,
                    patient_age=patient.age,
                    patient_sex=patient.sex
                )
                
                # Create report record
                report = Report(
                    transcription_id=transcription.id,
                    summary=summary,
                    full_report=report_text,
                    medications=json.dumps(medications),
                    tests=json.dumps(tests),
                    symptoms=json.dumps(symptoms),
                    causes=json.dumps(causes),
                    precautions=json.dumps(precautions)
                )
                db.add(report)
                db.commit()
                
                # Create entities
                for entity in entities:
                    db_entity = Entity(
                        report_id=report.id,
                        entity_type=entity['type'],
                        text=entity['text'],
                        start_char=entity.get('start', 0),
                        end_char=entity.get('end', 0)
                    )
                    db.add(db_entity)
                
                db.commit()
                
            except Exception as e:
                logging.error(f"Error generating report: {str(e)}")
                # Continue without report
        
        except Exception as e:
            logging.error(f"Error transcribing audio: {str(e)}")
            return JSONResponse(
                status_code=200,
                content={"message": "Recording saved but transcription failed. Please try again later."}
            )
        
        return JSONResponse(
            status_code=200,
            content={"message": "Recording processed successfully", "recording_id": recording.id}
        )
        
    except Exception as e:
        logging.error(f"Error in record_audio: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/recording/{recording_id}", response_class=HTMLResponse)
async def view_recording(
    request: Request,
    recording_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get recording
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    # Get patient
    patient = db.query(Patient).filter(Patient.id == recording.patient_id).first()
    
    # Check authorization
    if current_user.role == "doctor" and recording.doctor_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this recording")
    elif current_user.role == "patient" and patient.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this recording")
    
    # Get transcription and report
    transcription = db.query(Transcription).filter(Transcription.recording_id == recording.id).first()
    report = None
    entities = []
    
    if transcription:
        report = db.query(Report).filter(Report.transcription_id == transcription.id).first()
        if report:
            entities = db.query(Entity).filter(Entity.report_id == report.id).all()
    
    return templates.TemplateResponse("recording_detail.html", {
        "request": request,
        "user": current_user,
        "recording": recording,
        "patient": patient,
        "transcription": transcription,
        "report": report,
        "entities": entities
    })

@app.get("/download-report/{report_id}")
async def download_report(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get report
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # Get transcription and recording
    transcription = db.query(Transcription).filter(Transcription.id == report.transcription_id).first()
    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")
    
    recording = db.query(Recording).filter(Recording.id == transcription.recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    # Get patient
    patient = db.query(Patient).filter(Patient.id == recording.patient_id).first()
    
    # Check authorization
    if current_user.role == "doctor" and recording.doctor_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to download this report")
    elif current_user.role == "patient" and patient.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to download this report")
    
    # Generate report file
    report_filename = f"report_{report.id}.txt"
    report_path = os.path.join("reports", report_filename)
    
    with open(report_path, "w") as f:
        f.write(f"Medical Report\n")
        f.write(f"==============\n\n")
        f.write(f"Patient: {patient.name}\n")
        f.write(f"Patient ID: {patient.patient_id}\n")
        f.write(f"Age: {patient.age}\n")
        f.write(f"Sex: {patient.sex}\n")
        f.write(f"Date: {report.created_at.strftime('%Y-%m-%d')}\n\n")
        f.write(f"Summary:\n{report.summary}\n\n")
        f.write(f"Full Report:\n{report.full_report}\n\n")
        
        # Add entity sections
        medications = json.loads(report.medications)
        if medications:
            f.write("Medications:\n")
            for med in medications:
                f.write(f"- {med['text']}\n")
            f.write("\n")
        
        tests = json.loads(report.tests)
        if tests:
            f.write("Tests:\n")
            for test in tests:
                f.write(f"- {test['text']}\n")
            f.write("\n")
        
        symptoms = json.loads(report.symptoms)
        if symptoms:
            f.write("Symptoms:\n")
            for sym in symptoms:
                f.write(f"- {sym['text']}\n")
            f.write("\n")
        
        causes = json.loads(report.causes)
        if causes:
            f.write("Causes:\n")
            for cause in causes:
                f.write(f"- {cause['text']}\n")
            f.write("\n")
        
        precautions = json.loads(report.precautions)
        if precautions:
            f.write("Precautions:\n")
            for precaution in precautions:
                f.write(f"- {precaution['text']}\n")
            f.write("\n")
        
        # Add transcription
        f.write(f"Transcription:\n{transcription.text}\n")
    
    return FileResponse(
        path=report_path, 
        filename=f"patient_{patient.patient_id}_report.txt",
        media_type="text/plain"
    )

# Admin routes
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, current_user: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    # Get statistics for admin dashboard
    doctors_count = db.query(User).filter(User.role == "doctor").count()
    patients_count = db.query(Patient).count()
    recordings_count = db.query(Recording).count()
    reports_count = db.query(Report).count()
    
    # Get all users for user management
    users = db.query(User).order_by(User.created_at.desc()).all()
    
    # Calculate storage statistics
    recordings_size = 0
    if os.path.exists("recordings"):
        for path, dirs, files in os.walk("recordings"):
            for f in files:
                fp = os.path.join(path, f)
                recordings_size += os.path.getsize(fp) / (1024 * 1024)  # Convert to MB
    
    # Mock some recent activities
    activities = [
        {
            "type": "login",
            "title": "Admin Login",
            "description": f"Admin {current_user.username} logged in",
            "timestamp": datetime.now() - timedelta(minutes=5)
        },
        {
            "type": "patient",
            "title": "New Patient Added",
            "description": "Patient Robert Johnson was added",
            "timestamp": datetime.now() - timedelta(hours=2)
        },
        {
            "type": "recording",
            "title": "New Recording",
            "description": "A new recording was uploaded for patient Jane Doe",
            "timestamp": datetime.now() - timedelta(hours=3)
        }
    ]
    
    # System health data
    system_health = {
        "database": {
            "usage": 25,  # Mock value
            "status": "Healthy"
        },
        "storage": {
            "usage": int(min(recordings_size / 100 * 100, 100)),  # Percentage of 100MB
            "used": f"{recordings_size:.2f} MB",
            "total": "100 MB"  # Mock value
        }
    }
    
    # Create context for template
    context = {
        "request": request,
        "user": current_user,
        "stats": {
            "doctors": doctors_count,
            "patients": patients_count,
            "recordings": recordings_count,
            "reports": reports_count
        },
        "users": users,
        "activities": activities,
        "system_health": system_health
    }
    
    return templates.TemplateResponse("admin_dashboard.html", context)

@app.post("/api/admin/reset-database")
async def admin_reset_database(current_user: User = Depends(get_current_admin)):
    result = reset_database()
    return result

@app.post("/api/admin/doctors")
async def admin_add_doctor(
    user_data: UserCreate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    # Check if username or email exists
    existing_user = db.query(User).filter(
        (User.username == user_data.username) | (User.email == user_data.email)
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )
    
    # Create new doctor user
    new_doctor = create_user(
        db=db,
        username=user_data.username,
        email=user_data.email,
        password=user_data.password,
        full_name=user_data.full_name,
        role="doctor"
    )
    
    return {
        "id": new_doctor.id,
        "username": new_doctor.username,
        "full_name": new_doctor.full_name,
        "email": new_doctor.email,
        "role": new_doctor.role
    }

@app.post("/api/admin/patients")
async def admin_add_patient(
    patient_data: PatientCreate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    # Convert date of birth string to datetime
    try:
        date_of_birth = datetime.strptime(patient_data.date_of_birth, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD."
        )
    
    # Create patient
    patient = create_patient(
        db=db,
        name=patient_data.name,
        age=patient_data.age,
        sex=patient_data.sex,
        date_of_birth=date_of_birth,
        mobile_number=patient_data.mobile_number,
        doctor_id=1  # Default to first doctor, this would be selected in the UI
    )
    
    return {
        "id": patient.id,
        "patient_id": patient.patient_id,
        "name": patient.name,
        "age": patient.age,
        "sex": patient.sex
    }

@app.delete("/api/admin/doctors/{doctor_id}")
async def admin_delete_doctor(
    doctor_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    doctor = db.query(User).filter(User.id == doctor_id, User.role == "doctor").first()
    
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    # Check if doctor has patients
    patients = db.query(Patient).filter(Patient.doctor_id == doctor_id).all()
    
    if patients:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete doctor with assigned patients"
        )
    
    db.delete(doctor)
    db.commit()
    
    return {"message": "Doctor deleted successfully"}

@app.delete("/api/admin/patients/{patient_id}")
async def admin_delete_patient(
    patient_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    
    # Delete associated recordings, transcriptions, and reports
    recordings = db.query(Recording).filter(Recording.patient_id == patient_id).all()
    
    for recording in recordings:
        # Delete transcription and report
        transcription = db.query(Transcription).filter(Transcription.recording_id == recording.id).first()
        
        if transcription:
            report = db.query(Report).filter(Report.transcription_id == transcription.id).first()
            
            if report:
                # Delete report entities
                db.query(Entity).filter(Entity.report_id == report.id).delete()
                db.delete(report)
            
            db.delete(transcription)
        
        # Delete recording file
        if recording.file_path and os.path.exists(recording.file_path):
            try:
                os.remove(recording.file_path)
            except Exception as e:
                pass
                
        db.delete(recording)
    
    # If patient has a user account, delete it too
    if patient.user_id:
        user = db.query(User).filter(User.id == patient.user_id).first()
        if user:
            db.delete(user)
    
    db.delete(patient)
    db.commit()
    
    return {"message": "Patient deleted successfully"}

@app.post("/api/admin/delete-storage/{storage_type}")
async def admin_delete_storage(
    storage_type: str,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if storage_type not in ["recordings", "transcriptions", "reports"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid storage type"
        )
    
    if storage_type == "recordings":
        # Delete all recording files
        recordings = db.query(Recording).all()
        
        for recording in recordings:
            if recording.file_path and os.path.exists(recording.file_path):
                try:
                    os.remove(recording.file_path)
                except Exception as e:
                    pass
            
            recording.file_path = None
        
        # Clear recordings directory
        if os.path.exists("recordings"):
            for file in os.listdir("recordings"):
                file_path = os.path.join("recordings", file)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except Exception as e:
                    pass
        
    elif storage_type == "transcriptions":
        # Delete all transcriptions
        transcriptions = db.query(Transcription).all()
        
        for transcription in transcriptions:
            db.query(Report).filter(Report.transcription_id == transcription.id).delete()
            db.delete(transcription)
        
    elif storage_type == "reports":
        # Delete all reports
        reports = db.query(Report).all()
        
        for report in reports:
            db.query(Entity).filter(Entity.report_id == report.id).delete()
            db.delete(report)
    
    db.commit()
    
    return {"message": f"{storage_type.capitalize()} deleted successfully"}

@app.post("/api/admin/change-password")
async def admin_change_password(
    current_password: str,
    new_password: str,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    from .auth.auth import verify_password, get_password_hash
    
    # Verify current password
    if not verify_password(current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )
    
    # Update password
    current_user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    return {"message": "Password changed successfully"}

@app.get("/api/patient/recordings")
async def get_patient_recordings(
    current_user: User = Depends(get_current_patient),
    db: Session = Depends(get_db)
):
    """Get all recordings for the current patient"""
    try:
        # Get patient profile
        patient = current_user.patient_profile
        if not patient:
            raise HTTPException(status_code=404, detail="Patient profile not found")
        
        # Get recordings
        recordings = db.query(Recording).filter(
            Recording.patient_id == patient.id
        ).order_by(Recording.created_at.desc()).all()
        
        # Format recordings
        result = []
        for recording in recordings:
            # Get doctor name
            doctor = db.query(User).filter(User.id == recording.doctor_id).first()
            doctor_name = doctor.full_name if doctor else "Unknown"
            
            # Get transcription and report
            transcription = db.query(Transcription).filter(
                Transcription.recording_id == recording.id
            ).first()
            
            report = None
            if transcription:
                report = db.query(Report).filter(
                    Report.transcription_id == transcription.id
                ).first()
            
            # Format result
            result.append({
                "id": recording.id,
                "filename": recording.filename,
                "duration": recording.duration,
                "date": recording.created_at.isoformat(),
                "doctor_name": doctor_name,
                "has_transcription": transcription is not None,
                "has_report": report is not None,
                "report_id": report.id if report else None
            })
        
        return {"recordings": result}
    
    except Exception as e:
        logging.error(f"Error fetching patient recordings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/patient/reports")
async def get_patient_reports(
    current_user: User = Depends(get_current_patient),
    db: Session = Depends(get_db)
):
    """Get all reports for the current patient"""
    try:
        # Get patient profile
        patient = current_user.patient_profile
        if not patient:
            raise HTTPException(status_code=404, detail="Patient profile not found")
        
        # Get all recordings for this patient
        recording_ids = [r.id for r in db.query(Recording).filter(
            Recording.patient_id == patient.id
        ).all()]
        
        # Get transcriptions for these recordings
        transcription_ids = [t.id for t in db.query(Transcription).filter(
            Transcription.recording_id.in_(recording_ids)
        ).all()]
        
        # Get reports for these transcriptions
        reports = db.query(Report).filter(
            Report.transcription_id.in_(transcription_ids)
        ).order_by(Report.created_at.desc()).all()
        
        # Format reports
        result = []
        for report in reports:
            # Get transcription and recording
            transcription = db.query(Transcription).filter(
                Transcription.id == report.transcription_id
            ).first()
            
            if transcription:
                recording = db.query(Recording).filter(
                    Recording.id == transcription.recording_id
                ).first()
                
                if recording:
                    # Get doctor name
                    doctor = db.query(User).filter(User.id == recording.doctor_id).first()
                    doctor_name = doctor.full_name if doctor else "Unknown"
                    
                    # Format result
                    result.append({
                        "id": report.id,
                        "date": report.created_at.isoformat(),
                        "doctor_name": doctor_name,
                        "summary": report.summary,
                        "recording_id": recording.id
                    })
        
        return {"reports": result}
    
    except Exception as e:
        logging.error(f"Error fetching patient reports: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/patient/report/{report_id}")
async def get_patient_report_details(
    report_id: int,
    current_user: User = Depends(get_current_patient),
    db: Session = Depends(get_db)
):
    """Get detailed report by ID for the current patient"""
    try:
        # Get patient profile
        patient = current_user.patient_profile
        if not patient:
            raise HTTPException(status_code=404, detail="Patient profile not found")
        
        # Get report
        report = db.query(Report).filter(Report.id == report_id).first()
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        
        # Verify this report belongs to the patient
        transcription = db.query(Transcription).filter(
            Transcription.id == report.transcription_id
        ).first()
        
        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")
        
        recording = db.query(Recording).filter(
            Recording.id == transcription.recording_id
        ).first()
        
        if not recording or recording.patient_id != patient.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this report")
        
        # Get doctor name
        doctor = db.query(User).filter(User.id == recording.doctor_id).first()
        doctor_name = doctor.full_name if doctor else "Unknown"
        
        # Format report
        return {
            "id": report.id,
            "date": report.created_at.isoformat(),
            "doctor_name": doctor_name,
            "summary": report.summary,
            "full_report": report.full_report,
            "medications": json.loads(report.medications) if report.medications else [],
            "tests": json.loads(report.tests) if report.tests else [],
            "symptoms": json.loads(report.symptoms) if report.symptoms else [],
            "causes": json.loads(report.causes) if report.causes else [],
            "precautions": json.loads(report.precautions) if report.precautions else [],
            "transcription": transcription.text if transcription else ""
        }
    
    except Exception as e:
        logging.error(f"Error fetching patient report details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/patient/recording/{recording_id}")
async def get_patient_recording_audio(
    recording_id: int,
    current_user: User = Depends(get_current_patient),
    db: Session = Depends(get_db)
):
    """Stream recording audio file to patient"""
    try:
        # Get patient profile
        patient = current_user.patient_profile
        if not patient:
            raise HTTPException(status_code=404, detail="Patient profile not found")
        
        # Get recording
        recording = db.query(Recording).filter(
            Recording.id == recording_id,
            Recording.patient_id == patient.id
        ).first()
        
        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found or not authorized")
        
        # Check if file exists
        if not os.path.exists(recording.file_path):
            raise HTTPException(status_code=404, detail="Recording file not found")
        
        # Return file
        return FileResponse(
            recording.file_path,
            media_type="audio/wav",
            filename=recording.filename
        )
    
    except Exception as e:
        logging.error(f"Error streaming patient recording: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/recordings")
async def get_doctor_recordings(
    current_user: User = Depends(get_current_doctor),
    db: Session = Depends(get_db)
):
    """Get all recordings for the current doctor"""
    try:
        # Get recordings
        recordings = db.query(Recording).filter(
            Recording.doctor_id == current_user.id
        ).order_by(Recording.created_at.desc()).all()
        
        # Format recordings
        result = []
        for recording in recordings:
            # Get patient info
            patient = db.query(Patient).filter(Patient.id == recording.patient_id).first()
            patient_name = patient.name if patient else "Unknown"
            
            # Get transcription and report
            transcription = db.query(Transcription).filter(
                Transcription.recording_id == recording.id
            ).first()
            
            report = None
            if transcription:
                report = db.query(Report).filter(
                    Report.transcription_id == transcription.id
                ).first()
            
            # Format result
            result.append({
                "id": recording.id,
                "patient_name": patient_name,
                "patient_id": patient.patient_id if patient else None,
                "filename": recording.filename,
                "duration": recording.duration,
                "date": recording.created_at.isoformat(),
                "has_transcription": transcription is not None,
                "has_report": report is not None,
                "report_id": report.id if report else None
            })
        
        return {"recordings": result}
    
    except Exception as e:
        logging.error(f"Error fetching doctor recordings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 