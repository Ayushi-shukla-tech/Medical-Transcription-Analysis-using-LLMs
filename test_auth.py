from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
import os
import uvicorn

app = FastAPI()

# Setup templates directory for testing
os.makedirs("templates", exist_ok=True)

# Create a simple index.html for testing
with open("templates/index.html", "w") as f:
    f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>Test Auth</title>
</head>
<body>
    <h1>Test Login</h1>
    <form id="loginForm">
        <input type="text" id="username" placeholder="Username" value="testuser">
        <input type="password" id="password" placeholder="Password" value="password">
        <button type="submit">Login</button>
    </form>
    <div id="message"></div>

    <script>
        document.getElementById('loginForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            
            // Create form data
            const formData = new FormData();
            formData.append('username', username);
            formData.append('password', password);
            
            // Send login request
            fetch('/token', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                console.log("Login successful:", data);
                
                // Store token in localStorage
                localStorage.setItem('access_token', data.access_token);
                localStorage.setItem('token_type', data.token_type);
                
                // Set auth cookie for server-side requests
                document.cookie = `Authorization=${data.token_type} ${data.access_token}; path=/; SameSite=Strict`;
                console.log('Auth cookie set for dashboard access');
                
                document.getElementById('message').textContent = "Login successful! Redirecting...";
                
                // Redirect to dashboard
                setTimeout(() => {
                    window.location.href = '/dashboard';
                }, 1000);
            })
            .catch(error => {
                console.error('Error:', error);
                document.getElementById('message').textContent = "Login failed!";
            });
        });
    </script>
</body>
</html>
    """)

# Create a simple dashboard.html for testing
with open("templates/dashboard.html", "w") as f:
    f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>Dashboard</title>
</head>
<body>
    <h1>Welcome to Dashboard</h1>
    <p>You are logged in as: <span id="username"></span></p>
    <button id="logout">Logout</button>

    <script>
        // Check for token in localStorage
        const token = localStorage.getItem('access_token');
        if (!token) {
            window.location.href = '/';
        }
        
        // Fetch user info
        fetch('/users/me', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        })
        .then(response => response.json())
        .then(data => {
            document.getElementById('username').textContent = data.username;
        })
        .catch(error => {
            console.error('Error:', error);
            window.location.href = '/';
        });
        
        // Logout
        document.getElementById('logout').addEventListener('click', function() {
            localStorage.removeItem('access_token');
            localStorage.removeItem('token_type');
            document.cookie = 'Authorization=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
            window.location.href = '/';
        });
    </script>
</body>
</html>
    """)

# Mount templates
templates = Jinja2Templates(directory="templates")

# JWT settings
SECRET_KEY = "testsecretkey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

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

# User model
class User(BaseModel):
    username: str
    email: str = None
    disabled: bool = False

# Token model
class Token(BaseModel):
    access_token: str
    token_type: str

# Demo user database
users_db = {
    "testuser": {
        "username": "testuser",
        "email": "test@example.com",
        "hashed_password": pwd_context.hash("password"),
        "disabled": False,
    }
}

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_user(username: str):
    if username in users_db:
        user_dict = users_db[username]
        return User(**user_dict)
    return None

def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user:
        return False
    if not verify_password(password, users_db[username]["hashed_password"]):
        return False
    return user

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme_with_cookie)):
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
        
    user = get_user(username)
    if user is None:
        print(f"User not found in database: {username}")
        raise credentials_exception
    return user

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    print(f"Login attempt for username: {form_data.username}")
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        print(f"Authentication failed for user: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    # Log successful login
    print(f"Login successful for user: {user.username}")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username
    }

@app.get("/users/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: User = Depends(get_current_user)):
    try:
        print(f"Dashboard access - User: {current_user.username}")
        return templates.TemplateResponse("dashboard.html", {"request": request, "user": current_user})
    except Exception as e:
        print(f"Error accessing dashboard: {str(e)}")
        # If authentication failed, redirect to login page
        return RedirectResponse(url="/", status_code=303)

if __name__ == "__main__":
    print("Starting test auth server...")
    uvicorn.run(app, host="127.0.0.1", port=8000) 