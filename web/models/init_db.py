from sqlalchemy.orm import Session
from datetime import datetime
import os
import json
import shutil

from web.models.database import User, Patient, Recording, Transcription, Report, Entity, init_db, engine, SessionLocal
from web.auth.auth import get_password_hash, generate_patient_id, generate_patient_password

def create_dummy_users(db: Session):
    """Create dummy admin, doctor, and patient users if they don't exist"""
    
    # Create admin user
    admin_user = db.query(User).filter(User.username == "admin").first()
    if not admin_user:
        admin_user = User(
            username="admin",
            email="admin@medtranscribe.com",
            hashed_password=get_password_hash("admin123"),
            full_name="System Administrator",
            role="admin",
            created_at=datetime.utcnow()
        )
        db.add(admin_user)
        print("Created admin user: admin / admin123")
    
    # Create dummy doctor
    doctor_user = db.query(User).filter(User.username == "doctor").first()
    if not doctor_user:
        doctor_user = User(
            username="doctor",
            email="doctor@medtranscribe.com",
            hashed_password=get_password_hash("doctor123"),
            full_name="Dr. John Smith",
            role="doctor",
            created_at=datetime.utcnow()
        )
        db.add(doctor_user)
        print("Created doctor user: doctor / doctor123")
    
    # Create another dummy doctor
    doctor2_user = db.query(User).filter(User.username == "drpatel").first()
    if not doctor2_user:
        doctor2_user = User(
            username="drpatel",
            email="patel@medtranscribe.com",
            hashed_password=get_password_hash("doctor123"),
            full_name="Dr. Anita Patel",
            role="doctor",
            created_at=datetime.utcnow()
        )
        db.add(doctor2_user)
        print("Created doctor user: drpatel / doctor123")
    
    # Commit new users
    db.commit()
    
    # Make sure we have the doctor user for patient creation
    if not doctor_user:
        doctor_user = db.query(User).filter(User.username == "doctor").first()
    
    # Create dummy patient with a login
    patient_user = db.query(User).filter(User.username == "patient").first()
    if not patient_user:
        patient_user = User(
            username="patient",
            email="patient@example.com",
            hashed_password=get_password_hash("patient123"),
            full_name="Jane Doe",
            role="patient",
            created_at=datetime.utcnow()
        )
        db.add(patient_user)
        db.commit()
        db.refresh(patient_user)
        
        # Now create the patient profile for this user
        dob = datetime.strptime("1985-06-15", "%Y-%m-%d")
        patient_id = generate_patient_id(db)
        
        patient = db.query(Patient).filter(Patient.user_id == patient_user.id).first()
        if not patient:
            patient = Patient(
                patient_id=patient_id,
                user_id=patient_user.id,
                doctor_id=doctor_user.id,
                name="Jane Doe",
                age=38,
                sex="Female",
                date_of_birth=dob,
                mobile_number="555-123-4567",
                created_at=datetime.utcnow()
            )
            db.add(patient)
            db.commit()  # Commit here to ensure patient_id is in the database
            print(f"Created patient user: patient / patient123 (Patient ID: {patient_id})")
            
    # Create another dummy patient without login (only managed by doctor)
    patient_check = db.query(Patient).filter(Patient.name == "Robert Johnson").first()
    if not patient_check and doctor_user:
        dob = datetime.strptime("1970-09-22", "%Y-%m-%d")
        
        # Generate a unique patient ID by committing the previous patient first
        # and then generating a new ID
        patient_id = generate_patient_id(db)
        patient_password = generate_patient_password(patient_id, dob)
        
        patient = Patient(
            patient_id=patient_id,
            doctor_id=doctor_user.id,
            name="Robert Johnson",
            age=53,
            sex="Male",
            date_of_birth=dob,
            mobile_number="555-987-6543",
            created_at=datetime.utcnow()
        )
        db.add(patient)
        print(f"Created patient: Robert Johnson (Patient ID: {patient_id}, Password: {patient_password})")
    
    # Final commit for all changes
    db.commit()

def initialize_database():
    """Initialize the database with tables and dummy data"""
    # Create database tables
    init_db()
    
    # Create directory structure if they don't exist
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("recordings", exist_ok=True)
    os.makedirs("reports", exist_ok=True)
    
    # Create a session
    db = SessionLocal()
    try:
        # Create dummy users
        create_dummy_users(db)
    finally:
        db.close()

def reset_database():
    """Reset the database by dropping all tables and recreating them"""
    from web.models.database import Base
    
    # Drop all tables
    Base.metadata.drop_all(bind=engine)
    
    # Recreate tables
    Base.metadata.create_all(bind=engine)
    
    # Remove uploaded files
    if os.path.exists("uploads"):
        shutil.rmtree("uploads")
    if os.path.exists("recordings"):
        shutil.rmtree("recordings")
    if os.path.exists("reports"):
        shutil.rmtree("reports")
        
    # Recreate directories
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("recordings", exist_ok=True)
    os.makedirs("reports", exist_ok=True)
    
    # Initialize with dummy data
    db = SessionLocal()
    try:
        create_dummy_users(db)
    finally:
        db.close()
    
    return {"message": "Database reset successfully"}

if __name__ == "__main__":
    initialize_database() 