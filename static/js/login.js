// static/js/login.js

document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const btn = document.getElementById('loginBtn');
    const errorMsg = document.getElementById('errorMsg');
    
    // UI Feedback: Loading state
    btn.textContent = "Logging in...";
    btn.disabled = true;
    errorMsg.style.display = 'none';

    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    // Use our global AuthService from api.js
    const success = await AuthService.login(username, password);

    if (success) {
        // Redirect to dashboard on success
        window.location.href = '/'; 
    } else {
        errorMsg.style.display = 'block';
        btn.textContent = "Login";
        btn.disabled = false;
    }
});