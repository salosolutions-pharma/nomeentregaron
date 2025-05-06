import re
import time
import logging
import base64
import requests
from typing import Dict, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from config import (
    ConversationSteps, 
    WELCOME_MESSAGE, 
    MENSAJE_CONSENTIMIENTO,
    MENSAJE_FORMULA_MAL_LEIDA,
    MENSAJE_FORMULA_PERDIDA,
    MENSAJE_SOLICITUD_FORMULA
)
from core.session_manager import get_user_session, reset_session, actualizar_datos_contexto, iniciar_nueva_queja
from services.openai_service import OpenAIService
from core.prompt_generator import SystemPromptGenerator
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
        user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_FORMULA
        
        await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        help_text = (
            "Puedo ayudarte a radicar quejas cuando no te entregan medicamentos en tu EPS. "
            "Aquí hay algunos comandos útiles:\n\n"
            "/start - Iniciar una nueva conversación\n"
            "/reset - Reiniciar el proceso actual\n"
            "/help - Mostrar esta ayuda\n\n"
            "Para comenzar, simplemente envíame una foto de tu fórmula médica o escribe cualquier mensaje. 📋📸"
        )
        await update.message.reply_text(help_text)
    
    async def reset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = str(update.effective_user.id)
        user_session = get_user_session(user_id)
        
        reset_session(user_session)
        
        await update.message.reply_text("He reiniciado nuestra conversación. ¿En qué puedo ayudarte ahora? 🔄")
    
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

            # Check if this is the first interaction - greeting needed
            if not user_session["data"].get("has_greeted", False):
                logger.info("Primera interacción detectada - enviando saludo inicial")
                user_session["data"]["has_greeted"] = True
                user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_FORMULA
                
                # Send welcome message first
                await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")
                
                # Add greeting to conversation history
                user_session["data"]["conversation_history"].append({
                    "role": "assistant",
                    "content": WELCOME_MESSAGE
                })
                
                # Small delay to ensure messages appear in correct order
                import asyncio
                await asyncio.sleep(1)

            user_session["data"]["last_processed_time"] = current_time
            user_session["data"]["last_photo_id"] = current_photo_id

            user_session["data"]["conversation_history"].append({
                "role": "user",
                "content": "[Imagen de fórmula médica]"
            })

            # Manejar el caso de una queja completada
            envia_imagen_despues_de_completar = user_session["data"]["current_step"] == ConversationSteps.COMPLETADO

            if envia_imagen_despues_de_completar:
                # Guardar los datos de la queja completada si no están guardados
                if user_session["data"].get("formula_data") and not user_session["data"]["queja_actual"]["guardada"]:
                    await self.bigquery_service.save_user_data(user_session["data"], True)

                # Usar la nueva función para iniciar una nueva queja
                iniciar_nueva_queja(user_session, user_id)

            # Procesamiento estándar de la imagen
            user_session["data"]["awaiting_approval"] = True
            user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_CONSENTIMIENTO

            try:
                base64_image = await self.download_telegram_photo(update, context)
                formula_result = await self.image_processor.process_medical_formula(base64_image)
                user_session["data"]["pending_media"] = formula_result
                
                # Mensaje de consentimiento sin saludos redundantes
                mensaje_consentimiento = "Para leer tu fórmula y ayudarte, necesito tu autorización. ¿Me autorizas a procesar tus datos para tramitar la queja? (Responde sí o no) 📝"
                
                user_session["data"]["conversation_history"].append({
                    "role": "assistant",
                    "content": mensaje_consentimiento
                })
                
                await update.message.reply_text(mensaje_consentimiento)
                
            except Exception as e:
                logger.error(f"Error procesando la imagen: {e}")
                await update.message.reply_text(MENSAJE_FORMULA_MAL_LEIDA)
            
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

        # Solo guardamos información del usuario de Telegram temporalmente (no para uso en la conversación)
        if update.effective_user.username:
            user_session["data"]["username"] = update.effective_user.username

        try:
            # Primer mensaje - Mostrar saludo inicial si no se ha mostrado antes
            if not user_session["data"].get("has_greeted", False):
                user_session["data"]["has_greeted"] = True
                user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_FORMULA
                user_session["data"]["conversation_history"].append({
                    "role": "assistant",
                    "content": WELCOME_MESSAGE
                })
                await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")
                return
                
            # Manejar comandos básicos
            if text.lower() == '/reset' or 'empezar de nuevo' in text.lower() or 'reiniciar' in text.lower():
                await self.reset_command(update, context)
                return
            
            # Detectar nueva queja
            es_nueva_queja = re.search(r"(nueva queja|otra queja|quiero hacer otra|iniciar otra|tramitar otra|otra .*queja|reportar otro|denunciar otro|otro medicamento no entregado|volver a empezar)", text, re.I)
            if es_nueva_queja:
                # Guardar los datos de la queja actual si no están guardados
                if user_session["data"].get("formula_data") and not user_session["data"]["queja_actual"]["guardada"]:
                    await self.bigquery_service.save_user_data(user_session["data"], True)
                
                # Usar la nueva función para iniciar una nueva queja
                iniciar_nueva_queja(user_session, user_id)

                await update.message.reply_text("¡Claro! 👍 Vamos a tramitar una nueva queja. Por favor, envíame una foto de tu fórmula médica para comenzar. 📋📸")
                return

            # Manejar consentimiento (caso especial)
            if user_session["data"]["awaiting_approval"]:
                respuesta = self.intent_handler.manejar_consentimiento(user_session, text)
                await update.message.reply_text(respuesta)
                return

            # Detectar fórmula perdida (caso especial)
            if re.search(r"(perd[ií] la f[oó]rmula|no tengo la f[oó]rmula|se me perd[ií]|no la tengo|se me dañó|se me mojó|no la encuentro)", text, re.I):
                user_session["data"]["conversation_history"].append({"role": "assistant", "content": MENSAJE_FORMULA_PERDIDA})
                await update.message.reply_text(MENSAJE_FORMULA_PERDIDA)
                return
                
            # Detectar consultas de historial
            if re.search(r"(historial|quejas anteriores|quejas previas|consultar|anteriormente)", text, re.I):
                # Si tenemos una fórmula procesada, intentar consultar el historial
                if user_session["data"].get("formula_data"):
                    historial = await self.intent_handler.consultar_historial_paciente(user_session)
                    user_session["data"]["conversation_history"].append({
                        "role": "assistant",
                        "content": historial
                    })
                    await update.message.reply_text(historial)
                    return

            # Solicitud de fórmula inicial (caso especial)
            if (not user_session["data"].get("formula_data") and 
                not user_session["data"].get("pending_media") and 
                (user_session["data"]["current_step"] == ConversationSteps.INICIO or 
                user_session["data"]["current_step"] == ConversationSteps.ESPERANDO_FORMULA)):

                if len(text) > 3 and '/' not in text and '?' not in text and '¿' not in text:
                    await update.message.reply_text(MENSAJE_SOLICITUD_FORMULA)
                    return

            # Para todos los demás mensajes, utilizamos el enfoque conversacional
            respuesta = await self.intent_handler.procesar_mensaje(text, user_session)
            await update.message.reply_text(respuesta)
            
            # Si la conversación ha sido completada y tenemos todos los datos, guardamos en BigQuery
            if (user_session["data"]["current_step"] == ConversationSteps.COMPLETADO and 
                    not user_session["data"]["queja_actual"].get("guardada", False)):
                logger.info("Guardando datos en BigQuery...")
                await self.bigquery_service.save_user_data(user_session["data"], True)
                user_session["data"]["queja_actual"]["guardada"] = True
            
        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await update.message.reply_text("Disculpa, ocurrió un error inesperado. Por favor, intenta nuevamente o escribe /reset para reiniciar la conversación. 🔄")