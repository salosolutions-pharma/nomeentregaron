# No Me Entregaron

Bot para gestionar quejas cuando las EPS no entregan medicamentos a los pacientes.

## Descripción

Este proyecto implementa un bot que permite a los usuarios:

1. Enviar una foto de su fórmula médica
2. Indicar qué medicamentos no fueron entregados
3. Proporcionar datos adicionales necesarios para la queja
4. Recibir confirmación de que su queja será tramitada

El bot utiliza OpenAI para analizar las fórmulas médicas y mantener conversaciones naturales con los usuarios.

## Requisitos

- Python 3.8+
- Cuenta en Telegram
- Cuenta en OpenAI
- Acceso a Google BigQuery

## Estructura del Proyecto

```
python_nomeentregaron/
├── src/
│   ├── main.py             # Punto de entrada principal
│   ├── handler.py # Manejo
│   └── processor.py # Procesamiento
├── requirements.txt        # Dependencias
├── .env                    # Variables de entorno
├── .gitignore              # Archivos a ignorar en Git
└── README.md               # Documentación
```

## Instalación

1. Clone el repositorio:
   ```bash
   git clone https://github.com/salosolutions-pharma/nomeentregaron.git
   cd python_nomeentregaron
   ```

2. Instale las dependencias:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure las variables de entorno en el archivo `.env`:
   ```bash
   TELEGRAM_TOKEN=your_telegram_token
   OPENAI_API_KEY=your_openai_api_key
   BIGQUERY_PROJECT_ID=your_bigquery_project_id
   BIGQUERY_DATASET_ID=solutions2pharma_data
   BIGQUERY_TABLE_ID=quejas
   ```

## Uso

Para iniciar el bot:

```bash
python src/main.py
```

## Flujo de Conversación

El bot sigue el siguiente flujo:

1. Solicita foto de la fórmula médica
2. Pide consentimiento para procesar los datos
3. Analiza la fórmula y muestra los medicamentos detectados
4. Pregunta cuáles medicamentos no fueron entregados
5. Recopila datos adicionales (ciudad, celular, fecha de nacimiento, régimen, dirección, farmacia)
6. Almacena la queja en BigQuery
7. Confirma al usuario que la queja será tramitada

## Características Principales

- Análisis automático de fórmulas médicas mediante OpenAI Vision
- Conversación natural y empática
- Procesamiento de fechas en diferentes formatos
- Detección inteligente de correcciones de datos
- Almacenamiento seguro en Google BigQuery

## Contribuir

Las contribuciones son bienvenidas. Para contribuir:

1. Haga fork del repositorio
2. Cree una rama para su característica (`git checkout -b feature/nueva-caracteristica`)
3. Haga commit de sus cambios (`git commit -m 'Añadir nueva característica'`)
4. Empuje a la rama (`git push origin feature/nueva-caracteristica`)
5. Abra un Pull Request

## Licencia

[MIT](LICENSE)