import re
import time
import logging
import base64
import requests
from typing import Dict, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from src.config import (
    ConversationSteps, 
    WELCOME_MESSAGE, 
    MENSAJE_CONSENTIMIENTO,
    MENSAJE_FORMULA_MAL_LEIDA,
    MENSAJE_FORMULA_PERDIDA,
    MENSAJE_SOLICITUD_FORMULA
)
from src.models.user_session import get_user_session, reset_session, actualizar_datos_contexto
from src.services.openai_service import OpenAIService, SystemPromptGenerator
from src.services.image_processor import ImageProcessor
from src.services.bigquery_service import BigQueryService
from src.handlers.intent_handler import IntentHandler

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
        
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("reset", self.reset_command))

        application.add_handler(MessageHandler(filters.PHOTO, self.process_photo_message))
        
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_text_message))

        application.add_error_handler(lambda update, context: logger.error(f"Error en el bot: {context.error}"))
        
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

            if (user_session["data"].get("last_processed_time") and 
                    (current_time - user_session["data"]["last_processed_time"] < 2.5)):
                logger.info("Ignorando imagen duplicada")
                return

            last_photo_id = user_session["data"].get("last_photo_id")
            current_photo_id = update.message.photo[-1].file_unique_id
            
            if (user_session["data"].get("last_processed_time") and 
                    (current_time - user_session["data"]["last_processed_time"] < 2.0) and
                    last_photo_id == current_photo_id):
                logger.info("Ignorando imagen duplicada exacta")
                return

            user_session["data"]["last_processed_time"] = current_time
            user_session["data"]["last_photo_id"] = current_photo_id

            user_session["data"]["conversation_history"].append({
                "role": "user",
                "content": "[Imagen de fórmula médica]"
            })

            if not user_session["data"]["has_greeted"]:
                user_session["data"]["has_greeted"] = True
                user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_CONSENTIMIENTO
                
                nombre_usuario = update.effective_user.first_name or ''
                saludo_personalizado = f"¡Hola {nombre_usuario}! 👋" if nombre_usuario else "¡Hola! 👋"
                
                await update.message.reply_text(
                    f"{saludo_personalizado} Bienvenido a *No Me Entregaron*. "
                    "Estoy analizando tu fórmula médica, dame un momento... 🔍", 
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("Estoy analizando tu fórmula médica, dame un momento... 🔍")
            
            envia_imagen_despues_de_completar = user_session["data"]["current_step"] == ConversationSteps.COMPLETADO

            if envia_imagen_despues_de_completar:
                if user_session["data"].get("formula_data") and not user_session["data"]["queja_actual"]["guardada"]:
                    await self.bigquery_service.save_user_data(user_session["data"], True)

                user_session["data"]["queja_actual"] = {
                    "id": f"{user_id}_{int(time.time())}",
                    "guardada": False
                }

                user_session["data"]["city"] = ''
                user_session["data"]["eps"] = ''
                user_session["data"]["formula_data"] = None
                user_session["data"]["missing_meds"] = None
                user_session["data"]["summary_shown"] = False
                user_session["data"]["birth_date"] = ''
                user_session["data"]["affiliation_regime"] = ''
                user_session["data"]["residence_address"] = ''
                user_session["data"]["pharmacy"] = ''
                user_session["data"]["pharmacy_branch"] = ''
                user_session["data"]["cellphone"] = ''
                user_session["data"]["data_collected"] = {
                    "ciudad": False,
                    "fecha_nacimiento": False,
                    "regimen": False,
                    "direccion": False,
                    "farmacia": False,
                    "celular": False
                }

            if len(user_session["data"]["conversation_history"]) <= 2:
                user_session["data"]["has_greeted"] = True
                user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_CONSENTIMIENTO
                user_session["data"]["awaiting_approval"] = True

                try:
                    base64_image = await self.download_telegram_photo(update, context)
                    await update.message.reply_text("Estoy analizando tu fórmula médica, dame un momento... 🔍")
                    
                    formula_result = await self.image_processor.process_medical_formula(base64_image)
                    user_session["data"]["pending_media"] = formula_result
                    
                    user_session["data"]["conversation_history"].append({
                        "role": "assistant",
                        "content": MENSAJE_CONSENTIMIENTO
                    })
                    
                    await update.message.reply_text(MENSAJE_CONSENTIMIENTO, parse_mode="Markdown")
                    
                except Exception as e:
                    logger.error(f"Error procesando la imagen: {e}")
                    await update.message.reply_text(MENSAJE_FORMULA_MAL_LEIDA)
                
                return

            if not user_session["data"]["consented"]:
                try:
                    base64_image = await self.download_telegram_photo(update, context)
                    formula_result = await self.image_processor.process_medical_formula(base64_image)
                    
                    user_session["data"]["pending_media"] = formula_result
                    user_session["data"]["awaiting_approval"] = True
                    user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_CONSENTIMIENTO
                    
                    response_message = "Para ayudarte con tu queja por medicamentos no entregados, necesito tu autorización para analizar la fórmula médica y procesar tus datos. ¿Me autorizas? (Responde sí o no) 📝✅"
                    
                    user_session["data"]["conversation_history"].append({
                        "role": "assistant",
                        "content": response_message
                    })
                    
                    await update.message.reply_text(response_message)
                    
                except Exception as e:
                    logger.error(f"Error procesando la imagen: {e}")
                    await update.message.reply_text(MENSAJE_FORMULA_MAL_LEIDA)
                    
                return

            try:
                base64_image = await self.download_telegram_photo(update, context)
                formula_result = await self.image_processor.process_medical_formula(base64_image)
                
                self.intent_handler.actualizar_datos_formula(user_session, formula_result)
                user_session["data"]["current_step"] = ConversationSteps.FORMULA_ANALIZADA
                
                resumen = self.intent_handler.mostrar_resumen_formula(user_session)
                await update.message.reply_text(resumen)
                
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

        current_time = time.time()
        if (user_session["data"].get("last_processed_time") and 
                (current_time - user_session["data"]["last_processed_time"] < 2.0)):
            logger.info("Ignorando mensaje duplicado")
            return
        
        user_session["data"]["last_processed_time"] = current_time

        if update.effective_user.first_name:
            user_session["data"]["name"] = update.effective_user.first_name
            if update.effective_user.last_name:
                user_session["data"]["name"] += f" {update.effective_user.last_name}"
        
        if update.effective_user.username:
            user_session["data"]["cellphone"] = update.effective_user.username

        user_session["data"]["conversation_history"].append({
            "role": "user",
            "content": text
        })

        try:
            saludos_pattern = re.compile(r"(hola|buenos días|buenas tardes|buenas noches|saludos|hey|hi|hello|ey)", re.I)
            if saludos_pattern.search(text.lower()) and not user_session["data"]["has_greeted"]:
                user_session["data"]["has_greeted"] = True
                user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_FORMULA
                
            await update.message.reply_text(f"¡Hola! 👋 Bienvenido a No Me Entregaron.\n\n{MENSAJE_SOLICITUD_FORMULA}")
                return
            
            if text.lower() == '/reset' or 'empezar de nuevo' in text.lower() or 'reiniciar' in text.lower():
                reset_session(user_session)
                await update.message.reply_text("He reiniciado nuestra conversación. ¿En qué puedo ayudarte ahora? 🔄")
                return
            
            es_nueva_queja = re.search(r"(nueva queja|otra queja|quiero hacer otra|iniciar otra|tramitar otra|otra .*queja|reportar otro|denunciar otro|otro medicamento no entregado|volver a empezar)", text, re.I)
            if es_nueva_queja:
                if user_session["data"].get("formula_data") and not user_session["data"]["queja_actual"]["guardada"]:
                    await self.bigquery_service.save_user_data(user_session["data"], True)
                
                user_session["data"]["queja_actual"] = {"id": f"{user_id}_{int(time.time())}", "guardada": False}
                user_session["data"]["city"] = ''
                user_session["data"]["eps"] = ''
                user_session["data"]["formula_data"] = None
                user_session["data"]["missing_meds"] = None
                user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_FORMULA
                user_session["data"]["summary_shown"] = False
                user_session["data"]["birth_date"] = ''
                user_session["data"]["affiliation_regime"] = ''
                user_session["data"]["residence_address"] = ''
                user_session["data"]["pharmacy"] = ''
                user_session["data"]["pharmacy_branch"] = ''
                user_session["data"]["cellphone"] = ''
                user_session["data"]["data_collected"] = {
                    "ciudad": False,
                    "fecha_nacimiento": False,
                    "regimen": False,
                    "direccion": False,
                    "farmacia": False,
                    "celular": False
                }

                await update.message.reply_text("¡Claro! 👍 Vamos a tramitar una nueva queja. Por favor, envíame una foto de tu fórmula médica para comenzar. 📋📸")
                return

            if user_session["data"]["awaiting_approval"]:
                respuesta = self.intent_handler.manejar_consentimiento(user_session, text)
                await update.message.reply_text(respuesta)
                return

            if re.search(r"(perd[ií] la f[oó]rmula|no tengo la f[oó]rmula|se me perd[ií]|no la tengo|se me dañó|se me mojó|no la encuentro)", text, re.I):
                user_session["data"]["conversation_history"].append({"role": "assistant", "content": MENSAJE_FORMULA_PERDIDA})
                await update.message.reply_text(MENSAJE_FORMULA_PERDIDA)
                return

            if (not user_session["data"].get("formula_data") and 
                    not user_session["data"].get("pending_media") and 
                    (user_session["data"]["current_step"] == ConversationSteps.INICIO or 
                     user_session["data"]["current_step"] == ConversationSteps.ESPERANDO_FORMULA)):

                if len(text) > 3 and '/' not in text and '?' not in text and '¿' not in text:
                    await update.message.reply_text(MENSAJE_SOLICITUD_FORMULA)
                    return

            if user_session["data"]["current_step"] == ConversationSteps.ESPERANDO_MEDICAMENTOS:
                resultado = await self.intent_handler.procesar_seleccion_medicamentos(text, user_session)
                
                if resultado["exito"]:
                    user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_CIUDAD
                    siguiente_pregunta = self.intent_handler.get_next_question(user_session["data"])
                    if siguiente_pregunta:
                        mensaje_combinado = f"{resultado['mensaje']}\n\n{siguiente_pregunta}"
                        await update.message.reply_text(mensaje_combinado)
                        user_session["data"]["conversation_history"].append({"role": "assistant", "content": mensaje_combinado})
                    else:
                        await update.message.reply_text(resultado["mensaje"])
                        user_session["data"]["conversation_history"].append({"role": "assistant", "content": resultado["mensaje"]})
                    return
                elif resultado.get("mensaje"):
                    await update.message.reply_text(resultado["mensaje"])
                    user_session["data"]["conversation_history"].append({"role": "assistant", "content": resultado["mensaje"]})
                    return

            if user_session["data"]["current_step"] == ConversationSteps.ESPERANDO_CIUDAD:
                ciudad_match = re.match(r"^([A-Za-zÁáÉéÍíÓóÚúÜüÑñ\s]{3,})$", text)
                if ciudad_match and ciudad_match.group(1) and "?" not in text and "¿" not in text:
                    ciudad = ciudad_match.group(1).strip()
                    actualizar_datos_contexto(user_session, "ciudad", ciudad)
                    
                    user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_CELULAR
                    confirmacion = f"¡Perfecto, gracias! He registrado que estás en {ciudad}.\n\n¿Cuál es tu número de celular? 📱 Lo necesitamos para contactarte sobre el estado de tu queja."
                    await update.message.reply_text(confirmacion)
                    user_session["data"]["conversation_history"].append({"role": "assistant", "content": confirmacion})
                    return

            if user_session["data"]["current_step"] == ConversationSteps.ESPERANDO_CELULAR:
                pregunta_para_que = re.search(r"para\s+que\s+me\s+pides|por\s+que\s+me\s+pides", text, re.I)
                if pregunta_para_que:
                    logger.info("Derivando pregunta contextual a OpenAI...")
                else:
                    phone_match = re.match(r"^[+\d\s()-]{7,15}$", text)
                    if phone_match and "?" not in text and "¿" not in text:
                        celular = re.sub(r"[\s()-]", "", text)
                        actualizar_datos_contexto(user_session, "celular", celular)
                        
                        user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_FECHA_NACIMIENTO
                        confirmacion = f"Gracias, he registrado tu número de celular: {celular}. 📱\n\n¿Cuál es tu fecha de nacimiento (DD/MM/AAAA)? 📅"
                        await update.message.reply_text(confirmacion)
                        user_session["data"]["conversation_history"].append({"role": "assistant", "content": confirmacion})
                        return

            if user_session["data"]["current_step"] == ConversationSteps.ESPERANDO_FECHA_NACIMIENTO:
                fecha_extraida = self.intent_handler.extraer_fecha(text)
                if fecha_extraida:
                    actualizar_datos_contexto(user_session, "fechaNacimiento", fecha_extraida)
                    
                    user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_REGIMEN
                    confirmacion = f"Gracias, he registrado tu fecha de nacimiento: {fecha_extraida}. 📆✅\n\n¿Cuál es tu régimen de afiliación? (Contributivo o Subsidiado) 🏛️"
                    await update.message.reply_text(confirmacion)
                    user_session["data"]["conversation_history"].append({"role": "assistant", "content": confirmacion})
                    return

            if user_session["data"]["current_step"] == ConversationSteps.ESPERANDO_REGIMEN:
                texto_lower = text.lower().strip()
                
                if "contributivo" in texto_lower or texto_lower == "c" or texto_lower == "con" or texto_lower == "contributivo":
                    actualizar_datos_contexto(user_session, "regimen", "Contributivo")
                    
                    user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_DIRECCION
                    confirmacion = "Gracias, he registrado tu régimen como Contributivo. ✅\n\n¿Podrías proporcionarme tu dirección completa? 🏠"
                    await update.message.reply_text(confirmacion)
                    user_session["data"]["conversation_history"].append({"role": "assistant", "content": confirmacion})
                    return
                elif "subsidiado" in texto_lower or texto_lower == "s" or texto_lower == "sub" or texto_lower == "subsidiado":
                    actualizar_datos_contexto(user_session, "regimen", "Subsidiado")
                    
                    user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_DIRECCION
                    confirmacion = "Gracias, he registrado tu régimen como Subsidiado. ✅\n\n¿Podrías proporcionarme tu dirección completa? 🏠"
                    await update.message.reply_text(confirmacion)
                    user_session["data"]["conversation_history"].append({"role": "assistant", "content": confirmacion})
                    return

            if user_session["data"]["current_step"] == ConversationSteps.ESPERANDO_DIRECCION:
                if len(text) >= 5 and "?" not in text and "¿" not in text:
                    actualizar_datos_contexto(user_session, "direccion", text)
                    
                    user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_FARMACIA
                    confirmacion = f"¡Perfecto! He anotado tu dirección como {text}. 🏡\n\n¿Cuál es el nombre de la farmacia donde no te entregaron el medicamento? 💊"
                    await update.message.reply_text(confirmacion)
                    user_session["data"]["conversation_history"].append({"role": "assistant", "content": confirmacion})
                    return

            if user_session["data"]["current_step"] == ConversationSteps.ESPERANDO_FARMACIA:
                if len(text) >= 2 and "?" not in text and "¿" not in text:
                    actualizar_datos_contexto(user_session, "farmacia", text)
                    
                    user_session["data"]["current_step"] = ConversationSteps.COMPLETADO
                    resumen = self.intent_handler.generar_resumen_final(user_session["data"])
                    await update.message.reply_text(resumen)
                    user_session["data"]["conversation_history"].append({"role": "assistant", "content": resumen})

                    await self.bigquery_service.save_user_data(user_session["data"], True)
                    return

            patrones = [
                {"regex": re.compile(r"me equivoqu[eé](?:,)?\s+(?:me encuentro|estoy) en\s+([A-Za-zÁáÉéÍíÓóÚúÜüÑñ\s]+)", re.I), "campo": "ciudad"},
                {"regex": re.compile(r"no (?:vivo|resido|estoy) en\s+[^,]+,?\s+(?:sino|estoy) en\s+([A-Za-zÁáÉéÍíÓóÚúÜüÑñ\s]+)", re.I), "campo": "ciudad"},
                {"regex": re.compile(r"cambiar (.*)", re.I), "campo": "cambio"}
            ]
            
            for patron in patrones:
                match = patron["regex"].search(text)
                if match:
                    if patron["campo"] == "ciudad" and match.group(1):
                        nueva_ciudad = match.group(1).strip()
                        ciudad_antigua = user_session["data"].get("city", "la anterior")
                        actualizar_datos_contexto(user_session, "ciudad", nueva_ciudad)
                        
                        siguiente_pregunta = self.intent_handler.get_next_question(user_session["data"])
                        if siguiente_pregunta:
                            respuesta = f"Entendido, he actualizado tu ciudad de {ciudad_antigua} a {nueva_ciudad}. ✅\n\n{siguiente_pregunta}"
                            await update.message.reply_text(respuesta)
                            user_session["data"]["conversation_history"].append({"role": "assistant", "content": respuesta})
                        else:
                            respuesta = f"Entendido, he actualizado tu ciudad de {ciudad_antigua} a {nueva_ciudad}. ✅"
                            await update.message.reply_text(respuesta)
                            user_session["data"]["conversation_history"].append({"role": "assistant", "content": respuesta})
                        return
                    elif patron["campo"] == "cambio" and match.group(1):
                        campo_cambio = match.group(1).lower().strip()
                        
                        if "ciudad" in campo_cambio:
                            user_session["data"]["city"] = ""
                            user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_CIUDAD
                            await update.message.reply_text("Entendido, por favor dime tu ciudad. 🏙️")
                            return
                        elif "régimen" in campo_cambio or "regimen" in campo_cambio:
                            user_session["data"]["affiliation_regime"] = ""
                            user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_REGIMEN
                            await update.message.reply_text("Entendido, por favor dime tu régimen (Contributivo o Subsidiado). 🏛️")
                            return
                        elif "fecha" in campo_cambio:
                            user_session["data"]["birth_date"] = ""
                            user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_FECHA_NACIMIENTO
                            await update.message.reply_text("Entendido, por favor dime tu fecha de nacimiento (DD/MM/AAAA). 📅")
                            return
                        elif "dirección" in campo_cambio or "direccion" in campo_cambio:
                            user_session["data"]["residence_address"] = ""
                            user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_DIRECCION
                            await update.message.reply_text("Entendido, por favor dime tu dirección de residencia. 🏠")
                            return
                        elif "farmacia" in campo_cambio:
                            user_session["data"]["pharmacy"] = ""
                            user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_FARMACIA
                            await update.message.reply_text("Entendido, por favor dime el nombre de la farmacia. 🏪")
                            return
                        elif "celular" in campo_cambio or "teléfono" in campo_cambio or "telefono" in campo_cambio:
                            user_session["data"]["cellphone"] = ""
                            user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_CELULAR
                            await update.message.reply_text("Entendido, por favor dime tu nuevo número de celular. 📱")
                            return

            if (user_session["data"]["current_step"] == ConversationSteps.COMPLETADO or 
                    (user_session["data"].get("missing_meds") and 
                     user_session["data"].get("city") and 
                     user_session["data"].get("birth_date") and 
                     user_session["data"].get("affiliation_regime") and 
                     user_session["data"].get("residence_address") and 
                     user_session["data"].get("pharmacy") and 
                     user_session["data"].get("cellphone"))):
                
                if re.search(r"(no|nada|listo|ok|está bien|bien así|gracias|eso sería todo|es todo)", text, re.I):
                    mensaje_despedida = "¡Excelente! 😊 Estaré pendiente de enviar el número de radicado. Si se te ocurre alguna otra pregunta o necesitas ayuda en el futuro, no dudes en escribirme. ¡Espero que pronto se solucione tu situación! Que tengas un buen día. ⭐"
                    await update.message.reply_text(mensaje_despedida)
                    user_session["data"]["conversation_history"].append({"role": "assistant", "content": mensaje_despedida})

                    if not user_session["data"]["queja_actual"].get("guardada", False):
                        await self.bigquery_service.save_user_data(user_session["data"], True)
                    return
                
                user_session["data"]["current_step"] = ConversationSteps.COMPLETADO

            prompt_generator = SystemPromptGenerator(user_session)
            system_prompt = prompt_generator.generate()
            
            gpt_response = await self.openai_service.ask_openai(system_prompt, user_session["data"]["conversation_history"][-10:])
            
            response_text = gpt_response
            user_session["data"]["conversation_history"].append({"role": "assistant", "content": response_text})
            await update.message.reply_text(response_text)

            self.intent_handler.procesar_respuesta_para_extraccion_datos(response_text, user_session)

            if ("próximas 24 horas" in response_text and
                    "tramitaremos" in response_text and
                    "queja" in response_text and
                    not user_session["data"]["queja_actual"].get("guardada", False)):
                
                logger.info("Detectado mensaje de queja en trámite, guardando datos...")
                await self.bigquery_service.save_user_data(user_session["data"], True)
            
        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await update.message.reply_text("Disculpa, ocurrió un error inesperado. Por favor, intenta nuevamente o escribe /reset para reiniciar la conversación. 🔄")