# Manual técnico y de instalación

**Proyecto:** RehabilitacionApp-TFG  
**Versión del manual:** 1.5, 19 de noviembre de 2026\
**Plataforma de instalación descrita:** Windows, PowerShell y servidor en red local.

## 1. Alcance

Este documento explica la estructura, la instalación y la operación de la aplicación. La IA arranca en modo de demostración con casos ficticios. El modo clínico permite generar borradores con datos reales cuando el centro ha aprobado el uso previsto y ha completado los requisitos de los apartados 6.12 y 9.1.

Hay dos equipos conceptualmente distintos: el **servidor**, que ejecuta los procesos, y el **puesto del usuario**, que abre un navegador. Pueden ser el mismo ordenador durante las pruebas.

Las rutas de ejemplo corresponden a la instalación de Alvar. En otro equipo deben sustituirse por la carpeta real. Los comandos se ejecutan en PowerShell salvo indicación expresa.

## 2. Arquitectura y comunicaciones

```mermaid
flowchart LR
    N[Navegador] -->|HTTPS 443| C[Caddy]
    C -->|HTTP local 8501| S[Streamlit]
    S -->|HTTP local 8000 y JSON| A[FastAPI / Uvicorn]
    A -->|Psycopg| D[(PostgreSQL)]
    A -->|HTTP local 11434| O[Ollama]
```

| Componente | Función | Exposición prevista |
|---|---|---|
| Caddy | Certificados locales y proxy HTTPS hacia Streamlit. | Puerto 443 accesible en la red autorizada. |
| Streamlit | Formularios, estado de la sesión, tablas y gráficos. | `127.0.0.1:8501`. |
| API | Autenticación, permisos, validaciones y operaciones del dominio. | `127.0.0.1:8000`. |
| PostgreSQL | Persistencia de usuarios y datos de rehabilitación. | Ubicación definida en DATABASE_URL. |
| Ollama | Inferencia del modelo local para los borradores. | Habitualmente `127.0.0.1:11434`. |

El navegador no llama directamente a la API de negocio: Streamlit ejecuta Python en el servidor y realiza esas peticiones. Por eso el cliente puede utilizar `API_BASE_URL=http://127.0.0.1:8000` aunque el navegador esté en otro ordenador.

HTTPS termina en Caddy. Los tramos Caddy–Streamlit y Streamlit–API son HTTP local. Las conexiones a PostgreSQL fuera del equipo utilizan `sslmode=verify-full`, con comprobación del certificado y del nombre del servidor. HTTPS y TLS no cifran los archivos del disco. Si PostgreSQL está en Supabase, los datos almacenados siguen estando en ese servicio aunque la inferencia de IA sea local.

## 3. Estructura del repositorio

```text
api/             Rutas, esquemas HTTP, autorización y conexiones
cliente/         Interfaz Streamlit y cliente HTTP
comun/           Catálogos constantes y validadores compartidos
servidor/        Persistencia y operaciones de rehabilitación e IA
scripts/         Arranque, certificados y distribución
configuracion/   Caddyfile y secretos privados del servidor
recursos/        Icono, certificado público exportado y enlace de usuario
datos/           Datos locales y estado privado de Caddy
logs/            Registros de arranque
.streamlit/      Configuración de Streamlit
.venv/           Entorno Python local
```

Las últimas cuatro carpetas y diversos archivos privados se generan o se preparan en cada instalación. No todo este árbol se descarga desde GitHub.

### 3.1. Interfaz

| Archivo | Responsabilidad |
|---|---|
| `cliente/app.py` | Navegación, formularios, acciones del usuario y presentación. |
| `cliente/api_client.py` | Peticiones HTTP, Bearer token, errores, conexiones persistentes y reutilización de lecturas por ejecución. |
| `cliente/pagination.py` | Tamaño de página, navegación y reinicio al cambiar los filtros de cada listado. |
| `cliente/ui_helpers.py` | Etiquetas legibles y calendario de sesiones. |
| `comun/config.py` | Prioridades, turnos, transporte, patrones de días y meses españoles. |
| `comun/validators.py` | DNI, NHC, preferencias, horarios y coordinación. |

### 3.2. API y servidor

| Archivo | Responsabilidad |
|---|---|
| `api/main.py` | Rutas y comprobaciones antes de invocar servicios. |
| `api/schemas.py` | Modelos Pydantic, campos admitidos y límites de entrada. |
| `api/security.py` | Tokens, caducidad, límite de accesos y dependencias de autorización. |
| `api/db.py` | Apertura y cierre del pool; una conexión prestada por petición. |
| `api/queries.py` | Listados con nombres permitidos y filtros parametrizados. |
| `api/pagination.py` | Consulta de páginas, recuento total y reajuste de páginas fuera de rango. |
| `api/serialization.py` | Conservación de fechas y horas al convertirlas a JSON. |
| `api/init_db.py` | Inicialización explícita de tablas, índices y administrador. |
| `servidor/database.py` | SQL de esquema, helpers de consulta y lectura de DATABASE_URL. |
| `servidor/auth.py` | Hashes, verificación y creación de usuarios y catálogos de acceso. |
| `servidor/catalogos.py` | Especialidades, áreas y profesiones. |
| `servidor/services.py` | Solicitudes, asignación, sesiones, altas, indicadores, consentimiento y auditoría. |
| `servidor/ai_clinical.py` | Petición a Ollama y construcción del borrador identificado. |
| `servidor/ai_policy.py` | Selección del modo, versión del protocolo clínico, destino local, minimización básica y huellas. |

Los archivos `__init__.py` delimitan paquetes. Pueden estar vacíos. El nombre `conn` que conserva la interfaz es un parámetro de compatibilidad; Streamlit no abre mediante él una conexión local a PostgreSQL.

### 3.3. Arranque y parada del servidor

| Archivo | Responsabilidad |
|---|---|
| `IniciarServidor.vbs` | Ejecuta el lanzador del servidor sin abrir una terminal visible. |
| `scripts/iniciar_servidor.py` | Inicia o reutiliza API, Streamlit y Caddy y comprueba que respondan. |
| `DetenerServidor.vbs` | Ejecuta la parada desde el acceso directo del administrador. |
| `scripts/detener_servidor.py` | Solicita confirmación y coordina la parada de los servicios registrados. |
| `scripts/procesos_servidor.py` | Registra y comprueba la identidad de los procesos de esta instalación antes de detenerlos. |
| `scripts/crear_accesos.ps1` | Genera los accesos de servidor, parada y usuario para la carpeta y URL actuales. |

## 4. Recorridos principales del código

### 4.1. Autenticación

`cliente/app.py` recoge las credenciales y `api_client.py` envía POST `/auth/login`. La API aplica los límites, consulta la cuenta y verifica su hash PBKDF2-HMAC-SHA256 con sal aleatoria y 600.000 iteraciones. Los hashes antiguos se actualizan tras una comprobación válida.

El servidor entrega un token aleatorio opaco, no JWT. PostgreSQL conserva su hash, el usuario y la caducidad de 30 minutos. Cada operación protegida comprueba token, usuario activo, cambio obligatorio y rol. El DNI recibido al iniciar sesión se normaliza; la contraseña distingue mayúsculas y minúsculas.

Las funciones administrativas usan `admin_user`; las clínicas usan `ready_user`. La comprobación del rol no depende de que un botón esté visible. Las cuentas nuevas utilizan su DNI como usuario y una contraseña temporal única. El rol se calcula en el servidor a partir de la profesión.

### 4.2. Escritura de solicitudes y asignaciones

La API valida entradas y catálogos antes de llamar a `add_waiting_patient_multiple`. Esta guarda las entradas de espera y su auditoría en una transacción. En modo de demostración guarda también la decisión simulada sobre IA. En modo clínico, la solicitud puede registrarse sin consentimiento de IA. El médico rehabilitador puede registrar la decisión documentada desde Seguimiento clínico; el clínico asignado también puede registrarla, pero no puede generar ni consultar resúmenes de IA.

Antes de crear solicitudes, el servidor comprueba si el mismo NHC ya tiene registros para la misma especialidad y área creados en los últimos **tres meses naturales**. Las solicitudes pendientes y las asociadas a un tratamiento activo se comprueban aunque sean anteriores. En especialidades sin áreas, se compara la especialidad y el área vacía. La fecha que se utiliza es la de creación del registro en el sistema, no la fecha de solicitud que introduce el usuario.

Si hay coincidencias, la API responde con un aviso `409 DUPLICATE_REQUEST` sin guardar ninguna entrada del envío. Streamlit muestra las especialidades y áreas afectadas; el usuario puede marcar la confirmación y pulsar de nuevo **Guardar solicitud**. Cualquier cambio en el formulario invalida esa confirmación. El envío confirmado usa `confirm_duplicate=true` y la auditoría de las entradas repetidas deja constancia de la confirmación. Un bloqueo transaccional por NHC evita que dos envíos simultáneos pasen la comprobación antes de guardar el primero. Al actualizar, `python -m api.init_db` añade el índice de consulta por NHC, especialidad, área y fecha sin borrar registros.

`_waiting_filters` comparte condiciones entre vista previa y asignación. El orden SQL es Personal SACYL, urgente, preferente y ordinario, seguido de fecha y de identificador. No hay ascenso de prioridad por superar umbrales de espera.

La asignación usa `FOR UPDATE SKIP LOCKED` dentro de una transacción para evitar seleccionar simultáneamente la misma solicitud. Copia preferencias al tratamiento activo y conserva la referencia a la solicitud. El autor y el clínico asignado proceden de la identidad autenticada.

### 4.3. Sesiones, altas y auditoría

Al guardar una sesión, la API bloquea el tratamiento y comprueba que siga activo, los horarios y los motivos exigidos. Una falta no conserva hora ni EVA. El alta actualiza el estado y registra un evento con motivo y autor.

`add_treatment_session` guarda la sesión y el evento `REGISTRO_SESION` en una misma transacción. La auditoría incluye `session_id`, tratamiento, NHC, especialidad, estado de la sesión y DNI del clínico. Si falla la escritura del evento, se revierte también la sesión.

`delete_active_treatment` conserva su nombre por compatibilidad, pero desactiva el tratamiento: cambia su estado a `ELIMINADO_ADMIN`, mantiene sus sesiones y registra `DESACTIVACION_ADMIN_TRATAMIENTO`. Bloquea la fila y solo admite tratamientos en estado `ACTIVO`; una segunda desactivación o un intento sobre un tratamiento dado de alta no modifica el historial. La operación ya no genera eventos `ELIMINACION_SESION`, porque no borra esas filas.

Los indicadores de seguimiento contabilizan las faltas para la asistencia, pero solo toman EVA, estado funcional y objetivos de sesiones REALIZADA o REVISION. Para calcular una tendencia del dolor se necesitan al menos dos medidas; una sola no se interpreta como estancamiento.

**Registrar sesiones** ofrece un bloque independiente **Movilidad funcional · TUG (opcional)**. El profesional puede registrar el tiempo y las condiciones de la prueba cuando resulte relevante, aunque el tratamiento no sea de rodilla. No requiere activar las medidas de rodilla. El seguimiento y los informes presentan el TUG como movilidad funcional, separado de las medidas articulares.

El bloque **Medidas y objetivo de rodilla** mantiene la flexión, los grados que faltan para la extensión completa y el cuestionario KOOS, JR, específico de rodilla para artroplastia. Registra siempre la misma rodilla por tratamiento. Las medidas son opcionales y un campo vacío representa una medida ausente. Un déficit de extensión de 0° indica extensión completa. El servidor convierte la suma del KOOS, JR (0–28) a su puntuación de 0–100 usando la tabla oficial. [Instrucciones de puntuación del KOOS, JR](https://www.hss.edu/globalassets/files/research/hss-koos-jr-scoring-instructions.pdf)

El profesional puede fijar una flexión mínima o un déficit de extensión máximo. **Seguimiento clínico** y **Dashboard clínico** muestran la evolución y el último valor registrado para la meta vigente. Los tiempos del TUG se comparan entre registros con las mismas condiciones anotadas. El cumplimiento del umbral describe la medición; la valoración terapéutica sigue a cargo del profesional.

Los campos de rodilla se validan en la API y se guardan con la sesión. El historial conserva las metas fijadas y el seguimiento aplica la última en orden cronológico. Si se fija una meta nueva sin registrar la medida correspondiente, el informe la muestra pendiente de medición hasta disponer de un dato posterior. Una sesión previa a la migración mantiene vacíos los campos nuevos. El formulario deja vacía la EVA para diferenciar una medición ausente de un dolor con valor 0.

El listado de auditoría muestra registros existentes de `assignment_log`. Sus recuentos de realizadas y revisiones al alta se calculan con las sesiones que constan creadas antes de la fecha del evento; no son una instantánea inmutable firmada.

El filtro de eventos del Dashboard incluye la desactivación administrativa. Los eventos antiguos de eliminación de tratamiento siguen disponibles como históricos. La corrección del código no reescribe los registros previos: si existen eventos `ELIMINACION_SESION` emitidos por la versión anterior sin un borrado real, deben contrastarse con las sesiones conservadas.

El registro de visitas se realiza en el servidor al consultar una historia individual con rol CLINICO o MEDICO. Guarda DNI, NHC y fecha de Europe/Madrid. La clave compuesta evita duplicados para esa combinación durante un día.

### 4.4. Integración de IA

Hay tres roles: ADMIN administra usuarios y catálogos; CLINICO registra y consulta la actividad asistencial; MEDICO conserva el acceso asistencial y es el único que puede generar y visualizar los resúmenes de IA. La profesión determina automáticamente el rol: Administrador → ADMIN, Médico rehabilitador → MEDICO y el resto → CLINICO. El cliente no puede elegir un rol más privilegiado enviándolo a la API.

Al reiniciar la API, `init_user_roles()` amplía la restricción de PostgreSQL y convierte las cuentas existentes de Médico rehabilitador con rol CLINICO a MEDICO, sin cambiar DNI ni contraseña. También se ejecuta desde la inicialización completa. Haz una copia de seguridad antes de actualizar una instalación y reinicia API y Streamlit para cargar el nuevo código. La cuenta de base de datos debe poder modificar la tabla `users`. Las cuentas de otras profesiones conservan su rol.

Idealmente, lo hará el médico asignado por el centro al paciente. Esta recomendación no se guarda como una asignación nueva ni restringe el acceso de los demás médicos.

El acceso no combina los tratamientos del paciente en un único informe: el médico selecciona el NHC y el tratamiento concreto en Seguimiento clínico. Puede repetirlo para las distintas especialidades. Los clínicos y los administradores no reciben el texto de IA, aunque escriban manualmente la ruta de la API. El servidor registra `GENERACION_RESUMEN_IA` con DNI del médico, NHC, tratamiento, fecha y huellas del contenido; la consulta individual queda también en el registro diario de visitas. Se auditan las generaciones completadas; los resultados rechazados no se registran como generaciones correctas.


La ruta autenticada POST `/treatments/{id}/ai-summary` consulta el tratamiento activo seleccionado y sus sesiones REALIZADA o REVISION con contenido clínico. Identifica las fuentes como F1, F2 y siguientes. El servidor aplica los controles correspondientes al modo configurado.

| Modo | Requisitos para generar | Resultado |
|---|---|---|
| `demo`, predeterminado | Rol MEDICO (profesión Médico rehabilitador), aceptación simulada registrada y confirmación explícita de que el caso y los informes son ficticios. | Borrador marcado como demostración, con indicadores y descarga JSON. |
| `clinical` | Protocolo configurado, instalación local verificada, rol MEDICO, tratamiento activo y consentimiento explícito documentado para la versión vigente del protocolo. | Borrador descriptivo basado en las sesiones, con fuentes y revisión profesional pendiente. |
| IA deshabilitada | Un valor de modo distinto de `demo` o `clinical`, o un modo clínico con configuración incompleta, impide la generación. | La aplicación muestra que la IA está deshabilitada. |

En modo clínico, el profesional registra la aceptación o el rechazo en **Seguimiento clínico**. La aceptación requiere una referencia interna al consentimiento explícito que conserva el centro. Usa un código de hasta 80 caracteres que empiece por letra ASCII o número y utilice solo letras ASCII, números, puntos, guiones, barras o guiones bajos. Registra la retirada como rechazo. Las aceptaciones simuladas y las de otras versiones del protocolo quedan fuera de la comprobación clínica vigente. El servidor comprueba en PostgreSQL que la cuenta del médico siga activa, mantenga el rol MEDICO y la profesión Médico rehabilitador, y vuelve a comprobar el consentimiento antes de entregar el borrador. No exige que el tratamiento esté asignado al médico solicitante.

La API envía la solicitud a `/api/chat` en la dirección local del servidor, sin proxies del entorno ni redirecciones. La entrada serializada tiene un máximo de 24.000 caracteres. La minimización oculta algunos identificadores, como NHC, DNI y correo electrónico. Las notas pueden conservar otros datos que identifiquen al paciente y deben tratarse como datos de salud. La API rechaza respuestas inválidas o incompletas. El centro debe verificar con informes representativos que el contexto de Ollama admite el volumen de texto previsto.

En modo clínico, la aplicación numera los fragmentos de cada informe y pide a Ollama que los clasifique mediante una respuesta JSON estructurada. El servidor valida que estén todas las fuentes y que cada fragmento tenga una categoría admitida. Luego construye el resumen con los fragmentos conservados, sus fechas y sus referencias originales. Una respuesta inválida se rechaza. [Salidas estructuradas de Ollama](https://docs.ollama.com/capabilities/structured-outputs)

Cuando hay un TUG, medidas de rodilla u objetivo individual, el servidor incorpora al informe los valores registrados y su cambio cuando existe una comparación válida. El TUG aparece como movilidad funcional; las medidas y objetivos de rodilla se presentan por separado. Los cálculos y la puntuación se obtienen de los registros y quedan identificados aparte del texto resumido por Ollama. Esta separación utiliza las columnas existentes y no requiere una migración adicional de la base de datos.

El informe automático de seguimiento y el apartado numérico del informe con IA comparten el cálculo de `servidor/seguimiento_rodilla.py`. La conversión del KOOS, JR está en `comun/medidas_rodilla.py`. La huella de salida entregada por la API y la auditada cubren el texto combinado.

Para verificar la integración se usaron Ollama y un esquema temporal de PostgreSQL. Se generaron tres informes ficticios para comprobar una meta alcanzada, una meta nueva pendiente con un TUG en condiciones diferentes y un historial anterior a la migración. La comprobación también incluyó el bloqueo sin consentimiento, la huella del texto y los eventos de auditoría.

En la interfaz, los campos de informe son de solo lectura y se actualizan al cambiar de tratamiento o al regenerar el texto.

El profesional contrasta el resultado con las notas originales y comprueba si falta algún dato relevante antes de incorporar información a la documentación clínica del centro.

**Verificación de fidelidad documental.** Con el modelo local `qwen2.5:7b-instruct` y las instrucciones `clinical-summary-v12`, se contrastaron 50 resúmenes de 228 informes ficticios breves. Los 50 coincidieron con sus fuentes y fechas, sin datos añadidos ni omisiones detectadas. En los 34 casos comparados con las versiones anteriores, hubo incidencias en 33 con las instrucciones originales, en 11 con el primer refuerzo y en 0 con la versión final. El 100 % observado describe la fidelidad en ese conjunto de prueba. Queda pendiente evaluar la selección con informes reales y determinar su utilidad asistencial.

El texto se muestra en la sesión de Streamlit como borrador pendiente de revisión. La descarga JSON está disponible en la demostración. La auditoría registra la generación, el profesional, el modelo, la versión de las instrucciones y las huellas de entrada y salida. En modo clínico registra también la versión del protocolo. La incorporación del contenido revisado a la historia corresponde al profesional.

## 5. Persistencia y rendimiento

| Tabla | Contenido |
|---|---|
| `users` | Identidad profesional, profesión, rol, hash y estado. |
| `professions_config` | Profesiones y disponibilidad. |
| `specialties_config`, `subspecialties_config` | Especialidades y áreas. |
| `waitlist` | Solicitudes y sus preferencias. |
| `rehab_active` | Tratamientos asignados, estado y alta. |
| `treatment_sessions` | Sesiones, faltas y observaciones. |
| `patient_ai_consent` | Decisión vigente registrada para IA. |
| `assignment_log` | Eventos de auditoría. |
| `clinical_visit_log` | Acceso diario de clínicos a historias. |
| `api_sessions`, `api_login_limits` | Sesiones y control de intentos de acceso. |

Los índices de inicialización apoyan filtros de pendientes, estados, NHC y búsqueda de sesiones por tratamiento. El pool de cada proceso API se configura con mínimo 1, máximo 5 conexiones y espera de 20 segundos. Ese máximo no equivale al número máximo de usuarios; las peticiones se turnan y un proceso adicional tendría su propio pool.

La interfaz reutiliza conexiones HTTP por sesión. Las lecturas idénticas se comparten solo durante una ejecución de Streamlit y se invalidan al escribir. `/bootstrap` agrupa la identidad, catálogos y, cuando corresponde, contadores. Resumen e informe de seguimiento comparten `/followup`. Las bibliotecas gráficas se cargan en sus pantallas y solo se consulta la vista seleccionada del Dashboard.

El esquema general se prepara con `api.init_db`, no en cada interacción. El arranque de la API sí prepara los catálogos de profesión y la tabla de visitas. Estas funciones necesitan permisos adecuados en PostgreSQL.

Al actualizar una instalación anterior a las medidas de rodilla, vuelve a ejecutar `python -m api.init_db` desde la raíz del proyecto con el entorno virtual del servidor y después reinicia los servicios. La actualización añade columnas opcionales a `treatment_sessions`; las sesiones previas conservan sus datos.

### 5.1. Paginación de pacientes e historiales

La lista de espera, los tratamientos activos, el histórico de altas y la auditoría utilizan paginación en el servidor. También se paginan los historiales de sesiones, los selectores de tratamientos para sesiones, seguimiento, alta y dashboard individual, y el listado de eventos del dashboard. En administración se paginan el registro de visitas, los usuarios, los catálogos y los selectores para corregir solicitudes o desactivar tratamientos. Solo se descarga la página solicitada.

Las rutas `/tables/{name}` y `/treatments/{id}/sessions` admiten `page`, a partir de 1, y `page_size`, entre 1 y 100. Al solicitar una página, la respuesta incorpora `columns`, `rows`, `page`, `page_size`, `total` y `total_pages`. Las consultas anteriores sin `page` mantienen su respuesta compatible; no debe suponerse que esos accesos antiguos devuelven una base completa.

El servidor aplica los filtros antes de contar y paginar. `COUNT(*) OVER()` obtiene el total del conjunto filtrado junto con las filas, y LIMIT/OFFSET selecciona el tramo solicitado. Cada consulta mantiene un orden fijo con desempate por identificador; los historiales de sesiones ordenan por fecha, hora e identificador. Si una página queda fuera de rango, se consulta el total y se reajusta a la última disponible. Un resultado vacío se presenta como página 1 de 1, con cero registros.

`cliente/pagination.py` ofrece tamaños de 25, 50 y 100, con 50 por defecto, y botones Anterior/Siguiente. Cada listado conserva su propia página en la sesión de Streamlit. Cambiar los filtros, el NHC, el tratamiento de un historial o el tamaño reinicia ese listado en la primera página. Los indicadores, gráficos e informes siguen calculándose con los datos completos del tratamiento.

Las páginas no constituyen una instantánea persistente: inserciones o cambios concurrentes pueden desplazar registros entre peticiones. El orden estable evita empates ambiguos, pero no congela la base durante la navegación. Para localizar un caso concreto debe utilizarse su NHC cuando la pantalla ofrezca ese filtro.

## 6. Instalación del equipo servidor

### 6.1. Requisitos y descarga

Prepara Windows, conexión a la base PostgreSQL y una instalación compatible de Python. El entorno utilizado en el desarrollo es Python 3.14; los lanzadores comprueban al menos 3.11, pero hay que verificar que los paquetes fijados se puedan instalar en la versión elegida. Para reproducir el entorno probado, utiliza Python 3.14.

Descarga o clona el repositorio completo en una carpeta estable. Evita moverlo después de crear los accesos, porque el acceso del servidor apunta a esa instalación.

Abre PowerShell y entra en la carpeta. Si contiene espacios, conserva las comillas:

```powershell
cd "C:\Users\Alvar Martinez\Desktop\TFG\RehabilitacionApp-TFG"
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-api.txt
```

Si el comando `python` no está disponible pero sí el lanzador de Windows, utiliza `py -3.14 -m venv .venv`. Una vez creado el entorno, los comandos siguientes usan su ejecutable explícito: no dependen de activar `.venv` ni de la configuración de PyCharm.

### 6.2. Preparar PostgreSQL

Descargar el repositorio no proporciona una base ni acceso a la base del autor. Debes disponer de una base PostgreSQL local o remota creada previamente y de sus credenciales. `api.init_db` crea las tablas dentro de esa base, pero no instala PostgreSQL ni crea la propia base.

Si se utiliza una base existente, realiza una copia de seguridad y verifica el destino antes de inicializar. No se debe usar la base asistencial de un centro para las pruebas del TFG.

### 6.3. Configuración privada del servidor

```powershell
New-Item -ItemType Directory -Path configuracion -Force
notepad .\configuracion\.env.api
```

Guarda una configuración como la siguiente, sustituyendo los marcadores:

```ini
DATABASE_URL="postgresql://USUARIO:CONTRASENA@SERVIDOR:5432/BASE"
ADMIN_INITIAL_PASSWORD="CONTRASENA_PRIVADA_DE_AL_MENOS_12_CARACTERES"
OLLAMA_URL="http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL="qwen2.5:7b-instruct"
AI_USE_MODE="demo"
```

No pegues estas asignaciones directamente como comandos de PowerShell. Son contenido del archivo. La contraseña con caracteres reservados de una URI debe codificarse correctamente. En un proveedor remoto utiliza su cadena indicada y configura la protección TLS de PostgreSQL según sus instrucciones: el certificado de Caddy no protege ese tramo.

El administrador inicial solo se crea si no existe. Sus credenciales para el primer acceso son:

- **Usuario:** `admin`.
- **Contraseña:** la que hayas elegido en `ADMIN_INITIAL_PASSWORD`, dentro de `configuracion/.env.api`. Debe tener al menos 12 caracteres; el texto del ejemplo es un marcador que debes sustituir, no una contraseña predeterminada.

La aplicación obliga a cambiar esa contraseña en el primer acceso. Cambiar después `ADMIN_INITIAL_PASSWORD` no modifica la contraseña de un administrador ya registrado. El archivo `.env.api` está excluido de Git y no debe compartirse con los usuarios.

### 6.4. Configurar Streamlit

```powershell
New-Item -ItemType Directory -Path .streamlit -Force
notepad .\.streamlit\secrets.toml
```

Contenido:

```toml
API_BASE_URL = "http://127.0.0.1:8000"
```

Es la dirección que usa el proceso Streamlit del servidor. No sustituyas localhost por la IP de cada puesto de usuario. La configuración privada de PostgreSQL no pertenece a este archivo del cliente.

### 6.5. Crear el esquema

```powershell
.\.venv\Scripts\python.exe -m api.init_db
```

El mensaje esperado es `Tablas preparadas. No se han insertado pacientes de prueba.`. En una base vacía se crea la cuenta `admin`, con cambio de contraseña obligatorio. El comando no inserta casos ficticios: hay que crearlos después desde la interfaz o mediante un procedimiento de prueba separado.

### 6.6. Instalar Caddy

El ejecutable se excluye de Git. Para Windows x64 se puede descargar del sitio oficial:

```powershell
New-Item -ItemType Directory -Path herramientas -Force
Invoke-WebRequest -Uri "https://caddyserver.com/api/download?os=windows&arch=amd64" -OutFile ".\herramientas\caddy.exe"
.\herramientas\caddy.exe version
```

En Windows ARM debe obtenerse el ejecutable correspondiente a esa arquitectura, conservando el nombre y ubicación `herramientas/caddy.exe` para estos scripts.

### 6.7. Configurar la dirección de red y HTTPS

Consulta `ipconfig` y localiza la IPv4 de la conexión activa. El cable y la wifi pueden tener direcciones diferentes. Para una instalación estable es preferible reservar la dirección del servidor en la configuración de la red.

Edita `configuracion/Caddyfile` y sustituye la IP del ejemplo por la del servidor:

```caddyfile
{
    skip_install_trust
    auto_https disable_redirects
}

https://192.168.1.115, https://localhost {
    tls internal
    reverse_proxy 127.0.0.1:8501
}
```

`tls internal` utiliza la autoridad local de Caddy. `skip_install_trust` deja la instalación de confianza como paso explícito. La redirección automática desde HTTP está desactivada: debe abrirse una URL que empiece por `https://`.

No es necesario publicar puertos en el router para trabajar dentro de la misma red. La red debe permitir comunicación entre los equipos; una wifi de invitados o una separación por VLAN puede impedirla.

### 6.8. Primer arranque manual

Abre tres terminales de PowerShell. En todas entra primero en la carpeta principal del proyecto.

**Terminal 1: API**

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --env-file configuracion/.env.api --host 127.0.0.1 --port 8000 --no-access-log
```

Comprueba `http://127.0.0.1:8000/health`. La respuesta `{"status":"ok"}` confirma que el proceso responde; no sustituye probar una consulta real a PostgreSQL. La descripción interactiva de rutas está en `http://127.0.0.1:8000/docs`.

**Terminal 2: Streamlit**

```powershell
.\.venv\Scripts\python.exe -m streamlit run cliente/app.py --server.address=127.0.0.1 --server.port=8501
```

Comprueba `http://127.0.0.1:8501` en el servidor. En `--server.address` se escribe solo la IP, sin `http://`, sin `https://` y sin puerto.

**Terminal 3: Caddy**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\iniciar_https.ps1
```

El script fija los directorios de datos y configuración de Caddy dentro de `datos/`. Debe utilizarse ese mismo almacenamiento para no generar una autoridad diferente accidentalmente.

### 6.9. Exportar e instalar la confianza

Con Caddy ya iniciado, en otra terminal:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\exportar_certificado_https.ps1
certutil -user -addstore Root ".\recursos\certificado_https_local.crt"
```

La exportación copia el certificado público y muestra su SHA-256 para poder comprobar que se distribuye el correcto. El segundo comando instala la confianza para el usuario de Windows que lo ejecuta. Cierra completamente el navegador y vuelve a abrirlo. Prueba `https://localhost`.

Distribuye únicamente `recursos/certificado_https_local.crt`. No distribuyas `datos/https`, `root.key` ni otras claves privadas. Si se conserva la misma autoridad, cambiar la IP y reemitir su certificado de servidor no exige reinstalar la raíz. Si se pierde o sustituye la autoridad, habrá que renovar la confianza de los puestos.

### 6.10. Cortafuegos

En la red doméstica de confianza, comprueba que el perfil de la conexión del servidor sea Privado. En una organización esta decisión corresponde al responsable de red.

Abre **PowerShell como administrador** y permite TCP 443 desde la misma subred:

```powershell
New-NetFirewallRule -DisplayName "Rehabilitacion HTTPS local" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 443 -Profile Private -RemoteAddress LocalSubnet
```

No es necesario abrir 8000 ni 8501 a los demás equipos para esta arquitectura. Si los usuarios están en otra subred autorizada, la regla `LocalSubnet` puede no cubrirlos; debe adaptarla informática. No desactives el cortafuegos para resolverlo.

### 6.11. Ollama, opcional para la generación

Instala Ollama en el servidor y abre una terminal nueva para actualizar su PATH. Después:

```powershell
ollama --version
ollama pull qwen2.5:7b-instruct
ollama list
```

Abre Ollama desde Inicio. Si no hay un servidor ejecutándose, utiliza `ollama serve`. Si el puerto 11434 ya está ocupado, comprueba si Ollama está abierto antes de intentar iniciar otra instancia.

El modelo requiere espacio de disco y memoria. Su velocidad depende del procesador, memoria y GPU; no se establece aquí un rendimiento mínimo garantizado. No se descarga ni se ejecuta automáticamente desde el acceso del servidor.

### 6.12. Habilitar el modo clínico

1. **Completa la revisión del centro.** Verifica los requisitos del apartado 9.1 y registra la referencia de la versión del protocolo aprobado. La implementación actual utiliza consentimiento explícito documentado. Si el centro determina otra base para el tratamiento, el flujo de registro debe adaptarse a esa decisión antes del despliegue.
2. **Configura Ollama en el servidor.** Mantén el servicio en la dirección local e instala el modelo `qwen2.5:7b-instruct`, que es el admitido en el modo clínico actual. Configura `OLLAMA_NO_CLOUD=1` en el entorno del proceso de Ollama. En Windows puedes usar una variable de usuario de la cuenta que ejecuta Ollama. Ciérralo por completo, vuelve a abrirlo y verifica en su registro `Ollama cloud disabled: true`. [Documentación de Ollama](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features)
3. **Configura la API.** En `configuracion/.env.api`, sustituye `AI_USE_MODE=demo` y añade los valores siguientes. Reemplaza el ejemplo de protocolo por la referencia real. Usa un código de hasta 80 caracteres con el formato indicado en el apartado 4.4. Marca `AI_LOCAL_ONLY_CONFIRMED=true` tras verificar el paso 2. Esta variable registra la comprobación realizada por el operador.

```ini
AI_USE_MODE=clinical
AI_CLINICAL_PROTOCOL=PROTOCOLO-IA-REHAB-v1
AI_LOCAL_ONLY_CONFIRMED=true
OLLAMA_URL=http://127.0.0.1:11434/api/chat
OLLAMA_MODEL=qwen2.5:7b-instruct
```

4. **Reinicia la API y Streamlit.** Con una cuenta Médico rehabilitador (rol MEDICO), comprueba que puede registrar el consentimiento documentado y generar el resumen de un tratamiento activo aunque esté asignado a otro profesional. Comprueba que los roles CLINICO y ADMIN reciben un rechazo al solicitar el resumen, y que la ausencia o retirada de consentimiento y la revocación de la cuenta médica bloquean la entrega.
5. **Controla la puesta en marcha.** Verifica que el entorno asistencial usa la base, las cuentas y los certificados aprobados por el centro. Si necesitas suspender la función, configura `AI_USE_MODE=disabled` y reinicia la API y Streamlit. Reserva el modo `demo` para el entorno con datos ficticios.

La API espera 480 segundos a Ollama de forma predeterminada. El cliente espera 540 segundos a la API. El error HTTP 504 identifica el agotamiento del tiempo de espera de Ollama.

## 7. Preparar un puesto de usuario

1. Conéctalo a la red autorizada.
2. Copia el certificado público verificado a una carpeta conocida.
3. Instálalo con el usuario de Windows que abrirá el navegador. Ejemplo si está en `F:\Downloads`:

```powershell
certutil -user -addstore Root "F:\Downloads\certificado_https_local.crt"
```

4. Reinicia el navegador y abre `https://IP_DEL_SERVIDOR`.
5. Recibe una cuenta y contraseña temporal del administrador.

No uses `https://localhost` en ese puesto: apuntaría al propio puesto. No necesita repositorio, entorno virtual ni credenciales de PostgreSQL.

## 8. Accesos directos y operación diaria

En el servidor, ejecuta:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\crear_accesos.ps1
```

También puedes ejecutar `CrearAccesoDirecto.vbs`. Se crean:

- **Rehabilitacion - Servidor.lnk:** llama a `IniciarServidor.vbs` y a `scripts/iniciar_servidor.py`; inicia o reutiliza API, Streamlit y Caddy, comprueba su respuesta y abre `https://localhost`.
- **Rehabilitacion - Detener servidor.lnk:** llama a `DetenerServidor.vbs` y a `scripts/detener_servidor.py`; solicita confirmación y detiene los servicios registrados de esta instalación. Se utiliza únicamente en el equipo servidor.
- **Rehabilitacion - Usuario.url:** abre la URL de red tomada del Caddyfile. Se copia también a `recursos/` y puede entregarse a los demás usuarios.

El lanzador del servidor utiliza Python del proyecto, no instala automáticamente dependencias y no inicia sesión como administrador. Abre procesos ocultos con registros en `logs/api.log`, `logs/streamlit.log` y `logs/caddy.log`. Si falla el arranque, muestra un mensaje e intenta detener únicamente los procesos creados en ese intento.

El acceso no es un servicio de Windows ni implica arranque automático tras reiniciar el sistema. Cerrar el navegador no detiene los procesos. Para cerrar los servicios iniciados con la versión actual del acceso «Servidor», utiliza «Rehabilitacion - Detener servidor». La confirmación advierte de que los usuarios conectados perderán el acceso. La parada cierra primero Caddy, después Streamlit y por último la API; Ollama permanece abierto. No sustituye al cierre de sesión de cada usuario.

El lanzador registra los procesos que crea en `logs/procesos_servidor.json`, junto con la carpeta de instalación, el PID, el ejecutable y la fecha de creación del proceso. La parada comprueba esa identidad para evitar cerrar otro proceso que haya reutilizado el mismo PID. Cierra también los procesos hijos del servicio, incluido el intérprete que puede crear el entorno virtual. Si no consigue detener un servicio, conserva su registro para poder volver a intentarlo.

Los servicios iniciados manualmente, los que el lanzador reutiliza sin haber registrado y los abiertos antes de incorporar esta función no quedan bajo su control. Si los iniciaste manualmente, usa Ctrl+C en sus terminales. Si están ocultos y no están registrados, identifica sus PID en el Administrador de tareas o mediante las herramientas de puertos antes de detenerlos; no finalices todos los procesos Python indiscriminadamente. `logs/servicios_iniciados.json` se conserva como ayuda del último arranque; el acceso de parada utiliza `logs/procesos_servidor.json`.

Después de actualizar los lanzadores, vuelve a ejecutar `scripts/crear_accesos.ps1` o `CrearAccesoDirecto.vbs` para disponer del nuevo acceso de parada. El registro de procesos se genera localmente y no se distribuye por GitHub.

Los lanzadores antiguos se han retirado. Para iniciar los tres servicios utiliza el acceso «Rehabilitacion - Servidor» o los comandos manuales indicados anteriormente.

## 9. Configuración y seguridad operativa

| Elemento | Ubicación o comportamiento |
|---|---|
| Credenciales PostgreSQL | `configuracion/.env.api`, solo en el servidor. |
| URL de API | Variable de entorno o `.streamlit/secrets.toml`; por defecto localhost. |
| Claves de Caddy | `datos/https`, privadas. |
| Certificado para usuarios | Copia pública exportada en `recursos/`. |
| Contraseñas | Hash PBKDF2; no se recupera la contraseña original. |
| Tokens | Hash en base de datos y credencial temporal en la sesión de Streamlit. |
| Permisos | Comprobación en cada operación protegida de la API. |
| Secretos en disco | Archivos de texto protegidos por permisos; `.gitignore` no los cifra. |

Configura permisos de Windows, copias y conservación de registros según la instalación. No existe en el proyecto una programación automática de copias ni una garantía de restauración. Debe comprobarse la copia y restauración de PostgreSQL y protegerse la autoridad de certificados.

La generación de IA, tanto en demostración como en modo clínico, está reservada al rol MEDICO y a la profesión Médico rehabilitador. Este usuario puede revisar los resúmenes de los tratamientos de cualquier paciente, sin asignación previa. Las demás consultas clínicas verifican la asignación al tratamiento para el rol CLINICO. El médico puede consultar cualquier paciente y el administrador accede a la gestión, pero no a notas ni informes clínicos. Los filtros se aplican en la API y en las consultas SQL antes de paginar, incluidos los accesos directos por identificador. La reasignación cambia qué clínico puede consultar el tratamiento. Antes del despliegue asistencial, el centro debe evaluar si el acceso global médico y la distribución de permisos son adecuados a su organización.

El control de intentos comparte contador por usuario y por dirección vista por la API. En esta arquitectura, las peticiones vienen de Streamlit por localhost, por lo que el límite por IP puede agrupar a varios usuarios. No se interpreta como un bloqueo individual por IP de cada navegador.

### 9.1. Requisitos del centro antes de utilizar datos reales

1. **Finalidad y responsables.** Documenta quién es el responsable del tratamiento, qué profesionales pueden usar la función, qué informes se procesan y para qué se emplea el borrador. Involucra al delegado de protección de datos y a los responsables clínicos y técnicos del centro. Mantén documentados los destinatarios y el flujo entre navegador, servidor, Ollama y PostgreSQL. [RGPD, artículos 5, 24 y 30](https://eur-lex.europa.eu/eli/reg/2016/679/oj/spa)
2. **Legitimación e información al paciente.** Identifica una base del artículo 6 y una excepción del artículo 9 aplicables al uso concreto. Para la vía implementada, el centro debe determinar si puede usar consentimiento explícito, garantizar que sea libre, específico, informado y demostrable, e informar sobre la finalidad, el responsable, la conservación, los derechos y el modo de retirarlo. La retirada debe ser tan sencilla como otorgarlo. Conserva el documento acreditativo y su referencia. La aceptación simulada del TFG carece de valor para este flujo. [RGPD, artículos 4.11, 6, 7, 9 y 13](https://eur-lex.europa.eu/eli/reg/2016/679/oj/spa)
3. **Evaluación de impacto.** Antes de comenzar, documenta el análisis de riesgos y determina si corresponde una evaluación de impacto relativa a la protección de datos (EIPD). Es obligatoria si el tratamiento probablemente entraña un alto riesgo, incluido el tratamiento a gran escala de datos de salud. Si la EIPD deja un alto riesgo que el centro no puede mitigar, procede la consulta previa a la autoridad de control. [RGPD, artículos 35 y 36](https://eur-lex.europa.eu/eli/reg/2016/679/oj/spa) · [Criterios de la AEPD para la EIPD](https://www.aepd.es/documento/listas-dpia-es-35-4.pdf)
4. **Seguridad y conservación.** Limita accesos al personal autorizado, protege las comunicaciones con el navegador y PostgreSQL, y aplica medidas proporcionadas para servidor, almacenamiento, credenciales, registros y copias. Define plazos de conservación y procedimientos de restauración, incidentes y ejercicio de derechos. Si un proveedor externo aloja PostgreSQL o accede a datos por cuenta del centro, revisa sus garantías, el contrato de encargo y, cuando proceda, las transferencias internacionales. El acceso a la historia clínica debe respetar las reglas del centro y el deber de secreto. [RGPD, artículos 25, 28, 32 a 34 y 44 a 49](https://eur-lex.europa.eu/eli/reg/2016/679/oj/spa) · [Ley 41/2002, artículos 16 y 17](https://www.boe.es/buscar/act.php?id=BOE-A-2002-22188#a16)
5. **Validación y revisión profesional.** El centro debe evaluar el modelo y su configuración con informes representativos antes de la puesta en marcha. Comprueba omisiones relevantes, afirmaciones inventadas, fidelidad de fechas, medidas y negaciones, y correspondencia de las fuentes. Establece criterios de aceptación, forma a los profesionales para revisar el borrador y repite la validación si cambia el modelo, sus instrucciones o el flujo de uso. Documenta cómo suspender la función y revisar los incidentes. [Reglamento de IA, artículo 4](https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX%3A02024R1689-20260727)
6. **Clasificación sanitaria y de IA.** Evalúa la finalidad prevista con el responsable regulatorio. Si el software se destina a aportar información para decisiones diagnósticas o terapéuticas y se califica como producto sanitario, aplica la regla 11 y determina la clase y el procedimiento de conformidad. Evalúa también el artículo 6 del Reglamento de IA y las obligaciones aplicables según la clasificación y el calendario vigente. La revisión humana forma parte del flujo, pero la clasificación depende de la finalidad y de las funciones reales. [Reglamento de productos sanitarios, artículo 2 y anexo VIII, regla 11](https://eur-lex.europa.eu/eli/reg/2017/745/2026-07-19/spa/pdf) · [Reglamento de IA, artículo 6](https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX%3A02024R1689-20260727)

### 9.2. Posición regulatoria del código revisado

La revisión del 18 de noviembre de 2026 identifica una plataforma mixta. La gestión de solicitudes, catálogos e historiales tiene argumentos para considerarse administrativa o documental, pero el seguimiento hace más que almacenar notas. `get_clinical_followup_summary()` calcula una tendencia de EVA y señales de posible abandono y estancamiento. `format_clinical_followup_report()` recomienda revisar el plan terapéutico ante esa última señal. Estas funciones no dependen de Ollama: desactivar la IA no las elimina.

En el modo clínico, Ollama clasifica fragmentos y el servidor reconstruye el resumen con referencias a las fuentes. Esto limita la redacción libre, pero conserva una selección de información para pacientes individuales. No debe darse por probado que el módulo está excluido de la normativa sanitaria por llamarlo resumen o por exigir revisión médica. El encuadre recomendado es **prototipo con funciones clínicas candidatas a software producto sanitario**. La clase IIa es una hipótesis para un alcance no urgente delimitado, pendiente de concretar población, decisiones apoyadas, riesgos y clasificación. No es un dictamen oficial. [MDCG 2019-11, revisión de 2025](https://health.ec.europa.eu/system/files/2025-06/mdcg_2019_11_en.pdf) · [MDCG 2021-24, revisión de 2026](https://health.ec.europa.eu/document/download/cbb19821-a517-4e13-bf87-fdc6ddd1782e_en)

La autorización del hospital no sustituye la evaluación regulatoria ni los requisitos aplicables a la puesta en servicio. Tampoco lo hacen los resultados favorables de los 50 casos ficticios. No se ha identificado en la documentación revisada un expediente completo de conformidad que acredite la habilitación del producto para soporte diagnóstico. Si se sigue la vía ordinaria de un producto IIa, deberán completarse sus requisitos con intervención de un organismo notificado. La vía de fabricación interna tiene condiciones específicas: no basta con instalar el repositorio y considerarlo automáticamente un producto del hospital. [Requisitos de la AEMPS](https://www.aemps.gob.es/productos-sanitarios/productos-sanitarios/comercializacion-de-productos-sanitarios-en-espana/que-requisitos-deben-cumplir-los-productos-sanitarios/) · [Instrucción de uso interno hospitalario](https://www.aemps.gob.es/productosSanitarios/prodSanitarios/docs/folletos-instrucciones-formularios/Instruccion-procedimiento-comunicacion-fabricacion-ppss-uso-in-house.pdf)

Antes de un uso asistencial, deben delimitarse las funciones y documentarse la decisión regulatoria; la AEMPS publica un procedimiento específico de consulta. La configuración `AI_USE_MODE=clinical` únicamente habilita controles técnicos y no equivale a una autorización legal. [Consulta de cualificación y clasificación](https://www.aemps.gob.es/productos-sanitarios/consultas-relativas-a-la-cualificacion-y-clasificacion-de-productos-sanitarios-y-productos-sanitarios-de-diagnostico-in-vitro/)

## 10. Rutas principales para mantenimiento

| Grupo | Rutas representativas |
|---|---|
| Acceso | `/auth/login`, `/auth/me`, `/auth/logout`, `/auth/change-password`. |
| Inicio de pantalla | `/bootstrap`, `/stats`. |
| Listados | `/tables/{name}` con nombres permitidos y parámetros. |
| Catálogos | `/catalog/specialties`, `/catalog/areas`, `/catalog/professions`. |
| Solicitudes | `/requests`, `/requests/preview`. |
| Tratamientos | `/treatments/assign`, `/{id}/discharge`, `/{id}/sessions`. |
| Seguimiento | `/treatments/{id}/followup` y rutas de indicadores. |
| Consentimiento | GET y PUT `/patients/{nhc}/ai-consent`. En modo clínico, la aceptación en PUT requiere `evidence_reference`. |
| IA | POST `/treatments/{id}/ai-summary`. La confirmación ficticia `synthetic_data_confirmed` se exige en modo `demo`. |
| Administración | `/admin/users`, `/admin/catalog/...`, `/admin/requests/...`, `/admin/treatments/...`, `/admin/visits`. |

Las rutas de tratamiento abreviadas en la tabla conservan el prefijo `/treatments`. Los errores habituales son 401 para sesión inválida, 403 para restricciones de acceso, 422 para entrada no válida, 429 para límites y 503 para indisponibilidad de base de datos u Ollama. Algunas validaciones de negocio se devuelven como 400.

Ejemplo de consulta paginada: `/tables/audit?page=2&page_size=50&patient_id=000001`. El total y las páginas corresponden al NHC filtrado. La paginación conserva las comprobaciones de autorización de cada consulta.

## 11. Actualizaciones y comprobaciones

Antes de actualizar, conserva una copia del código que funciona y una copia de los datos. No sobrescribas secretos ni claves al descargar una versión nueva. Actualiza las dependencias cuando cambien los requirements. Si cambia el esquema, ejecuta la inicialización prevista sin usuarios trabajando y tras comprobar el destino; no existe un historial de migraciones gestionado por una herramienta dedicada.

Después de actualizar, comprueba manualmente con casos ficticios el recorrido de acceso, cambio de contraseña, solicitud, asignación, sesión, seguimiento, alta y auditoría. Verifica que las funciones administrativas solo estén disponibles para el rol autorizado y que desactivar un tratamiento conserve sus sesiones.

En los listados paginados, comprueba Anterior/Siguiente, los tres tamaños y el reinicio de página al cambiar los filtros. Recorre un conjunto estable para confirmar que sus registros sean accesibles sin repeticiones ni omisiones. Verifica también que los informes e indicadores no cambien al pasar de página.

Comprueba también el arranque y la parada desde los accesos del servidor. Antes de detenerlo, avisa a los usuarios conectados. Desde otro equipo, verifica la confianza HTTPS y el acceso mediante la URL de red. Para comprobar la generación con IA, utiliza únicamente casos ficticios con aceptación registrada y revisa la respuesta frente a los informes originales.

## 12. Diagnóstico de incidencias

| Síntoma | Comprobación |
|---|---|
| `ModuleNotFoundError` | Usa el ejecutable explícito de `.venv`; comprueba dependencias en ese entorno. |
| No se encuentra un archivo | Comprueba carpeta actual y nueva estructura `cliente/`, `servidor/` y `configuracion/`. |
| `getaddrinfo failed` al arrancar Streamlit | `--server.address` debe contener solo una dirección válida, sin protocolo ni puerto. |
| DATABASE_URL ausente | Revisa el archivo privado y el argumento `--env-file configuracion/.env.api`. |
| Fallo de contraseña PostgreSQL | Revisa usuario y credenciales de la base, no la contraseña del clínico. |
| API responde, pero falla una consulta | `/health` no ejecuta una comprobación completa de base de datos. Revisa logs y conectividad. |
| Puerto ocupado | Identifica el proceso que escucha antes de detener o reutilizarlo. |
| `ERR_CERT_AUTHORITY_INVALID` | Instala el certificado de la autoridad actual para el usuario del navegador y reinícialo. |
| Error de nombre del certificado | Comprueba que URL e IP del Caddyfile coincidan; si cambia IP, actualiza y recarga Caddy. |
| `ERR_CONNECTION_TIMED_OUT` | Revisa IP activa, cortafuegos, perfil Privado y comunicación entre subredes. |
| IA no genera | Revisa Ollama, modelo, tamaño de entrada y modo configurado. En `demo`, comprueba la aceptación simulada y la confirmación ficticia. En ambos modos utiliza una cuenta de Médico rehabilitador con rol MEDICO. En `clinical`, verifica además el protocolo, la configuración local y el consentimiento vigente; no se exige asignación al tratamiento. |
| IA devuelve 504 | Ollama agotó el tiempo de espera. Revisa la carga del servidor y vuelve a intentarlo con un conjunto de informes que se ajuste al contexto validado. |

Desde el otro equipo, prueba TCP 443 en PowerShell:

```powershell
Test-NetConnection 192.168.1.115 -Port 443
```

Si estás en CMD:

```cmd
powershell -NoProfile -Command "Test-NetConnection 192.168.1.115 -Port 443"
```

Para consultar los procesos que escuchan en el servidor, usa PowerShell:

```powershell
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 443,8000,8501 } | Select-Object LocalAddress,LocalPort,OwningProcess
```

Si cambia la IP, edita Caddyfile y reinicia el proceso correspondiente o recárgalo:

```powershell
.\herramientas\caddy.exe reload --config .\configuracion\Caddyfile --adapter caddyfile
```

Después vuelve a crear y distribuir el enlace de usuario. No compartas salidas de registros que contengan secretos o información identificativa.

## 13. Git y distribución

El repositorio contiene código, requirements, scripts, icono, Caddyfile, README y licencia MIT. No incluye `.venv`, `.idea`, `__pycache__`, secretos, bases locales, ejecutables descargados, claves privadas ni accesos generados. El archivo `licencia` se incluye también en el paquete cliente.

Para los puestos de usuario de esta arquitectura basta con el enlace y el certificado público: no se distribuye el servidor ni su contraseña de PostgreSQL. `scripts/preparar_cliente.py` prepara una carpeta de distribución con el enlace HTTPS, el certificado público y la licencia. Requiere crear antes los accesos y exportar el certificado. No incluye código Python ni configuración del servidor y exige una carpeta de destino nueva.

## 14. Límites conocidos de la versión documentada

- El modo clínico genera borradores descriptivos. Cada centro debe validar su calidad y completar la revisión normativa y operativa del apartado 9.1 antes de utilizarlo con datos reales.
- No hay instalación como servicio de Windows ni arranque automático tras reiniciar el equipo. El acceso de parada solo controla los procesos registrados por el lanzador de esta instalación.
- La paginación cubre los listados clínicos y administrativos descritos en el apartado 5.1. Las altas y modificaciones concurrentes pueden desplazar un registro de una página a otra durante la consulta.
- La frecuencia semanal se establece al asignar, no se filtra como frecuencia solicitada de la lista de espera.
- La corrección de sesiones no tiene una interfaz general de edición y eliminación individual.
- La coordinación entre tratamientos depende de los nombres concretos que reconoce `FISIO_ESPECIALIDADES`; ampliar un catálogo no amplía automáticamente esas reglas.
- El traslado de la aplicación a un hospital requiere revisar permisos por paciente, infraestructura, bases jurídicas, conservación, seguridad y validación con los responsables correspondientes.


### Baja temporal y reasignación de tratamientos

En **Ajustes → Baja temporal de clínicos**, el administrador puede marcar una cuenta de rol CLINICO como de baja o reincorporarla. Es una ausencia temporal: conserva el acceso, el DNI, la contraseña y el historial, pero impide recibir nuevas asignaciones. La columna `users.on_leave` se añade automáticamente al reiniciar la API.

Los tratamientos activos del clínico de baja aparecen en **Reasignar tratamientos por baja**, con búsqueda por NHC y paginación. El administrador elige un tratamiento y un sustituto activo, disponible, de la misma profesión y con la contraseña inicial cambiada. Debe comprobar que puede atender la especialidad, el área y el horario: el catálogo de profesiones no acredita esas competencias ni calcula su capacidad asistencial. Si no hay sustituto, el tratamiento sigue activo y pendiente, sin crear una solicitud nueva ni borrar sesiones.

La reasignación cambia únicamente el DNI, nombre y profesión del responsable del tratamiento. Conserva su identificador, solicitud de origen, fechas iniciales, horario, transporte, metas e informes. El autor de las sesiones anteriores permanece intacto. Reincorporar al clínico no devuelve automáticamente los pacientes ya reasignados.

Las rutas PUT `/admin/users/{id}/leave` y POST `/admin/treatments/{id}/reassign` exigen rol ADMIN. Se bloquean las filas durante las operaciones y se comprueba que el tratamiento no haya cambiado desde que se seleccionó. Un clínico de baja no puede eludir la restricción llamando directamente a la asignación de la API. El cambio de responsable y su auditoría se guardan juntos; si falla la auditoría, se revierte la reasignación.

La auditoría registra `BAJA_CLINICO`, `REINCORPORACION_CLINICO` y `REASIGNACION_TRATAMIENTO`. El último incluye NHC, tratamiento, especialidad, clínico anterior, nuevo clínico, administrador y fecha. La baja no altera los permisos exclusivos del rol Médico para los resúmenes de IA.


### Controles de acceso y transporte incorporados

| Rol | Acceso asistencial | Administración |
|---|---|---|
| CLINICO | Tratamientos actualmente asignados a su DNI, incluidas sus sesiones e historial. Registra sesiones y altas. Los listados y la auditoría se filtran por esa asignación. | Sin gestión de usuarios ni catálogos. |
| MEDICO | Puede consultar los tratamientos de todos los pacientes. Es el único que genera resúmenes de IA, con los controles de consentimiento y modo correspondientes. | No dispone de funciones administrativas. |
| ADMIN | Gestiona solicitudes, usuarios, catálogos, bajas y reasignaciones. No recibe notas clínicas, informes de seguimiento, resúmenes de IA ni comentarios y motivos libres de la auditoría clínica. | Consulta los registros de visitas y de seguridad. |

La lista de espera y los contadores generales de actividad conservan su finalidad operativa. Los indicadores clínicos globales del Dashboard se reservan al médico. La interfaz adapta sus opciones, pero la protección se aplica también cuando se llama directamente a la API. Al cambiar de identidad o de rol se elimina el estado temporal; un rechazo de acceso invalida la caché de la petición y los resultados temporales de IA.

Las consultas individuales se registran en `security_access_log` con DNI, operación, resultado, tratamiento, NHC y fecha con hora. `clinical_visit_log` mantiene además el registro de una visita por DNI, NHC y día. Los rechazos de acceso se registran con una conexión independiente para conservarlos aunque se revierta la operación. No se guardan contraseñas, tokens ni notas en ese registro; las rutas se identifican por su plantilla, sin copiar parámetros libres. Si falla la auditoría de una lectura clínica, la API no entrega los datos. Si falla el registro de un rechazo, mantiene el rechazo y deja un aviso técnico sin información clínica. Son registros de aplicación, no un almacén inmutable frente al propietario de PostgreSQL. El centro debe proteger sus permisos y definir conservación y revisión.

El nuevo registro está en **Registro de visitas → Accesos y rechazos de la API**. Las búsquedas y la paginación no descargan toda la tabla. Los rechazos pueden carecer de NHC cuando la cuenta no estaba autorizada para conocerlo; para verlos, deje vacío ese filtro.

`get_database_url()` aplica verificación TLS a las conexiones que no son de loopback o socket local. Para Supabase se incluye su CA pública en `recursos/supabase_ca.crt`. Se obtuvo del repositorio de descargas HTTPS del proveedor: `https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt`. Su SHA-256 es `700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7`. El certificado es público y no contiene claves privadas. Antes de una instalación, contraste la CA con la que facilita el panel del proyecto. Si el proveedor cambia el certificado raíz, actualice la copia desde una fuente oficial.

Para otra autoridad certificadora, configure `DATABASE_SSLROOTCERT` con la ruta absoluta a su certificado PEM, o indique `sslrootcert` en la conexión. Para otros servidores remotos se usa por defecto el almacén de confianza `system` de libpq. Un fallo de verificación impide conectar: no se reduce automáticamente a `require` ni se desactiva la comprobación. Para PostgreSQL exclusivamente local se mantiene la configuración explícita del administrador.

Caddy conserva HTTPS con la autoridad local e incorpora protección frente a inclusión en marcos, detección de tipos de contenido y envío de referencias. Las respuestas dinámicas llevan `Cache-Control: no-store`; los archivos estáticos mantienen su caché. La API también marca sus respuestas como no almacenables. El arranque conserva API y Streamlit en `127.0.0.1` y activa expresamente los controles CORS y XSRF de Streamlit. No se expone la API a otros equipos ni se cambia la autoridad de certificados ya instalada.

Al reiniciar la API se crea la tabla de seguridad. La auditoría general admite NHC vacío para las bajas y reincorporaciones del personal, que no pertenecen a un paciente concreto; las operaciones asistenciales siguen registrando su NHC. Reinicie API, Streamlit y Caddy tras actualizar. Las pruebas verifican estos comportamientos, pero no sustituyen una auditoría independiente, el análisis de riesgos del centro ni la evaluación regulatoria del módulo clínico.

Referencias técnicas: [TLS de PostgreSQL](https://www.postgresql.org/docs/current/libpq-ssl.html), [SSL de Supabase](https://supabase.com/docs/guides/platform/ssl-enforcement) y [cabeceras de Caddy](https://caddyserver.com/docs/caddyfile/directives/header).
