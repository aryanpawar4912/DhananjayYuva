#!/usr/bin/env bash
# Exit immediately if a command fails
set -o errexit

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Collect static files & run database migrations
python manage.py collectstatic --no-input
python manage.py migrate

# Automatically create superuser if environment variables are set and user doesn't exist
python manage.py shell -c "
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

if username and password:
    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username=username, email=email, password=password)
        print('Superuser created successfully.')
    else:
        print('Superuser already exists. Skipping creation.')
else:
    print('Superuser environment variables not set. Skipping creation.')
"