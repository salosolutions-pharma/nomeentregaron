import re
import time
import logging
import base64
import requests
from typing import Dict, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from config import WELCOME_MESSAGE
from core.session_manager import get_user_session, reset_session, iniciar_nueva_queja
from services.openai_service import OpenAIService
from services.image_processor import ImageProcessor
from services.bigquery_service import BigQueryService
from handlers.intent_handler import IntentHandler

logger = logging.getLogger(__name__)

class TelegramHandler:
    def __init__(self, telegram_token: str, openai_service: OpenAIService, image_processor: ImageProcessor, bigquery_service: BigQueryService):
        self.telegram_token = telegram_token
        self.openai_service = openai_service
        self.image_processor = image_processor
        self.bigquery_service = bigquery_service
        self.intent_handler = IntentHandler(openai_service)
        
    def setup_telegram_bot(self) -> Application:
        application = Application.builder().token(self.telegram_token).build()
        
        # Configurar la eliminación del webhook para que se ejecute durante la inicialización
        async def post_init(application: Application) -> None:
            await application.bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook eliminado correctamente")
        
        application.post_init = post_init
        
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("reset", self.reset_command))

        application.add_handler(MessageHandler(filters.PHOTO, self.process_photo_message))
        
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_text_message))
        
        async def error_handler(update, context):
            logger.error(f"Error en el bot: {context.error}")

        application.add_error_handler(error_handler)
        
        return application
    
    async def download_telegram_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
        try:
            file_id = update.message.photo[-1].file_id
            photo_file = await context.bot.get_file(file_id)
            
            response = requests.get(photo_file.file_path)
            if response.status_code != 200:
                raise Exception(f"Error descargando foto: {response.status_code}")
                
            base64_image = base64.b64encode(response.content).decode('utf-8')
            return base64_image
            
        except Exception as e:
            logger.error(f"Error descargando foto de Telegram: {e}")
            raise
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = str(update.effective_user.id)
        user_session = get_user_session(user_id)
        
        user_session["data"]["has_greeted"] = True
        user_session["data"]["is_first_interaction"] = False
        
        await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")
        
        # Add the greeting to the conversation history
        user_session["data"]["conversation_history"].append({
            "role": "assistant", 
            "content": WELCOME_MESSAGE
        })
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = str(update.effective_user.id)
        user_session = get_user_session(user_id)
        
        # Add help request to conversation history
        user_session["data"]["conversation_history"].append({
            "role": "user", 
            "content": "/help - Solicitar ayuda sobre el uso del bot"
        })
        
        # Let the AI generate a help response
        response = await self.openai_service.ask_openai(user_session)
        await update.message.reply_text(response)
    
    async def reset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = str(update.effective_user.id)
        user_session = get_user_session(user_id)
        
        reset_session(user_session)
        
        # Add reset notification to conversation history
        user_session["data"]["conversation_history"].append({
            "role": "user", 
            "content": "/reset - Reiniciar la conversación"
        })
        
        # Let the AI generate a reset confirmation
        response = await self.openai_service.ask_openai(user_session)
        await update.message.reply_text(response)
    
    async def process_photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = str(update.effective_user.id)
        user_session = get_user_session(user_id)

        try:
            current_time = time.time()

            # Evitar procesar imágenes duplicadas
            if (user_session["data"].get("last_processed_time") and 
                    (current_time - user_session["data"]["last_processed_time"] < 2.5)):
                logger.info("Ignorando imagen duplicada")
                return

            last_photo_id = user_session["data"].get("last_photo_id")
            current_photo_id = update.message.photo[-1].file_unique_id
            
            if (last_photo_id == current_photo_id):
                logger.info("Ignorando imagen duplicada exacta")
                return

            user_session["data"]["last_processed_time"] = current_time
            user_session["data"]["last_photo_id"] = current_photo_id

            # Detectar si es una nueva queja después de completar una anterior
            if user_session["data"].get("process_completed", False):
                # Si la queja anterior no se guardó, hacerlo ahora
                if not user_session["data"]["queja_actual"].get("guardada", False):
                    logger.info("Guardando queja completada antes de iniciar una nueva")
                    await self.bigquery_service.save_user_data(user_session["data"], True)
                
                iniciar_nueva_queja(user_session, user_id)

            try:
                # Download and process the formula image
                base64_image = await self.download_telegram_photo(update, context)
                formula_result = await self.image_processor.process_medical_formula(base64_image)
                
                # Process the formula using the AI-driven approach
                response = await self.intent_handler.manejar_imagen_formula(formula_result, user_session)
                await update.message.reply_text(response)
                
            except Exception as e:
                logger.error(f"Error procesando la imagen: {e}")
                
                # Add error notification to conversation history
                user_session["data"]["conversation_history"].append({
                    "role": "user", 
                    "content": "[Error procesando imagen de fórmula médica]"
                })
                
                # Let the AI generate an error response
                response = await self.openai_service.ask_openai(user_session)
                await update.message.reply_text(response)
            
        except Exception as e:
            logger.error(f"Error general en process_photo_message: {e}")
            await update.message.reply_text("Lo siento, tuve un problema al procesar tu imagen. ¿Podrías intentar enviarla de nuevo o con mejor iluminación? 📸✨")
    
    async def process_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
       
        text = update.message.text or ''
        user_id = str(update.effective_user.id)
        user_session = get_user_session(user_id)

        # Evitar procesar mensajes duplicados
        current_time = time.time()
        if (user_session["data"].get("last_processed_time") and 
                (current_time - user_session["data"]["last_processed_time"] < 0.5) and
                user_session["data"].get("last_message") == text):
            logger.info("Ignorando mensaje duplicado")
            return
        
        user_session["data"]["last_processed_time"] = current_time
        user_session["data"]["last_message"] = text

        # Solo guardamos información del usuario de Telegram temporalmente
        if update.effective_user.username:
            user_session["data"]["username"] = update.effective_user.username

        try:
            # Detectar comandos simples en texto
            if text.lower() == '/reset' or 'empezar de nuevo' in text.lower() or 'reiniciar' in text.lower():
                await self.reset_command(update, context)
                return
            
            # Detectar nueva queja
            es_nueva_queja = re.search(r"(nueva queja|otra queja|quiero hacer otra|iniciar otra|tramitar otra|otra .*queja|reportar otro|denunciar otro|otro medicamento no entregado|volver a empezar)", text, re.I)
            if es_nueva_queja and user_session["data"].get("formula_data"):
                # Guardar queja actual si corresponde
                if not user_session["data"]["queja_actual"].get("guardada", False):
                    logger.info("Iniciando nueva queja - Guardando queja actual primero")
                    await self.bigquery_service.save_user_data(user_session["data"], True)
                
                # Iniciar nueva queja
                iniciar_nueva_queja(user_session, user_id)
                
                # Add new complaint request to conversation history
                user_session["data"]["conversation_history"].append({
                    "role": "user", 
                    "content": text
                })
                
                # Let the AI generate a response for new complaint request
                response = await self.openai_service.ask_openai(user_session)
                await update.message.reply_text(response)
                return
            
            # Procesar el mensaje con el enfoque basado en IA
            response = await self.intent_handler.procesar_mensaje(text, user_session)
            await update.message.reply_text(response)
            
            # Verificar si el proceso está completo para guardar datos
            self.intent_handler._verificar_informacion_completa(user_session)
            
            # Si la conversación ha sido completada, guardar en BigQuery
            if user_session["data"].get("process_completed", False):
                if not user_session["data"]["queja_actual"].get("guardada", False):
                    logger.info("✅ Proceso completado detectado - Guardando datos en BigQuery...")
                    
                    # Asegurarse de que todos los campos requeridos estén presentes
                    if not user_session["data"].get("residence_address"):
                        user_session["data"]["residence_address"] = "No proporcionada"
                    
                    success = await self.bigquery_service.save_user_data(user_session["data"], True)
                    
                    if success:
                        user_session["data"]["queja_actual"]["guardada"] = True
                        logger.info("✅ Datos guardados exitosamente en BigQuery")
                    else:
                        logger.error("❌ Error al guardar datos en BigQuery")
                else:
                    logger.info("Proceso completado, pero los datos ya fueron guardados previamente")
            
            # Si es un mensaje de despedida, intentar guardar aunque no se haya detectado como completado
            es_despedida = re.search(r"(gracias|adios|chao|hasta luego|muchas gracias|listo)", text.lower())
            if es_despedida and self._tiene_informacion_suficiente(user_session["data"]):
                if not user_session["data"]["queja_actual"].get("guardada", False):
                    logger.info("Mensaje de despedida detectado - Forzando guardado final")
                    user_session["data"]["process_completed"] = True
                    
                    # Añadir valores por defecto para campos faltantes
                    if not user_session["data"].get("residence_address"):
                        user_session["data"]["residence_address"] = "No proporcionada"
                    
                    if not user_session["data"].get("affiliation_regime"):
                        user_session["data"]["affiliation_regime"] = "No especificado"
                    
                    success = await self.bigquery_service.save_user_data(user_session["data"], True)
                    if success:
                        user_session["data"]["queja_actual"]["guardada"] = True
                        logger.info("✅ Datos guardados exitosamente en BigQuery por mensaje de despedida")
                    else:
                        logger.error("❌ Error al guardar datos en BigQuery por mensaje de despedida")
        
        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await update.message.reply_text("Disculpa, ocurrió un error inesperado. Por favor, intenta nuevamente o escribe /reset para reiniciar la conversación. 🔄")
    
    def _tiene_informacion_suficiente(self, data: Dict[str, Any]) -> bool:
        """Verifica si hay suficiente información para guardar la queja"""
        return (data.get("formula_data") and 
                data.get("missing_meds") and 
                data.get("city") and
                data.get("cellphone"))