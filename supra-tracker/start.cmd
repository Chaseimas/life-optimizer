@echo off
cd /d %~dp0
if not exist logs mkdir logs
node server.js >> logs\tracker.log 2>&1
