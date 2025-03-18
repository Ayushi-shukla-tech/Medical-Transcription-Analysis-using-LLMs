from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Boolean, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
import os

from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    role = Column(String)  # 'doctor' or 'patient'
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    patients = relationship("Patient", back_populates="doctor", foreign_keys="Patient.doctor_id")
    patient_profile = relationship("Patient", back_populates="user", foreign_keys="Patient.user_id", uselist=False)
    
class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, unique=True, index=True)  # Auto-generated ID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # If patient has login
    doctor_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)
    age = Column(Integer)
    sex = Column(String)
    date_of_birth = Column(DateTime)
    mobile_number = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    doctor = relationship("User", back_populates="patients", foreign_keys=[doctor_id])
    user = relationship("User", back_populates="patient_profile", foreign_keys=[user_id])
    recordings = relationship("Recording", back_populates="patient")
    
class Recording(Base):
    __tablename__ = "recordings"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    doctor_id = Column(Integer, ForeignKey("users.id"))
    filename = Column(String)
    file_path = Column(String)
    duration = Column(Integer)  # Duration in seconds
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    patient = relationship("Patient", back_populates="recordings")
    doctor = relationship("User")
    transcription = relationship("Transcription", back_populates="recording", uselist=False)
    
class Transcription(Base):
    __tablename__ = "transcriptions"

    id = Column(Integer, primary_key=True, index=True)
    recording_id = Column(Integer, ForeignKey("recordings.id"))
    text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    recording = relationship("Recording", back_populates="transcription")
    report = relationship("Report", back_populates="transcription", uselist=False)
    
class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    transcription_id = Column(Integer, ForeignKey("transcriptions.id"))
    summary = Column(Text)
    full_report = Column(Text)
    medications = Column(Text)  # JSON string of medications
    tests = Column(Text)  # JSON string of recommended tests
    precautions = Column(Text)  # JSON string of precautions
    symptoms = Column(Text)  # JSON string of symptoms
    causes = Column(Text)  # JSON string of causes
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    transcription = relationship("Transcription", back_populates="report")
    entities = relationship("Entity", back_populates="report")
    
class Entity(Base):
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("reports.id"))
    entity_type = Column(String)  # medication, test, symptom, etc.
    text = Column(String)
    start_char = Column(Integer)
    end_char = Column(Integer)
    
    # Relationships
    report = relationship("Report", back_populates="entities")

def init_db():
    Base.metadata.create_all(bind=engine)

# Create tables when module is imported
init_db() 