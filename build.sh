#!/usr/bin/env bash
# Exit immediately if a command fails
set -o errexit

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Collect static files & run database migrations
python manage.py collectstatic --no-input
python manage.py migrate

# Automatically create superuser if not present
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()

username = 'dhananjay@admin'
email = 'dhananjay@admin.gmail.com'
password = 'Dhanjay@Admin'

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=email, password=password)
    print('Superuser created successfully.')
else:
    print('Superuser already exists. Skipping creation.')
"