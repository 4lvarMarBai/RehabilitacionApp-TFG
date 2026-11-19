# Gestión de Rehabilitación — TFG

Aplicación para gestionar solicitudes de rehabilitación, organizar la lista de espera por prioridad y antigüedad, registrar tratamientos y sesiones, consultar la evolución de los pacientes y tramitar altas.

Incluye acceso por roles de administrador, clínico y médico, gestión de usuarios y catálogos, auditoría y generación de resúmenes con IA mediante Ollama. La IA requiere la aceptación registrada del paciente y sus resultados deben ser revisados por un profesional.

## Módulos del repositorio

El navegador accede a Streamlit a través de Caddy. Streamlit consulta la API de FastAPI y esta utiliza PostgreSQL y, al generar un resumen, Ollama.

| Carpeta | Módulos principales |
| --- | --- |
| `cliente/` | `app.py` contiene las pantallas. `api_client.py` comunica Streamlit con la API. `pagination.py` y `ui_helpers.py` reúnen los controles de paginación y otras utilidades de interfaz. |
| `api/` | `main.py` define las rutas. `schemas.py` valida las peticiones y `security.py` comprueba sesiones y permisos. `db.py` gestiona las conexiones e `init_db.py` prepara la base de datos. `queries.py`, `pagination.py` y `serialization.py` preparan los datos que devuelve la API. |
| `servidor/` | `services.py` aplica las reglas de rehabilitación. `database.py`, `auth.py` y `catalogos.py` gestionan la persistencia, los usuarios y los catálogos. `ai_policy.py` aplica las restricciones de IA y `ai_clinical.py` solicita y prepara los borradores de Ollama. |
| `comun/` | `config.py` reúne constantes como prioridades y turnos. `validators.py` contiene las validaciones compartidas. |
| `scripts/` | Arranque y parada del servidor, preparación de accesos directos y exportación del certificado HTTPS. Los archivos `.vbs` de la raíz ejecutan las operaciones de arranque, parada y creación de accesos. |
| `configuracion/` | Configuración de la API y de Caddy en el equipo servidor. |
| `recursos/` | Icono y, tras ejecutar los scripts de preparación, certificado público y enlace de acceso. |
| `docs/` | Manual técnico e instrucciones de instalación y operación. |

| Componente | Dónde se configura |
| --- | --- |
| API y PostgreSQL | En `configuracion/.env.api`, mediante `DATABASE_URL` y `ADMIN_INITIAL_PASSWORD` para el primer arranque. |
| Streamlit | En `.streamlit/secrets.toml`, mediante `API_BASE_URL`. También se puede indicar como variable de entorno. |
| Caddy | En `configuracion/Caddyfile`, donde se establece la dirección HTTPS y el destino interno de Streamlit. |
| Ollama | La API lee `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT` y el modo de uso de IA desde `configuracion/.env.api`. Las opciones del propio proceso de Ollama, como `OLLAMA_NO_CLOUD`, se configuran en el equipo servidor. |

Consulta el [manual técnico](docs/Manual_tecnico_instalacion.md) para los detalles de instalación y los requisitos del modo clínico.

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

## Resúmenes con datos reales

El modo predeterminado de la IA es `demo`. Solo el rol Médico, vinculado a la profesión Médico rehabilitador, puede generar y consultar resúmenes de IA de los tratamientos de cualquier paciente, sin necesitar una asignación previa. En modo clínico contrasta el resultado con las sesiones originales. La aplicación conserva la decisión del paciente y la referencia al consentimiento explícito documentado conforme al protocolo del centro.

El centro debe validar la finalidad, la seguridad del despliegue y la calidad de los resúmenes antes de habilitar este modo. Debe determinar si el consentimiento es la base adecuada y si el uso previsto está sujeto a la normativa de producto sanitario. La referencia del protocolo es un dato de configuración. El centro conserva la documentación que respalda esa referencia.

En Ollama, deshabilita las funciones de nube con `OLLAMA_NO_CLOUD=1` en el entorno del proceso de Ollama. Reinícialo y verifica que el registro indique `Ollama cloud disabled: true`. Tras verificar el despliegue y disponer de la autorización del centro, añade a `configuracion/.env.api` estas variables y reinicia la API y Streamlit:

```ini
AI_USE_MODE=clinical
AI_CLINICAL_PROTOCOL=REFERENCIA_DEL_PROTOCOLO_APROBADO
AI_LOCAL_ONLY_CONFIRMED=true
```

Los clínicos consultan y modifican sus tratamientos asignados; los médicos pueden consultar todos los pacientes y son los únicos que generan resúmenes de IA. El administrador conserva la gestión administrativa y los registros de acceso, sin acceso a notas ni informes clínicos. Las conexiones remotas a PostgreSQL verifican el certificado y el nombre del servidor. Estos controles requieren evaluación en la instalación del centro antes de utilizar datos reales.
