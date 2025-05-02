import os
import logging
import sys
import fcntl
from dotenv import load_dotenv
from handlers.telegram_handler import TelegramHandler
from services.openai_service import OpenAIService
from services.image_processor import ImageProcessor
from services.bigquery_service import BigQueryService
from config import get_api_config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():

    lock_file = open('/tmp/nomeentregaron_bot.lock', 'w')
    
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        logger.info("Bloqueo adquirido, procediendo con el inicio del bot")
        
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
        
        bot.run_polling(allowed_updates=['message'], drop_pending_updates=True)

    except IOError:
        logger.error("No se puede adquirir el bloqueo. Otra instancia está en ejecución. Saliendo.")
        sys.exit(1)

if __name__ == "__main__":
    main()