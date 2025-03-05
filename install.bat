del /f /q bot_venv
python -m venv bot_venv
call bot_venv\Scripts\activate
call pip install -r requirements.txt
ECHO Done
