@echo off
python -m pip install -r requirements.txt
python web\manage.py runserver 5000
