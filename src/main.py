import os
import logging
from dotenv import load_dotenv
from src.handlers.telegram_handler import TelegramHandler
from src.services.openai_service import OpenAIService
from src.services.image_processor import ImageProcessor
from src.services.bigquery_service import BigQueryService
from src.config import get_api_config

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():

    load_dotenv()
    
    config = get_api_config()
    
    telegram_token = config.get('telegram_token')
    if not telegram_token:
        logger.error("Error: No se encontró el token de Telegram en las variables de entorno")
        return
        
    openai_api_key = config.get('openai_api_key')
    if not openai_api_key:
        logger.error("Error: No se encontró la API key de OpenAI en las variables de entorno")
        return
    
    bigquery_project_id = config.get('bigquery_project_id')
    if not bigquery_project_id:
        logger.error("Error: No se encontró el ID del proyecto de BigQuery en las variables de entorno")
        return

    logger.info("Inicializando servicios...")
    openai_service = OpenAIService(openai_api_key)
    image_processor = ImageProcessor(openai_api_key)
    bigquery_service = BigQueryService(
        bigquery_project_id,
        config.get('bigquery_dataset_id'),
        config.get('bigquery_table_id')
    )

    logger.info("Iniciando el bot de No Me Entregaron...")
    telegram_handler = TelegramHandler(
        telegram_token, 
        openai_service, 
        image_processor, 
        bigquery_service
    )
    
    bot = telegram_handler.setup_telegram_bot()

    logger.info("Bot iniciado correctamente!")
    bot.run_polling(allowed_updates=['message'])

if __name__ == "__main__":
    main()