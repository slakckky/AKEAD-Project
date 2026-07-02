#!/bin/bash
cd "$(dirname "$0")"
if [ -f ".venv/bin/python3" ]; then
    exec .venv/bin/python3 app.py
elif [ -f ".venv/bin/python" ]; then
    exec .venv/bin/python app.py
else
    osascript -e 'display alert "Setup required" message "Run setup first:\n\npython3 -m venv .venv\nsource .venv/bin/activate\npip install -r requirements.txt"'
fi
