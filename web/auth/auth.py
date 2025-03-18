from datetime import datetime, timedelta
from typing import Optional, Union
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
import os
from dotenv import load_dotenv
import re
import logging
import secrets
import string
import sys
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from ..models.database import User, SessionLocal, Patient

# Load environment variables
load_dotenv()

# Security settings
SECRET_KEY = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Database configuration
engine = create_engine("sqlite:///app.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Token model
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_user(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def get_patient_by_id(db: Session, patient_id: str):
    return db.query(Patient).filter(Patient.patient_id == patient_id).first()

def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def generate_patient_id(db: Session):
    # Get the highest patient ID
    highest_patient = db.query(Patient).order_by(Patient.id.desc()).first()
    if highest_patient:
        # Extract and increment numeric ID
        base_id = "P"
        if highest_patient.patient_id.startswith('P'):
            number = int(highest_patient.patient_id[1:])
            new_id = f"{base_id}{number + 1:05d}"
        else:
            new_id = "P00001"
    else:
        new_id = "P00001"
    
    return new_id

def generate_patient_password(patient_id: str, dob: datetime):
    # Format: patientID_DOB_YEAR
    return f"{patient_id}_{dob.strftime('%d%m')}_{dob.strftime('%Y')}"

def create_user(db: Session, username: str, email: str, password: str, full_name: str, role: str):
    hashed_password = get_password_hash(password)
    db_user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        full_name=full_name,
        role=role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def create_patient(db: Session, name: str, age: int, sex: str, date_of_birth: datetime, 
                  mobile_number: str, doctor_id: int):
    patient_id = generate_patient_id(db)
    db_patient = Patient(
        patient_id=patient_id,
        doctor_id=doctor_id,
        name=name,
        age=age,
        sex=sex,
        date_of_birth=date_of_birth,
        mobile_number=mobile_number
    )
    db.add(db_patient)
    db.commit()
    db.refresh(db_patient)
    
    # Generate patient password
    password = generate_patient_password(patient_id, date_of_birth)
    
    # Create user account for patient if mobile number is valid
    if mobile_number and re.match(r'^\d{10}$', mobile_number):
        username = f"patient_{patient_id}"
        email = f"{patient_id}@medicaltranscription.app"
        user = create_user(db, username, email, password, name, "patient")
        
        # Link user to patient
        db_patient.user_id = user.id
        db.commit()
        db.refresh(db_patient)
    
    return db_patient, password

# Custom OAuth2 scheme that also checks cookies
class CookieOrHeaderAuth(OAuth2PasswordBearer):
    async def __call__(self, request: Request):
        # First try to get token from authorization header
        try:
            token = await super().__call__(request)
            if token:
                return token
        except HTTPException:
            # If header auth fails, check for cookie
            authorization = request.cookies.get("Authorization")
            if authorization:
                scheme, token = authorization.split()
                if scheme.lower() == "bearer":
                    return token
            
            # If we got this far, no valid auth was found
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

# Create instance of custom auth scheme
oauth2_scheme_with_cookie = CookieOrHeaderAuth(tokenUrl="token")

# Get current user from token
async def get_current_user(token: str = Depends(oauth2_scheme_with_cookie), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        print(f"Validating token: {token[:10]}...")  # Only log first 10 chars for security
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            print("Token missing 'sub' claim")
            raise credentials_exception
        print(f"Token validated for user: {username}")
    except JWTError as e:
        print(f"JWT Error: {str(e)}")
        raise credentials_exception
    except Exception as e:
        print(f"Unexpected error validating token: {str(e)}")
        raise credentials_exception
        
    user = get_user(db, username=username)
    if user is None:
        print(f"User not found in database: {username}")
        raise credentials_exception
    return user

async def get_current_doctor(current_user: User = Depends(get_current_user)):
    if current_user.role != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this resource",
        )
    return current_user

async def get_current_patient(current_user: User = Depends(get_current_user)):
    if current_user.role != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this resource",
        )
    return current_user 