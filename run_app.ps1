# Script de arranque para la aplicacion SENA Certificacion App
# Evita el error "OpenBLAS error: Memory allocation still failed after 10 retries"
# limitando el numero de hilos usados por OpenBLAS/OpenMP en Windows.

# Establece variables de entorno EN EL PROCESO ACTUAL (no requiere admin)
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS      = "1"
$env:MKL_NUM_THREADS      = "1"
$env:VECLIB_MAXIMUM_THREADS = "1"
$env:NUMEXPR_NUM_THREADS  = "1"

Write-Host "= SENA Certificacion App =" -ForegroundColor Cyan
Write-Host "OPENBLAS/OMP threads = 1 (evita error de memoria OpenBLAS en Windows)" -ForegroundColor Gray
Write-Host "URL: http://localhost:8000" -ForegroundColor Green
Write-Host "Docs: http://localhost:8000/docs" -ForegroundColor Green
Write-Host "Detener: Ctrl + C`n" -ForegroundColor Yellow

py -3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
