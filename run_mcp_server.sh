#!/bin/bash
# MCP Server Launcher for Intune Device Healer
# This script ensures the correct Python environment is used

# Change to project directory
cd "/Users/vijayshankar/.gemini/antigravity/scratch/SentientAI Agent/intune-device-healer"

# Activate virtual environment and run server
source "/Users/vijayshankar/.gemini/antigravity/scratch/SentientAI Agent/intune-device-healer/venv/bin/activate"
exec python src/server.py
