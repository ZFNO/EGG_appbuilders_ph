@echo off
REM Download the AppBuilders PH hackathon VOD audio into .\audio\ (relative to this script).
setlocal
set "HERE=%~dp0"
set "YOUTUBE_DL=%HERE:~0,-1%"
python "%HERE%..\module\YTDL.py" https://youtube.com/watch?v=sTcnZ_tk8vA --a
echo done > "%HERE%audio_status.txt"
