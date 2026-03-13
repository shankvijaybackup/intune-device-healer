#!/bin/bash
# Install required Python packages into the virtual environment
VENV_PATH="/Users/vijayshankar/.gemini/antigravity/scratch/SentientAI Agent/intune-device-healer/venv"
if [ ! -d "$VENV_PATH" ]; then
  python3 -m venv "$VENV_PATH"
fi
source "$VENV_PATH/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt
