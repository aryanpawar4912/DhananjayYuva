// static/js/api.js

const BASE_URL = '/api/v1';

const AuthService = {
    async fetchWithAuth(endpoint, options = {}) {
        const token = localStorage.getItem('access_token');
        const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json', ...options.headers };
        let response = await fetch(`/api/v1${endpoint}`, { ...options, headers });
        if (response.status === 401) {
            // Logic to refresh token
            window.location.href = '/login/';
        }
        return response;
    },
    getUserDetails() {
        const token = localStorage.getItem('access_token');
        if (!token) return null;
        return JSON.parse(atob(token.split('.')[1]));
    },

    // 2. Decode the JWT to read our custom claims (Admin vs Member, Name, etc.)
    getUserDetails() {
        const token = localStorage.getItem('access_token');
        if (!token) return null;
        
        try {
            // JWTs are base64 encoded strings separated by dots. The payload is the second part.
            const payloadBase64 = token.split('.')[1];
            const decodedPayload = JSON.parse(atob(payloadBase64));
            return decodedPayload; // Returns { user_id, username, full_name, is_staff, etc. }
        } catch (e) {
            return null;
        }
    },

    // 3. Secure Logout
    logout() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login/'; // Redirect to login page
    },

    // 4. Secure Fetch Wrapper - Use this instead of standard fetch() for protected routes
    async fetchWithAuth(endpoint, options = {}) {
        let accessToken = localStorage.getItem('access_token');
        
        // Set default headers and inject the Bearer token
        const headers = {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${accessToken}`,
            ...options.headers
        };

        let response = await fetch(`${BASE_URL}${endpoint}`, { ...options, headers });

        // If token expired (401), try to refresh it automatically once
        if (response.status === 401) {
            const refreshToken = localStorage.getItem('refresh_token');
            if (refreshToken) {
                const refreshRes = await fetch(`${BASE_URL}/auth/token/refresh/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ refresh: refreshToken })
                });

                if (refreshRes.ok) {
                    const refreshData = await refreshRes.json();
                    localStorage.setItem('access_token', refreshData.access);
                    
                    // Retry the original request with the new token
                    headers['Authorization'] = `Bearer ${refreshData.access}`;
                    response = await fetch(`${BASE_URL}${endpoint}`, { ...options, headers });
                } else {
                    // Refresh failed, kick user to login
                    this.logout();
                }
            } else {
                this.logout();
            }
        }
        return response;
    }
};