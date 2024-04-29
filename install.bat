del /f /q bot_venv
python -m venv bot_venv
cd bot_venv/Scripts
call pip install -r ../../requirements.txt
ECHO Done
