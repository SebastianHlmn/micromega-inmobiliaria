# Micromega Inmobiliaria · V0

Prototipo ejecutable de un chatbot inmobiliario en el que WhatsApp es un canal, no el sistema completo. El motor guarda conversaciones y transforma parte de lo conversado en datos estructurados reutilizables.

## Qué incluye esta V0

- API FastAPI.
- Base de datos SQLAlchemy; arranca con SQLite para que la demo funcione sin instalar nada extra y puede cambiar a PostgreSQL.
- 15 propiedades ficticias de prueba.
- Simulador de mensajes.
- Extracción de operación, barrios, ambientes, presupuesto, moneda, mascotas y fecha de mudanza.
- Extracción semántica opcional mediante LLM, con normalización y fallback determinístico si no hay API o si falla el modelo.
- Búsqueda de propiedades compatibles.
- Registro de contactos, conversaciones, mensajes, perfiles de búsqueda e intereses.
- Derivación a humano por palabra clave.
- Panel Streamlit con simulador, propiedades y leads.
- Endpoint oficial de webhook preparado para WhatsApp Cloud API.
- Validación opcional de firma de Meta.
- Envío de respuestas por WhatsApp al completar credenciales.
- Docker Compose para PostgreSQL.

## Arranque rápido en Windows

Requisitos: Python 3.11 o 3.12. Docker es opcional en esta primera prueba.

1. Abrir CMD o PowerShell dentro de la carpeta del proyecto.
2. Ejecutar:

```bat
scripts\setup_windows.bat
```

3. Abrir una terminal y ejecutar:

```bat
scripts\run_api.bat
```

4. Abrir otra terminal y ejecutar:

```bat
scripts\run_panel.bat
```

5. Abrir `http://127.0.0.1:8501`.

La documentación técnica de la API queda en `http://127.0.0.1:8000/docs`.

## Prueba sugerida

Enviar desde el simulador:

> Busco alquilar 2 o 3 ambientes en Caballito hasta 800 mil. Tengo un perro y me mudo en octubre.

El motor debería devolver propiedades compatibles y guardar un perfil estructurado del cliente.

Después, usando el mismo teléfono demo, probar un mensaje de continuidad:

> También me sirve Palermo, pero mejor hasta 750 mil.

Con LLM activado, la extracción interpreta el segundo mensaje en relación con el perfil acumulado y actualiza únicamente los campos que correspondan.

También se puede probar una propiedad específica:

> ¿Sigue disponible MM-002? Tengo perro.

Y la derivación humana:

> Quiero hablar con un humano.

## Extracción semántica y LLM

Por defecto el proyecto funciona sin ninguna API externa:

```text
LLM_PROVIDER=mock
```

En ese modo se utiliza un extractor determinístico simple. Para activar OpenAI, completar `.env`:

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=...
```

Al estar activado, el modelo tiene dos funciones separadas:

1. interpretar el mensaje y devolver actualizaciones estructuradas del perfil de búsqueda;
2. reescribir de forma natural la respuesta que el sistema ya construyó con datos comprobados.

La salida de extracción se valida y normaliza antes de modificar la base. Si la llamada al modelo falla, el sistema vuelve automáticamente al extractor por reglas. En el simulador se muestra la fuente utilizada (`openai`, `rules` o `rules_fallback`) y qué campos fueron detectados específicamente en el último mensaje.

El LLM no es la fuente de verdad de precio, disponibilidad, expensas ni condiciones de una propiedad. Esos datos siempre salen de la base inmobiliaria.

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


## Demo de gestión integrada

La rama `feature/whatsapp-gpt` incorpora un panel de gestión servido por la misma aplicación FastAPI. No requiere Streamlit ni Node para probar la demo.

Con la API levantada:

```bat
scripts\run_api.bat
```

abrir:

```text
http://127.0.0.1:8000/panel
```

El panel incluye:

- **Resumen**: consultas, personas, mensajes recibidos, intereses, pedidos de visita, visitas concertadas y derivaciones a una persona.
- **Embudo comercial**: Nuevo → Calificado → Interesado → Visita solicitada → Visita concertada → Seguimiento → Cerrado/Descartado.
- **Conversaciones**: bandeja por contacto, perfil de búsqueda, categorías detectadas, chat completo, resumen generado con GPT, notas internas y cambio manual de etapa.
- **Categorías**: taxonomía configurable que el clasificador de GPT usa para estructurar las consultas. El usuario puede activar/desactivar categorías y Micromega mantiene la lógica de prompts y comportamiento del agente.
- **Propiedades**: visualización del stock, alta manual y activación/pausa de disponibilidad.
- **Visitas**: pedidos detectados por el agente y confirmación manual de fecha/estado.
- **Exportación**: CSV de conversaciones estructuradas y CSV de mensajes crudos.

### Datos estructurados de las conversaciones

Además de los mensajes se registran:

- categorías de consulta por conversación;
- eventos comerciales (`search_started`, `search_refined`, `property_question`, `interest_registered`, `visit_requested`, `visit_scheduled`, `visit_completed`, `handoff`, etc.);
- etapa del embudo;
- resumen interno;
- notas de seguimiento;
- intereses y visitas;
- perfil de búsqueda acumulado.

Las categorías no están codificadas en el frontend. Se guardan en base y pueden configurarse. El clasificador recibe la taxonomía activa en cada análisis. La fuente de verdad de propiedades, precios, disponibilidad y condiciones sigue siendo la base de datos.

### Agente de WhatsApp

El flujo principal usa OpenAI Responses API con herramientas del sistema:

- `buscar_propiedades`
- `ver_propiedad`
- `registrar_interes`
- `registrar_visita`
- `derivar_a_humano`

GPT lleva la conversación y decide cuándo usar una herramienta. Las acciones reales y los datos de propiedad se ejecutan en Python/SQLAlchemy. Si OpenAI falla, permanece el flujo anterior como respaldo para no cortar el webhook.

### Para probar el circuito completo

1. Levantar FastAPI.
2. Mantener activo el túnel/webhook de WhatsApp.
3. Enviar desde WhatsApp una búsqueda, por ejemplo: `Busco alquilar un 2 ambientes en Caballito hasta 800 mil y tengo un perro`.
4. Preguntar por una propiedad concreta.
5. Pedir una visita.
6. Abrir `/panel`: la conversación debe aparecer con categorías, eventos y etapa comercial.
7. Desde **Visitas**, pasar el pedido a `scheduled` para que cuente como visita concertada.
8. Exportar los CSV desde **Conversaciones**.

Para bases SQLite ya existentes no hace falta borrar datos: al reiniciar FastAPI, SQLAlchemy crea las nuevas tablas de gestión que falten.
