/**
 * Medical Transcription Application - Main JavaScript
 * Handles UI interactions, audio recording, and API calls
 */

document.addEventListener('DOMContentLoaded', () => {
    // Initialize UI components
    initializeUI();
    
    // Set up event listeners
    setupEventListeners();
    
    // Check authentication status
    checkAuthStatus();
});

/**
 * Initialize UI components
 */
function initializeUI() {
    // Toggle mobile menu
    const menuToggle = document.querySelector('.menu-toggle');
    const sidebar = document.querySelector('.sidebar');
    
    if (menuToggle && sidebar) {
        menuToggle.addEventListener('click', () => {
            sidebar.classList.toggle('active');
        });
    }
    
    // Initialize tabs if present
    initializeTabs();
    
    // Initialize tooltips
    const tooltips = document.querySelectorAll('[data-tooltip]');
    tooltips.forEach(tooltip => {
        tooltip.addEventListener('mouseenter', showTooltip);
        tooltip.addEventListener('mouseleave', hideTooltip);
    });
}

/**
 * Initialize tab navigation
 */
function initializeTabs() {
    const tabLinks = document.querySelectorAll('.tab-link');
    const tabContents = document.querySelectorAll('.tab-content');
    
    if (tabLinks.length > 0) {
        tabLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                
                // Remove active class from all tabs
                tabLinks.forEach(tab => tab.classList.remove('active'));
                tabContents.forEach(content => content.classList.remove('active'));
                
                // Add active class to current tab
                link.classList.add('active');
                
                // Show corresponding content
                const target = document.querySelector(link.getAttribute('data-target'));
                if (target) {
                    target.classList.add('active');
                }
            });
        });
        
        // Activate first tab by default
        if (tabLinks[0]) {
            tabLinks[0].click();
        }
    }
}

/**
 * Set up global event listeners
 */
function setupEventListeners() {
    // Form submission handling
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', handleFormSubmit);
    });
    
    // Modal handling
    const modalTriggers = document.querySelectorAll('[data-modal]');
    modalTriggers.forEach(trigger => {
        trigger.addEventListener('click', (e) => {
            e.preventDefault();
            const modalId = trigger.getAttribute('data-modal');
            openModal(modalId);
        });
    });
    
    // Modal close buttons
    const closeButtons = document.querySelectorAll('.modal-close, .modal-overlay');
    closeButtons.forEach(button => {
        button.addEventListener('click', (e) => {
            e.preventDefault();
            closeModal(e.target.closest('.modal-container').id);
        });
    });
    
    // Audio recording buttons
    setupAudioRecording();
}

/**
 * Handle form submissions
 */
function handleFormSubmit(e) {
    e.preventDefault();
    const form = e.target;
    const formId = form.id;
    
    // Show loading state
    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) {
        const originalText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner"></span> Processing...';
        
        // Reset button after timeout (in case of network issues)
        setTimeout(() => {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }, 10000);
    }
    
    // Collect form data
    const formData = new FormData(form);
    const data = Object.fromEntries(formData.entries());
    
    // Handle different form types
    switch (formId) {
        case 'login-form':
            handleLogin(data);
            break;
        case 'register-form':
            handleRegistration(data);
            break;
        case 'patient-form':
            handlePatientSubmission(data);
            break;
        case 'report-form':
            handleReportSubmission(data);
            break;
        default:
            // Generic form handling
            submitFormData(form.action, data)
                .then(response => {
                    showNotification('Success', 'Form submitted successfully', 'success');
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.textContent = originalText;
                    }
                })
                .catch(error => {
                    showNotification('Error', error.message || 'An error occurred', 'error');
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.textContent = originalText;
                    }
                });
    }
}

/**
 * Handle login form submission
 */
async function handleLogin(data) {
    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.detail || 'Login failed');
        }
        
        // Store token in localStorage
        localStorage.setItem('auth_token', result.access_token);
        localStorage.setItem('user_role', result.role);
        
        // Redirect based on role
        if (result.role === 'doctor') {
            window.location.href = '/doctor/dashboard';
        } else if (result.role === 'patient') {
            window.location.href = '/patient/dashboard';
        } else {
            window.location.href = '/dashboard';
        }
        
    } catch (error) {
        showNotification('Login Failed', error.message, 'error');
        const submitBtn = document.querySelector('#login-form button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Log In';
        }
    }
}

/**
 * Check authentication status
 */
function checkAuthStatus() {
    const token = localStorage.getItem('auth_token');
    const userRole = localStorage.getItem('user_role');
    
    // Update UI based on authentication status
    const authLinks = document.querySelectorAll('.auth-link');
    const userLinks = document.querySelectorAll('.user-link');
    
    if (token) {
        // User is logged in
        authLinks.forEach(link => link.style.display = 'none');
        userLinks.forEach(link => link.style.display = 'block');
        
        // Set user role specific elements
        const roleElements = document.querySelectorAll(`[data-role="${userRole}"]`);
        roleElements.forEach(el => el.style.display = 'block');
        
        // Fetch user data if on dashboard
        if (window.location.pathname.includes('dashboard')) {
            fetchUserData();
        }
    } else {
        // User is not logged in
        authLinks.forEach(link => link.style.display = 'block');
        userLinks.forEach(link => link.style.display = 'none');
        
        // Redirect to login if trying to access protected pages
        const protectedPaths = ['/dashboard', '/doctor/', '/patient/', '/reports/'];
        if (protectedPaths.some(path => window.location.pathname.includes(path))) {
            window.location.href = '/login';
        }
    }
}

/**
 * Set up audio recording functionality
 */
function setupAudioRecording() {
    const recordButton = document.getElementById('record-button');
    const stopButton = document.getElementById('stop-button');
    const audioPlayer = document.getElementById('audio-player');
    const saveRecordingButton = document.getElementById('save-recording');
    
    if (!recordButton || !stopButton) return;
    
    let mediaRecorder;
    let audioChunks = [];
    
    recordButton.addEventListener('click', async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            
            mediaRecorder.ondataavailable = (event) => {
                audioChunks.push(event.data);
            };
            
            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                const audioUrl = URL.createObjectURL(audioBlob);
                
                if (audioPlayer) {
                    audioPlayer.src = audioUrl;
                    audioPlayer.style.display = 'block';
                }
                
                if (saveRecordingButton) {
                    saveRecordingButton.style.display = 'block';
                    saveRecordingButton.onclick = () => saveRecording(audioBlob);
                }
            };
            
            // Start recording
            mediaRecorder.start();
            recordButton.style.display = 'none';
            stopButton.style.display = 'block';
            
            // Update UI to show recording state
            const recordingIndicator = document.getElementById('recording-indicator');
            if (recordingIndicator) {
                recordingIndicator.style.display = 'block';
            }
            
        } catch (error) {
            showNotification('Recording Error', 'Could not access microphone. Please check permissions.', 'error');
        }
    });
    
    stopButton.addEventListener('click', () => {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
            recordButton.style.display = 'block';
            stopButton.style.display = 'none';
            
            // Update UI to hide recording state
            const recordingIndicator = document.getElementById('recording-indicator');
            if (recordingIndicator) {
                recordingIndicator.style.display = 'none';
            }
        }
    });
}

/**
 * Save recording to server
 */
async function saveRecording(audioBlob) {
    try {
        const formData = new FormData();
        formData.append('audio_file', audioBlob, 'recording.wav');
        
        // Get patient ID if available
        const patientSelect = document.getElementById('patient-select');
        if (patientSelect) {
            formData.append('patient_id', patientSelect.value);
        }
        
        // Add notes if available
        const notesField = document.getElementById('recording-notes');
        if (notesField) {
            formData.append('notes', notesField.value);
        }
        
        const response = await fetch('/api/recordings/upload', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
            },
            body: formData
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.detail || 'Failed to save recording');
        }
        
        showNotification('Success', 'Recording saved successfully', 'success');
        
        // Reset UI
        const audioPlayer = document.getElementById('audio-player');
        const saveRecordingButton = document.getElementById('save-recording');
        
        if (audioPlayer) {
            audioPlayer.style.display = 'none';
            audioPlayer.src = '';
        }
        
        if (saveRecordingButton) {
            saveRecordingButton.style.display = 'none';
        }
        
        if (notesField) {
            notesField.value = '';
        }
        
    } catch (error) {
        showNotification('Error', error.message, 'error');
    }
}

/**
 * Show notification
 */
function showNotification(title, message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerHTML = `
        <div class="notification-header">
            <h4>${title}</h4>
            <button class="notification-close">&times;</button>
        </div>
        <div class="notification-body">
            <p>${message}</p>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    // Add close button functionality
    const closeButton = notification.querySelector('.notification-close');
    closeButton.addEventListener('click', () => {
        notification.classList.add('fade-out');
        setTimeout(() => {
            notification.remove();
        }, 300);
    });
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.classList.add('fade-out');
        setTimeout(() => {
            notification.remove();
        }, 300);
    }, 5000);
}

/**
 * Modal handling functions
 */
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'flex';
        document.body.classList.add('modal-open');
        
        // Focus first input if exists
        const firstInput = modal.querySelector('input, textarea, select');
        if (firstInput) {
            firstInput.focus();
        }
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
        document.body.classList.remove('modal-open');
    }
}

/**
 * Tooltip functions
 */
function showTooltip(e) {
    const tooltip = e.target;
    const text = tooltip.getAttribute('data-tooltip');
    
    const tooltipElement = document.createElement('div');
    tooltipElement.className = 'tooltip';
    tooltipElement.textContent = text;
    
    document.body.appendChild(tooltipElement);
    
    const rect = tooltip.getBoundingClientRect();
    tooltipElement.style.top = `${rect.top - tooltipElement.offsetHeight - 10}px`;
    tooltipElement.style.left = `${rect.left + (rect.width / 2) - (tooltipElement.offsetWidth / 2)}px`;
    
    tooltip._tooltipElement = tooltipElement;
}

function hideTooltip(e) {
    const tooltip = e.target;
    if (tooltip._tooltipElement) {
        tooltip._tooltipElement.remove();
        delete tooltip._tooltipElement;
    }
}

/**
 * Fetch user data for dashboard
 */
async function fetchUserData() {
    try {
        const response = await fetch('/api/users/me', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to fetch user data');
        }
        
        const userData = await response.json();
        
        // Update UI with user data
        const userNameElements = document.querySelectorAll('.user-name');
        userNameElements.forEach(el => {
            el.textContent = `${userData.first_name} ${userData.last_name}`;
        });
        
        const userRoleElements = document.querySelectorAll('.user-role');
        userRoleElements.forEach(el => {
            el.textContent = userData.role.charAt(0).toUpperCase() + userData.role.slice(1);
        });
        
        // Load dashboard data based on role
        if (userData.role === 'doctor') {
            loadDoctorDashboard();
        } else if (userData.role === 'patient') {
            loadPatientDashboard();
        }
        
    } catch (error) {
        console.error('Error fetching user data:', error);
        // If authentication error, redirect to login
        if (error.message.includes('401')) {
            localStorage.removeItem('auth_token');
            localStorage.removeItem('user_role');
            window.location.href = '/login';
        }
    }
}

/**
 * Load doctor dashboard data
 */
async function loadDoctorDashboard() {
    try {
        // Fetch patients
        const patientsResponse = await fetch('/api/doctors/patients', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
            }
        });
        
        if (!patientsResponse.ok) {
            throw new Error('Failed to fetch patients');
        }
        
        const patients = await patientsResponse.json();
        
        // Update patient list
        const patientList = document.getElementById('patient-list');
        if (patientList) {
            patientList.innerHTML = '';
            
            if (patients.length === 0) {
                patientList.innerHTML = '<tr><td colspan="4" class="text-center">No patients found</td></tr>';
            } else {
                patients.forEach(patient => {
                    patientList.innerHTML += `
                        <tr>
                            <td>${patient.first_name} ${patient.last_name}</td>
                            <td>${patient.email}</td>
                            <td>${new Date(patient.created_at).toLocaleDateString()}</td>
                            <td>
                                <button class="btn btn-sm btn-primary" data-patient-id="${patient.id}" onclick="viewPatientDetails(${patient.id})">
                                    View
                                </button>
                            </td>
                        </tr>
                    `;
                });
            }
        }
        
        // Fetch recent recordings
        const recordingsResponse = await fetch('/api/doctors/recordings/recent', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
            }
        });
        
        if (!recordingsResponse.ok) {
            throw new Error('Failed to fetch recordings');
        }
        
        const recordings = await recordingsResponse.json();
        
        // Update recordings list
        const recordingsList = document.getElementById('recordings-list');
        if (recordingsList) {
            recordingsList.innerHTML = '';
            
            if (recordings.length === 0) {
                recordingsList.innerHTML = '<div class="empty-state">No recordings found</div>';
            } else {
                recordings.forEach(recording => {
                    recordingsList.innerHTML += `
                        <div class="recording-item">
                            <div class="recording-info">
                                <h4>Patient: ${recording.patient_name}</h4>
                                <p>Recorded: ${new Date(recording.created_at).toLocaleString()}</p>
                                <p class="recording-status ${recording.status}">Status: ${recording.status}</p>
                            </div>
                            <div class="recording-actions">
                                <button class="btn btn-sm btn-primary" onclick="playRecording('${recording.audio_url}')">
                                    <i class="icon-play"></i> Play
                                </button>
                                <button class="btn btn-sm btn-secondary" onclick="viewRecordingDetails(${recording.id})">
                                    Details
                                </button>
                            </div>
                        </div>
                    `;
                });
            }
        }
        
    } catch (error) {
        console.error('Error loading doctor dashboard:', error);
        showNotification('Error', 'Failed to load dashboard data', 'error');
    }
}

/**
 * Load patient dashboard data
 */
async function loadPatientDashboard() {
    try {
        // Fetch reports
        const reportsResponse = await fetch('/api/patients/reports', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
            }
        });
        
        if (!reportsResponse.ok) {
            throw new Error('Failed to fetch reports');
        }
        
        const reports = await reportsResponse.json();
        
        // Update reports list
        const reportsList = document.getElementById('reports-list');
        if (reportsList) {
            reportsList.innerHTML = '';
            
            if (reports.length === 0) {
                reportsList.innerHTML = '<div class="empty-state">No reports found</div>';
            } else {
                reports.forEach(report => {
                    reportsList.innerHTML += `
                        <div class="report-card">
                            <div class="report-header">
                                <h4>${report.title}</h4>
                                <span class="report-date">${new Date(report.created_at).toLocaleDateString()}</span>
                            </div>
                            <div class="report-body">
                                <p>${report.summary}</p>
                            </div>
                            <div class="report-footer">
                                <button class="btn btn-primary" onclick="viewReport(${report.id})">
                                    View Full Report
                                </button>
                            </div>
                        </div>
                    `;
                });
            }
        }
        
        // Fetch upcoming appointments
        const appointmentsResponse = await fetch('/api/patients/appointments', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
            }
        });
        
        if (!appointmentsResponse.ok) {
            throw new Error('Failed to fetch appointments');
        }
        
        const appointments = await appointmentsResponse.json();
        
        // Update appointments list
        const appointmentsList = document.getElementById('appointments-list');
        if (appointmentsList) {
            appointmentsList.innerHTML = '';
            
            if (appointments.length === 0) {
                appointmentsList.innerHTML = '<div class="empty-state">No upcoming appointments</div>';
            } else {
                appointments.forEach(appointment => {
                    appointmentsList.innerHTML += `
                        <div class="appointment-item">
                            <div class="appointment-date">
                                <span class="day">${new Date(appointment.date_time).getDate()}</span>
                                <span class="month">${new Date(appointment.date_time).toLocaleString('default', { month: 'short' })}</span>
                            </div>
                            <div class="appointment-details">
                                <h4>Dr. ${appointment.doctor_name}</h4>
                                <p>${new Date(appointment.date_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
                                <p>${appointment.location || 'Virtual'}</p>
                            </div>
                            <div class="appointment-actions">
                                <button class="btn btn-sm btn-outline" onclick="rescheduleAppointment(${appointment.id})">
                                    Reschedule
                                </button>
                            </div>
                        </div>
                    `;
                });
            }
        }
        
    } catch (error) {
        console.error('Error loading patient dashboard:', error);
        showNotification('Error', 'Failed to load dashboard data', 'error');
    }
}

/**
 * Utility function for API calls
 */
async function submitFormData(url, data) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
        },
        body: JSON.stringify(data)
    });
    
    const result = await response.json();
    
    if (!response.ok) {
        throw new Error(result.detail || 'An error occurred');
    }
    
    return result;
}

/**
 * Logout function
 */
function logout() {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user_role');
    window.location.href = '/login';
}

// Export functions for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        initializeUI,
        showNotification,
        openModal,
        closeModal
    };
} 