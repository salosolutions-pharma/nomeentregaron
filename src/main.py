import os
import logging
from dotenv import load_dotenv
from handler import setup_telegram_bot

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    load_dotenv()
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    if not telegram_token:
        logger.error("Error: No se encontró el token de Telegram en las variables de entorno")
        return
    
    openai_api_key = os.getenv('OPENAI_API_KEY')
    if not openai_api_key:
        logger.error("Error: No se encontró la API key de OpenAI en las variables de entorno")
        return

    bigquery_project_id = os.getenv('BIGQUERY_PROJECT_ID')
    if not bigquery_project_id:
        logger.error("Error: No se encontró el ID del proyecto de BigQuery en las variables de entorno")
        return
    
    logger.info("Iniciando el bot de No Me Entregaron...")
    
    bot = setup_telegram_bot(telegram_token)
    
    logger.info("Bot iniciado correctamente!")
    bot.run_polling(allowed_updates=['message'])

if __name__ == "__main__":
    main()