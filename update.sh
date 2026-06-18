#!/bin/bash
cd /root/RoadRadio/backend
pkill -f "uvicorn main:app" 2>/dev/null
sleep 1
git pull origin main
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 >> radio.log 2>&1 &
sleep 2
tail -3 radio.log
echo "Done."
