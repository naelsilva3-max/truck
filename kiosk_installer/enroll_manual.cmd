@echo off
set /p EMPID="Digite o ID do funcionario: "
"%~dp0kiosk_agent.exe" enroll --employee-id %EMPID%
echo.
pause
