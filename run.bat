@echo off
REM Script para arrancar la app con Streamlit
echo Instalando dependencias...
pip install -q -r requirements.txt

echo.
echo Iniciando Football Predictor...
echo.
streamlit run app_streamlit.py
pause
