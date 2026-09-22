@echo off
cd /d "%~dp0.."
echo 正在合成单题速通训练音频（需要 fish.audio 可达）...
.venv\Scripts\python glm-workflow\generate_question_kit.py --kit glm-workflow\demo_smartphones.kit.json --media --force
pause
