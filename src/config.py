import os
import logging
from enum import Enum, auto

logger = logging.getLogger(__name__)

class ConversationSteps(Enum):
    INICIO = auto()
    ESPERANDO_FORMULA = auto()
    ESPERANDO_CONSENTIMIENTO = auto()
    FORMULA_ANALIZADA = auto()
    ESPERANDO_MEDICAMENTOS = auto()
    ESPERANDO_CIUDAD = auto()
    ESPERANDO_CELULAR = auto()
    ESPERANDO_FECHA_NACIMIENTO = auto()
    ESPERANDO_REGIMEN = auto()
    ESPERANDO_DIRECCION = auto()
    ESPERANDO_FARMACIA = auto()
    COMPLETADO = auto()

WELCOME_MESSAGE = "¡Hola! 👋 Bienvenido a *No Me Entregaron*. \n\nSoy tu asistente virtual y estoy aquí para ayudarte a radicar quejas cuando no te entregan tus medicamentos en la EPS. 💊\n\nPor favor envíame una foto clara de tu fórmula médica. 📋📸"
MENSAJE_CONSENTIMIENTO = "Para leer tu fórmula y ayudarte, necesito tu autorización. ¿Me autorizas a procesar tus datos para tramitar la queja? (Responde sí o no) 📝"
MENSAJE_FORMULA_MAL_LEIDA = "No pude leer bien la fórmula. 🔍❌ ¿Podrías enviarme una foto más clara por favor? Necesito que la imagen esté bien iluminada y enfocada. 📸✨"
MENSAJE_FORMULA_PERDIDA = "Entiendo que no tienes la fórmula médica en este momento. 📋❓\n\nEstas son algunas opciones que puedes considerar:\n• Solicitar un duplicado directamente en tu EPS 🏥\n• Consultar tu historial médico en la página web de tu EPS (muchas permiten descargar fórmulas anteriores) 💻\n• Contactar a tu médico tratante para que te genere una nueva fórmula 👨‍⚕️\n\n¿Te gustaría más información sobre alguna de estas alternativas? También puedes escribirme cuando tengas la fórmula y te ayudaré con gusto. 🤝"
MENSAJE_SOLICITUD_FORMULA = "Para ayudarte con tu queja, necesito que me envíes una foto clara de tu fórmula médica. 📋📸"

def get_api_config():
    return {
        "telegram_token": os.getenv('TELEGRAM_TOKEN'),
        "openai_api_key": os.getenv('OPENAI_API_KEY'),
        "bigquery_project_id": os.getenv('BIGQUERY_PROJECT_ID'),
        "bigquery_dataset_id": os.getenv('BIGQUERY_DATASET_ID', 'solutions2pharma_data'),
        "bigquery_table_id": os.getenv('BIGQUERY_TABLE_ID', 'quejas'),
        "google_credentials_path": os.getenv('GOOGLE_CREDENTIALS_PATH')
    }