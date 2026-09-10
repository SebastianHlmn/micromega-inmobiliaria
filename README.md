# Micromega Inmobiliaria · V0

Prototipo ejecutable de un chatbot inmobiliario en el que WhatsApp es un canal, no el sistema completo. El motor guarda conversaciones y transforma parte de lo conversado en datos estructurados reutilizables.

## Qué incluye esta V0

- API FastAPI.
- Base de datos SQLAlchemy; arranca con SQLite para que la demo funcione sin instalar nada extra y puede cambiar a PostgreSQL.
- 15 propiedades ficticias de prueba.
- Simulador de mensajes.
- Extracción inicial de operación, barrios, ambientes, presupuesto, moneda, mascotas y mes de mudanza.
- Búsqueda de propiedades compatibles.
- Registro de contactos, conversaciones, mensajes, perfiles de búsqueda e intereses.
- Derivación a humano por palabra clave.
- Panel Streamlit con simulador, propiedades y leads.
- Endpoint oficial de webhook preparado para WhatsApp Cloud API.
- Validación opcional de firma de Meta.
- Envío de respuestas por WhatsApp al completar credenciales.
- Capa LLM opcional. El modo `mock` funciona sin clave y no inventa información.
- Docker Compose para PostgreSQL.

## Arranque rápido en Windows

Requisitos: Python 3.11 o 3.12. Docker es opcional en esta primera prueba.

1. Descomprimir el proyecto.
2. Abrir CMD o PowerShell dentro de la carpeta.
3. Ejecutar:

```bat
scripts\setup_windows.bat
```

4. Abrir una terminal y ejecutar:

```bat
scripts\run_api.bat
```

5. Abrir otra terminal y ejecutar:

```bat
scripts\run_panel.bat
```

6. Abrir `http://127.0.0.1:8501`.

La documentación técnica de la API queda en `http://127.0.0.1:8000/docs`.

## Prueba sugerida

Enviar desde el simulador:

> Busco alquilar 2 o 3 ambientes en Caballito hasta 800 mil. Tengo un perro y me mudo en octubre.

El motor debería devolver propiedades compatibles y guardar un perfil estructurado del cliente.

También se puede probar una propiedad específica:

> ¿Sigue disponible MM-002? Tengo perro.

Y la derivación humana:

> Quiero hablar con un humano.

## Pasar de SQLite a PostgreSQL

La V0 arranca deliberadamente con SQLite para poder probarla en minutos. El stack previsto es PostgreSQL. Si Docker está instalado:

```bat
scripts\use_postgres_windows.bat
```

Luego editar `.env` y usar:

```text
DATABASE_URL=postgresql+psycopg://micromega:micromega@localhost:5432/micromega
```

Reiniciar la API y ejecutar:

```bat
python -m app.seed
```

## Conectar un LLM

Por defecto:

```text
LLM_PROVIDER=mock
```

Eso deja que toda la lógica se pruebe sin API externa. Para activar OpenAI, completar en `.env`:

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=...
```

La capa LLM sólo reescribe un borrador construido con datos obtenidos por el sistema. No es la fuente de verdad de precio, disponibilidad, expensas o condiciones.

## Conectar WhatsApp real

El endpoint preparado es:

```text
GET/POST /webhooks/whatsapp
```

Al configurar Meta habrá que completar `.env` con:

- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_GRAPH_API_VERSION`
- `META_APP_SECRET`

El servidor deberá ser accesible públicamente por HTTPS para que Meta pueda entregar webhooks. Durante desarrollo se puede exponer el puerto 8000 con un túnel HTTPS. La conexión real se hace después de validar primero el motor con el simulador.

## Qué NO hace todavía

Esta V0 no pretende ser todavía un CRM inmobiliario completo. Faltan, entre otras cosas: agenda real de visitas, ingesta de publicaciones existentes, audios e imágenes, portal del corredor, reglas de seguimiento, plantillas de WhatsApp, métricas, matching avanzado y una interfaz final de producción.

La siguiente etapa razonable es reemplazar las propiedades ficticias por la fuente real de la inmobiliaria y definir el flujo comercial real antes de automatizar más cosas.
