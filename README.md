# RehabilitacionApp-TFG

## Introducción
Aplicación desarrollada con Streamlit para la gestión integral del proceso de rehabilitación. 

Permite registrar solicitudes de pacientes con su prioridad, especialidad y área, preferencias de tratamiento, transporte y días de asistencia; consultar la lista de espera y asignar pacientes elegibles a profesionales según su prioridad; y administrar los tratamientos activos, sus sesiones y las altas.

También facilita el seguimiento clínico mediante el registro de asistencia, incidencias, notas, evolución funcional, dolor y cumplimiento de objetivos. Incluye vistas de resumen y estadísticas, historial de actividad para auditar operaciones relevantes y herramientas de administración para gestionar usuarios, especialidades y áreas. 

La aplicación almacena la información en una base de datos PostgreSQL y ofrece controles de acceso según el rol del usuario.
## Requisitos

- Python 3
- Una base de datos PostgreSQL accesible desde la aplicación

## Instalación en Windows

Desde la carpeta raíz del proyecto, abre PowerShell y ejecuta:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt