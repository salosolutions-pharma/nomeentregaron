import os
import logging
import asyncio
from dotenv import load_dotenv

from config import get_api_config
from services.openai_service import OpenAIService
from services.image_processor import ImageProcessor
from services.bigquery_service import BigQueryService
from handlers.telegram_handler import TelegramHandler

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def main():
    # Cargar variables de entorno
    load_dotenv()
    
    # Obtener configuración
    config = get_api_config()
    
    # Inicializar servicios
    openai_service = OpenAIService(api_key=config['openai_api_key'])
    image_processor = ImageProcessor(api_key=config['openai_api_key'])
    bigquery_service = BigQueryService(
        project_id=config['bigquery_project_id'],
        dataset_id=config['bigquery_dataset_id'],
        table_id=config['bigquery_table_id'],
        credentials_path=config['google_credentials_path']
    )
    
    # Inicializar el manejador de Telegram
    telegram_handler = TelegramHandler(
        telegram_token=config['telegram_token'],
        openai_service=openai_service,
        image_processor=image_processor,
        bigquery_service=bigquery_service
    )
    
    # Configurar y arrancar el bot de Telegram
    application = telegram_handler.setup_telegram_bot()
    
    logger.info("Bot inicializado y listo para procesar mensajes")
    
    try:
        # Iniciar el bot
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        logger.info("Bot iniciado correctamente")
        
        # Mantener el bot corriendo indefinidamente
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Deteniendo el bot por interrupción del usuario")
    finally:
        # Detener el bot al finalizar
        await application.stop()
        logger.info("Bot detenido")

if __name__ == "__main__":
    asyncio.run(main())