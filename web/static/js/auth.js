/**
 * Authentication utilities for the Medical Transcription System
 */

// Check if user is logged in
function isLoggedIn() {
    return localStorage.getItem('access_token') !== null;
}

// Get the current user's role
function getUserRole() {
    return localStorage.getItem('user_role');
}

// Get the current user's username
function getUsername() {
    return localStorage.getItem('username');
}

// Get the authorization header for API requests
function getAuthHeader() {
    const token = localStorage.getItem('access_token');
    const tokenType = localStorage.getItem('token_type');
    
    if (!token || !tokenType) {
        console.error('No authentication token found');
        return {};
    }
    
    return {
        'Authorization': `${tokenType} ${token}`
    };
}

// Include authorization header in fetch requests
async function authenticatedFetch(url, options = {}) {
    // Make sure we have headers object
    if (!options.headers) {
        options.headers = {};
    }
    
    // Add auth header if not already present
    if (!options.headers['Authorization']) {
        const authHeader = getAuthHeader();
        options.headers = {
            ...options.headers,
            ...authHeader
        };
    }
    
    try {
        const response = await fetch(url, options);
        
        // Handle 401 Unauthorized errors by redirecting to login
        if (response.status === 401) {
            console.error('Authentication failed, redirecting to login');
            logout();
            window.location.href = '/';
            return null;
        }
        
        return response;
    } catch (error) {
        console.error('Error in authenticated fetch:', error);
        throw error;
    }
}

// Logout the user
function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('token_type');
    localStorage.removeItem('user_role');
    localStorage.removeItem('username');
    
    // Redirect to login page
    window.location.href = '/';
}

// Set token in cookie for server-side access
function setAuthCookie() {
    const token = localStorage.getItem('access_token');
    const tokenType = localStorage.getItem('token_type');
    
    if (token && tokenType) {
        // Set cookie with the token that will be sent with requests
        document.cookie = `Authorization=${tokenType} ${token}; path=/; SameSite=Strict`;
        console.log('Auth cookie set for server requests');
    }
}

// Initialize auth event listeners
document.addEventListener('DOMContentLoaded', function() {
    // Add logout functionality to logout buttons
    const logoutButtons = document.querySelectorAll('.logout-btn');
    logoutButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            logout();
        });
    });

    // Check authentication for protected pages
    const currentPath = window.location.pathname;
    if ((currentPath.includes('/dashboard') || currentPath.includes('/admin'))) {
        if (!isLoggedIn()) {
            console.warn('Unauthorized access attempt to protected page');
            window.location.href = '/';
        } else {
            // Set the auth cookie for server-side auth
            setAuthCookie();
            
            // If we're on a protected page, let's wrap all links and forms to ensure auth
            wrapNavigationWithAuth();
        }
    }
});

// Wrap navigation elements to include auth
function wrapNavigationWithAuth() {
    // For links to protected pages
    document.querySelectorAll('a').forEach(link => {
        const href = link.getAttribute('href');
        if (href && (href.includes('/dashboard') || href.includes('/admin'))) {
            link.addEventListener('click', function(e) {
                e.preventDefault();
                // Before navigation, ensure the auth cookie is set
                setAuthCookie();
                window.location.href = href;
            });
        }
    });
} 