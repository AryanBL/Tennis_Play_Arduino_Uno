#!/usr/bin/env bash
set -e
python3 -m pip install -r requirements.txt
python3 web/manage.py runserver 5000
