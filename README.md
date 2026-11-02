# Gestión de Rehabilitación — TFG

Aplicación para gestionar solicitudes de rehabilitación, organizar la lista de espera por prioridad y antigüedad, registrar tratamientos y sesiones, consultar la evolución de los pacientes y tramitar altas.

Incluye acceso por roles de administrador y clínico, gestión de usuarios y catálogos, auditoría y generación de resúmenes con IA mediante Ollama. La IA requiere la aceptación registrada del paciente y sus resultados deben ser revisados por un profesional.

## Requisitos

- Python 3.11 o posterior.
- Una base de datos PostgreSQL disponible.
- Ollama con el modelo `qwen2.5:7b-instruct`, para utilizar los resúmenes con IA.

## Instalación y configuración

Ejecuta estos comandos desde la carpeta principal del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-api.txt
```

Crea `configuracion/.env.api` con la conexión de PostgreSQL y una contraseña inicial privada de al menos 12 caracteres:

```ini
DATABASE_URL="TU_CONEXION_POSTGRESQL"
ADMIN_INITIAL_PASSWORD="TU_CONTRASEÑA_INICIAL"
OLLAMA_MODEL=qwen2.5:7b-instruct
```

La contraseña inicial solo se utiliza si todavía no existe el administrador. Crea `.streamlit/secrets.toml` con:

```toml
API_BASE_URL = "http://127.0.0.1:8000"
```

Inicializa las tablas una vez, comprobando antes que has configurado la base de datos correcta:

```powershell
.\.venv\Scripts\python.exe -m api.init_db
```

## Ejecución

Inicia la API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --env-file configuracion/.env.api --host 127.0.0.1 --port 8000 --no-access-log
```

En otra terminal, inicia la aplicación:

```powershell
.\.venv\Scripts\python.exe -m streamlit run cliente/app.py --server.address 127.0.0.1
```

Para acceso HTTPS local, inicia también `powershell -ExecutionPolicy Bypass -File scripts/iniciar_https.ps1`. Abre `https://192.168.1.115` desde los dispositivos de la misma red, tras instalar en ellos el certificado de confianza local. El cortafuegos debe permitir el puerto 443 en redes privadas. El equipo servidor debe permanecer encendido con los tres servicios funcionando. Para utilizar IA, Ollama también debe estar en ejecución en ese equipo.

El administrador crea los usuarios, que acceden con su DNI y una contraseña temporal que deben cambiar en el primer inicio. Ejecuta `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crear_accesos.ps1` para crear los dos accesos. «Rehabilitacion - Servidor» inicia API, Streamlit y Caddy y abre la aplicación. «Rehabilitacion - Usuario» solo abre la URL y puede copiarse a otros equipos. Cada equipo necesita confiar en el certificado local. El enlace no inicia sesión: cada usuario debe identificarse con su propia cuenta. Ollama se abre por separado cuando se utilice la función de resumen. Los errores de arranque se guardan en `logs/`. Si cambia la IP, actualiza Caddyfile y vuelve a crear y distribuir el enlace de usuario.

## Datos y seguridad

PostgreSQL almacena los datos y solo la API utiliza sus credenciales. No subas a Git contraseñas, archivos de secretos ni bases de datos con información de pacientes. El acceso HTTP en la red local se destina a pruebas con datos ficticios; utiliza HTTPS para trabajar con datos reales.
