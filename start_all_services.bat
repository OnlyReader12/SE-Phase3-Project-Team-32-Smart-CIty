# Windows batch script to start all Smart City microservices in new terminals

start "AccessControl" cmd /k "cd /d %~dp0core_modules\AccessControl && python main.py"
start "IngestionEngine" cmd /k "cd /d %~dp0core_modules\IngestionEngine && python main.py"
start "EHSEngine" cmd /k "cd /d %~dp0core_modules\EHSEngine && python main.py"
start "EnergyManagementEngine" cmd /k "cd /d %~dp0core_modules\EnergyManagementEngine && python main.py"
