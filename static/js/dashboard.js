// static/js/dashboard.js

document.addEventListener('DOMContentLoaded', async () => {
    const user = AuthService.getUserDetails();
    if (!user) window.location.href = '/login/';
    
    document.getElementById('userFullName').textContent = user.full_name;
    
    const res = await AuthService.fetchWithAuth('/admin/dashboard-stats/');
    if (res.ok) {
        const data = await res.json();
        document.getElementById('totalMembers').textContent = data.total_members;
    }

    // 2. Update the Top Bar Profile UI using the custom claims in the token
    document.getElementById('userFullName').textContent = user.full_name || user.username;
    document.getElementById('userRole').textContent = user.is_staff ? 'System Administrator' : 'SHG Member';
    
    // Create initials for avatar (e.g., "Dhananjay Shinde" -> "DS")
    const initials = (user.full_name || user.username).split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
    document.getElementById('avatarIcon').textContent = initials;

    // 3. Fetch Dashboard Stats from API
    try {
        // Note: Update this endpoint to match whatever you named it in urls.py
        const response = await AuthService.fetchWithAuth('/admin/dashboard-stats/'); 
        
        if (response.ok) {
            const data = await response.json();
            
            // 4. Paint the UI with real data
            document.getElementById('totalMembers').textContent = data.total_members;
            
            // Format numbers as Indian Rupees (e.g., 184500 -> ₹1,84,500)
            const inrFormatter = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 });
            
            document.getElementById('groupSavings').textContent = inrFormatter.format(data.total_savings);
            document.getElementById('outstandingLoans').textContent = inrFormatter.format(data.active_loans);
        }
    } catch (error) {
        console.error("Failed to load dashboard data:", error);
        // Optionally show a user-friendly error state on the UI here
    }
});