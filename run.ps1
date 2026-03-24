# Script para arrancar la app con Streamlit desde PowerShell
Write-Host "Instalando dependencias..."
pip install -q -r requirements.txt

Write-Host ""
Write-Host "Iniciando Football Predictor..."
Write-Host ""
streamlit run app_streamlit.py
