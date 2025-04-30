import os
import logging
import time
import base64
import requests
import re
from io import BytesIO
from enum import Enum, auto
from typing import Dict, Any, Optional, List
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from processor import (
    process_medical_formula,
    ask_openai,
    SystemPromptGenerator
)

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
MENSAJE_CONSENTIMIENTO = "Para ayudarte con tu queja por medicamentos no entregados, necesito tu autorización para analizar la fórmula médica y procesar tus datos. ¿Me autorizas? (responde sí o no) 📝✅"
MENSAJE_FORMULA_MAL_LEIDA = "No pude leer bien la fórmula. 🔍❌ ¿Podrías enviarme una foto más clara por favor? Necesito que la imagen esté bien iluminada y enfocada. 📸✨"
MENSAJE_FORMULA_PERDIDA = "Entiendo que no tienes la fórmula médica en este momento. 📋❓\n\nEstas son algunas opciones que puedes considerar:\n• Solicitar un duplicado directamente en tu EPS 🏥\n• Consultar tu historial médico en la página web de tu EPS (muchas permiten descargar fórmulas anteriores) 💻\n• Contactar a tu médico tratante para que te genere una nueva fórmula 👨‍⚕️\n\n¿Te gustaría más información sobre alguna de estas alternativas? También puedes escribirme cuando tengas la fórmula y te ayudaré con gusto. 🤝"
MENSAJE_SOLICITUD_FORMULA = "Para ayudarte con tu queja, necesito que me envíes una foto clara de tu fórmula médica. 📋📸"

user_sessions: Dict[str, Dict[str, Any]] = {}

def get_user_session(user_id: str) -> Dict[str, Any]:
    
    if user_id not in user_sessions:
        
        user_sessions[user_id] = {
            "session_id": f"telegram-session-{user_id}-{int(time.time())}",
            "data": {
                "user_id": user_id,
                "name": "",
                "city": "",
                "eps": "",
                "consented": False,
                "formula_data": None,
                "missing_meds": None,
                "pending_media": None,
                "conversation_history": [],
                "last_interaction": time.time(),
                "current_step": ConversationSteps.INICIO,
                "awaiting_approval": False,
                "context_variables": {},
                "has_greeted": False,
                "summary_shown": False,
                "last_processed_time": None,
                
                "cellphone": "",
                "birth_date": "",
                "affiliation_regime": "",
                "residence_address": "",
                "pharmacy": "",
                "pharmacy_branch": "",
                
                "data_collected": {
                    "ciudad": False,
                    "fecha_nacimiento": False,
                    "regimen": False,
                    "direccion": False,
                    "farmacia": False,
                    "celular": False
                },
                
                "queja_actual": {
                    "id": f"{user_id}_{int(time.time())}",
                    "guardada": False
                },
                "quejas_anteriores": []
            }
        }
        logger.info(f"Nueva sesión creada para {user_id}: {user_sessions[user_id]['session_id']}")
    else:
        user_sessions[user_id]["data"]["last_interaction"] = time.time()
    
    return user_sessions[user_id]

def reset_session(user_session: Dict[str, Any]) -> None:
    
    previous_user_id = user_session["data"]["user_id"]
    previous_name = user_session["data"]["name"]
    previous_conversation_history = user_session["data"]["conversation_history"]
    previous_quejas = user_session["data"]["quejas_anteriores"] or []

    user_session["data"] = {
        "user_id": previous_user_id,
        "name": previous_name,
        "city": "",
        "eps": "",
        "consented": True,
        "formula_data": None,
        "missing_meds": None,
        "pending_media": None,
        "conversation_history": previous_conversation_history,
        "last_interaction": time.time(),
        "current_step": ConversationSteps.ESPERANDO_FORMULA,
        "awaiting_approval": False,
        "context_variables": {},
        "has_greeted": True,
        "summary_shown": False,
        "last_processed_time": time.time(),
        
        "cellphone": "",
        "birth_date": "",
        "affiliation_regime": "",
        "residence_address": "",
        "pharmacy": "",
        "pharmacy_branch": "",
        
        "data_collected": {
            "ciudad": False,
            "fecha_nacimiento": False,
            "regimen": False,
            "direccion": False,
            "farmacia": False,
            "celular": False
        },
        
        "queja_actual": {
            "id": f"{previous_user_id}_{int(time.time())}",
            "guardada": False
        },
        "quejas_anteriores": previous_quejas
    }

async def download_telegram_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    
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

def actualizar_datos_formula(user_session: Dict[str, Any], formula_result: Dict[str, Any]) -> None:
    
    user_session["data"]["formula_data"] = formula_result.get("datos", {})
    
    user_session["data"]["eps"] = formula_result.get("datos", {}).get("eps", "")

    if formula_result.get("datos", {}).get("diagnostico"):
        user_session["data"]["formula_data"]["diagnostico"] = formula_result["datos"]["diagnostico"]

    medicamentos = formula_result.get("datos", {}).get("medicamentos", [])
    if medicamentos:
        medicamentos_lista = [f"{i + 1}. {med}" for i, med in enumerate(medicamentos)]
        medicamentos_texto = "\n".join(medicamentos_lista)
        
        user_session["data"]["context_variables"]["medicamentos_lista"] = medicamentos_texto
        user_session["data"]["context_variables"]["medicamentos_array"] = medicamentos

def generar_resumen_formula(formula_data: Dict[str, Any]) -> str:
    medicamentos = formula_data.get("medicamentos", [])
    medicamentos_texto = ""
    
    if medicamentos:
        medicamentos_texto = "\n".join([f"{i + 1}. {med}" for i, med in enumerate(medicamentos)])
    else:
        medicamentos_texto = "No se identificaron medicamentos"
    
    return (
        f"¡Gracias por tu autorización! He analizado tu fórmula médica y aquí te muestro lo que encontré:\n\n"
        f"👤 Paciente: {formula_data.get('paciente', 'No visible')}\n"
        f"📄 Documento: {formula_data.get('tipo_documento', 'No visible')} {formula_data.get('numero_documento', 'No visible')}\n"
        f"🏥 EPS: {formula_data.get('eps', 'No visible')}\n"
        f"👨‍⚕️ Doctor: {formula_data.get('doctor', 'No visible')}\n"
        f"📅 Fecha de atención: {formula_data.get('fecha_atencion', 'No visible')}\n\n"
        f"💊 Medicamentos recetados:\n{medicamentos_texto}\n\n"
        f"Por favor, dime cuáles de estos medicamentos no te fueron entregados. Puedes indicarlos por número (ej. \"el 1 y el 3\"), nombre, o decir \"todos\" o \"ninguno\" según corresponda."
    )

def mostrar_resumen_formula(user_session: Dict[str, Any]) -> str:
    user_session["data"]["summary_shown"] = True
    resumen = generar_resumen_formula(user_session["data"]["formula_data"])
    user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_MEDICAMENTOS
    user_session["data"]["conversation_history"].append({"role": "assistant", "content": resumen})
    return resumen

def generar_resumen_final(user_data: Dict[str, Any]) -> str:
    
    if not user_data.get("missing_meds") or user_data.get("missing_meds") == "[aún no especificado]":
        user_data["current_step"] = ConversationSteps.ESPERANDO_MEDICAMENTOS
        return "Por favor, antes de finalizar, necesito saber cuáles medicamentos no te fueron entregados. 💊"
    
    medicamentos_faltantes = user_data.get("missing_meds", "")
    
    return (
        f"¡Perfecto! Entonces, vamos a resumir lo que tengo hasta ahora:\n\n"
        f"- Medicamento(s) no entregado(s): {medicamentos_faltantes}\n"
        f"- Farmacia: {user_data.get('pharmacy', '')} en {user_data.get('city', '')}\n"
        f"\nEn las próximas 24 horas tramitaremos tu queja ante la EPS y te enviaré el número de radicado por este mismo chat. ¿Hay algo más en lo que pueda ayudarte? 😊"
    )

def actualizar_datos_contexto(user_session: Dict[str, Any], tipo: str, valor: str) -> None:
    
    if not valor or not valor.strip():
        return
    
    logger.info(f"Actualizando {tipo}: {valor}")
    
    data = user_session["data"]
    
    if tipo == "ciudad":
        data["city"] = valor
    elif tipo == "farmacia":
        data["pharmacy"] = valor
    elif tipo == "direccion":
        data["residence_address"] = valor
    elif tipo == "regimen":
        data["affiliation_regime"] = valor
    elif tipo == "fechaNacimiento":
        data["birth_date"] = valor
    elif tipo == "medicamentos":
        data["missing_meds"] = valor
    elif tipo == "celular":
        data["cellphone"] = valor
    else:
        logger.warning(f"Tipo de dato no reconocido: {tipo}")

def manejar_consentimiento(user_session: Dict[str, Any], text: str) -> str:
    
    import re
    
    affirmative = bool(re.search(r"(si|sí|claro|ok|dale|autorizo|acepto|por supuesto|listo|adelante)", text, re.I))
    
    if affirmative:
        user_session["data"]["consented"] = True
        user_session["data"]["awaiting_approval"] = False
        
        if user_session["data"]["pending_media"]:
            try:
                formula_result = user_session["data"]["pending_media"]
                actualizar_datos_formula(user_session, formula_result)
                user_session["data"]["current_step"] = ConversationSteps.FORMULA_ANALIZADA
                user_session["data"]["pending_media"] = None
                return mostrar_resumen_formula(user_session)
            except Exception as e:
                logger.error(f"Error al procesar fórmula pendiente: {e}")
                user_session["data"]["pending_media"] = None
                user_session["data"]["conversation_history"].append({"role": "assistant", "content": MENSAJE_FORMULA_MAL_LEIDA})
                return MENSAJE_FORMULA_MAL_LEIDA
        
        mensaje = "¡Gracias por tu autorización! 👍 Ahora por favor envíame una foto de tu fórmula médica para comenzar el proceso. 📋📸"
        user_session["data"]["conversation_history"].append({"role": "assistant", "content": mensaje})
        return mensaje
    else:
        user_session["data"]["awaiting_approval"] = False
        user_session["data"]["pending_media"] = None
        mensaje = "Entiendo. Sin tu autorización no puedo procesar tus datos ni ayudarte con la queja. Si cambias de opinión, puedes escribirme nuevamente. ¡Que tengas un buen día! 👋"
        user_session["data"]["conversation_history"].append({"role": "assistant", "content": mensaje})
        return mensaje

async def procesar_seleccion_medicamentos(text: str, user_session: Dict[str, Any]) -> Dict[str, Any]:
    
    text_lower = text.lower().strip()
    medicamentos_array = user_session["data"]["context_variables"].get("medicamentos_array", [])
    
    if not medicamentos_array:
        return {"exito": False, "mensaje": "No hay medicamentos para seleccionar"}
    
    numero_medicamento = re.search(r"(?:n[uú]mero\s*)?(?:la\s*)?(\d{1,2})", text_lower)
    if numero_medicamento:
        index = int(numero_medicamento.group(1)) - 1
        if 0 <= index < len(medicamentos_array):
            medicamento_seleccionado = medicamentos_array[index]
            actualizar_datos_contexto(user_session, "medicamentos", medicamento_seleccionado)
            return {
                "exito": True,
                "mensaje": f"Entiendo, el medicamento que no te entregaron es el {index + 1}: {medicamento_seleccionado}."
            }
    
    if text_lower in ["ninguno", "ninguna", "ningun", "ningún"]:
        todos_los_medicamentos = ", ".join(medicamentos_array)
        actualizar_datos_contexto(user_session, "medicamentos", todos_los_medicamentos)
        return {
            "exito": True,
            "mensaje": "Entiendo que no te entregaron ninguno de los medicamentos recetados."
        }
    
    if text_lower in ["todos", "todo"] or "todos los" in text_lower:
        todos_los_medicamentos = ", ".join(medicamentos_array)
        actualizar_datos_contexto(user_session, "medicamentos", todos_los_medicamentos)
        return {
            "exito": True,
            "mensaje": "Entiendo que no te entregaron ninguno de los medicamentos recetados."
        }
    
    for med in medicamentos_array:
        nombre_base = med.split(' ')[0].lower()
        if nombre_base in text_lower:
            actualizar_datos_contexto(user_session, "medicamentos", med)
            return {
                "exito": True,
                "mensaje": f"Entiendo, el medicamento que no te entregaron es: {med}."
            }
    
    return {
        "exito": False,
        "mensaje": "No he podido identificar qué medicamento no te entregaron. Por favor, especifica el número del medicamento o su nombre."
    }

def get_next_question(user_data: Dict[str, Any]) -> Optional[str]:
    
    if user_data["current_step"] == ConversationSteps.FORMULA_ANALIZADA and not user_data["summary_shown"]:
        return None

    if not user_data.get("missing_meds") or user_data["missing_meds"] == "" or user_data["missing_meds"] == "[aún no especificado]":
        user_data["current_step"] = ConversationSteps.ESPERANDO_MEDICAMENTOS
        return "Por favor, dime cuáles de estos medicamentos no te fueron entregados. 💊"

    if not user_data.get("city") and not user_data["data_collected"]["ciudad"]:
        user_data["current_step"] = ConversationSteps.ESPERANDO_CIUDAD
        user_data["data_collected"]["ciudad"] = True
        return "¿En qué ciudad te entregan tus medicamentos? 🏙️"

    if not user_data.get("cellphone") and not user_data["data_collected"]["celular"]:
        user_data["current_step"] = ConversationSteps.ESPERANDO_CELULAR
        user_data["data_collected"]["celular"] = True
        return "¿Cuál es tu número de celular? 📱 Lo necesitamos para contactarte sobre el estado de tu queja."

    if not user_data.get("birth_date") and not user_data["data_collected"]["fecha_nacimiento"]:
        user_data["current_step"] = ConversationSteps.ESPERANDO_FECHA_NACIMIENTO
        user_data["data_collected"]["fecha_nacimiento"] = True
        return "¿Cuál es tu fecha de nacimiento (DD/MM/AAAA)? 📅"

    if not user_data.get("affiliation_regime") and not user_data["data_collected"]["regimen"]:
        user_data["current_step"] = ConversationSteps.ESPERANDO_REGIMEN
        user_data["data_collected"]["regimen"] = True
        return "¿Cuál es tu régimen de afiliación? (Contributivo o Subsidiado) 🏛️"

    if not user_data.get("residence_address") and not user_data["data_collected"]["direccion"]:
        user_data["current_step"] = ConversationSteps.ESPERANDO_DIRECCION
        user_data["data_collected"]["direccion"] = True
        return "¿Podrías proporcionarme tu dirección completa? 🏠"

    if not user_data.get("pharmacy") and not user_data["data_collected"]["farmacia"]:
        user_data["current_step"] = ConversationSteps.ESPERANDO_FARMACIA
        user_data["data_collected"]["farmacia"] = True
        return "¿Cuál es el nombre de la farmacia donde no te entregaron el medicamento? 💊"

    user_data["current_step"] = ConversationSteps.COMPLETADO
    return generar_resumen_final(user_data)

def extraer_fecha(texto: str) -> Optional[str]:
    
    formato_slash = re.search(r"(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})", texto)
    formato_texto = re.search(r"(\d{1,2})\s+de\s+([a-zñáéíóú]+)(?:\s+de\s+)?(\d{4})?", texto, re.I)
    
    if formato_slash:
        dia = formato_slash.group(1).zfill(2)
        mes = formato_slash.group(2).zfill(2)
        anio = formato_slash.group(3)
        return f"{dia}/{mes}/{anio}"
    
    if formato_texto:
        dia = formato_texto.group(1).zfill(2)
        mes_texto = formato_texto.group(2).lower()
        anio = formato_texto.group(3) or str(time.localtime().tm_year)
        
        meses = {
            'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04',
            'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
            'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12'
        }
        
        for nombre, numero in meses.items():
            if nombre in mes_texto:
                return f"{dia}/{numero}/{anio}"
    
    return None

async def save_user_data(user_data: Dict[str, Any], force_save: bool = False) -> bool:
    
    try:
        from google.cloud import bigquery
        
        
        datos_obligatorios_completos = (
            user_data.get("formula_data") and
            user_data.get("missing_meds") and
            user_data.get("missing_meds") != "[aún no especificado]"
        )

        if not datos_obligatorios_completos and not force_save:
            logger.info("Datos incompletos, no se guarda en BigQuery todavía")
            return False

        logger.info("Preparando datos para BigQuery...")

        
        fecha_atencion = None
        if user_data.get("formula_data", {}).get("fecha_atencion"):
            fecha_parts = user_data["formula_data"]["fecha_atencion"].split('/')
            if len(fecha_parts) == 3:
                dia, mes, anio = fecha_parts
                fecha_atencion = f"{anio}-{mes.zfill(2)}-{dia.zfill(2)}"

        
        nombre_paciente = user_data.get("formula_data", {}).get("paciente", "No disponible")
        logger.info(f"Nombre del paciente desde la fórmula: {nombre_paciente}")

        
        row = {
            "PK": user_data["queja_actual"]["id"],
            "tipo_documento": user_data.get("formula_data", {}).get("tipo_documento", "No disponible"),
            "numero_documento": user_data.get("formula_data", {}).get("numero_documento", "No disponible"),
            "paciente": nombre_paciente,
            "fecha_atencion": fecha_atencion,
            "eps": user_data.get("formula_data", {}).get("eps", "No disponible"),
            "doctor": user_data.get("formula_data", {}).get("doctor", "No disponible"),
            "ips": user_data.get("formula_data", {}).get("ips", "No disponible"),
            "diagnostico": user_data.get("formula_data", {}).get("diagnostico", "No disponible"),
            "medicamentos": ", ".join(user_data.get("formula_data", {}).get("medicamentos", [])) or "No disponible",
            "image_url": "",
            "no_entregado": user_data.get("missing_meds", "No especificado"),
            "fecha_nacimiento": user_data.get("birth_date", "No disponible"),
            "telefono": user_data.get("cellphone", user_data.get("user_id", "No disponible")),
            "regimen": user_data.get("affiliation_regime", "No disponible"),
            "municipio": user_data.get("city", "No disponible"),
            "direccion": user_data.get("residence_address", "No disponible"),
            "farmacia": user_data.get("pharmacy", "No disponible")
        }

        
        if user_data["queja_actual"].get("guardada", False):
            logger.info(f"La queja {user_data['queja_actual']['id']} ya fue guardada anteriormente.")
            return True
            
        
        bigquery_client = bigquery.Client(project=os.getenv('BIGQUERY_PROJECT_ID'))
        dataset_id = os.getenv('BIGQUERY_DATASET_ID', 'solutions2pharma_data')
        table_id = os.getenv('BIGQUERY_TABLE_ID', 'quejas')
        table_ref = f"{os.getenv('BIGQUERY_PROJECT_ID')}.{dataset_id}.{table_id}"

        try:
            
            logger.info(f"Enviando datos a BigQuery con los campos: {list(row.keys())}")
            logger.info(f"Datos que se enviarán: {row}")
            
            
            table = bigquery_client.get_table(table_ref)
            errors = bigquery_client.insert_rows_json(table, [row])
            
            if not errors:
                
                user_data["queja_actual"]["guardada"] = True
                user_data["quejas_anteriores"].append({
                    "id": user_data["queja_actual"]["id"],
                    "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "paciente": nombre_paciente,
                    "medicamentos": user_data.get("missing_meds", "")
                })

                logger.info(f"✅ Datos guardados correctamente en BigQuery para el paciente: {nombre_paciente}")
                return True
            else:
                logger.error(f"❌ Errores al insertar en BigQuery: {errors}")
                return False

        except Exception as error:
            logger.error(f'❌ Error guardando en BigQuery: {error}')
            
            
            if hasattr(error, 'errors'):
                problematicos = []
                for err in getattr(error, 'errors', []):
                    for detail in getattr(err, 'errors', []):
                        match = re.search(r"no such field: ([^.]+)", getattr(detail, 'message', ''))
                        if match and match.group(1):
                            problematicos.append(match.group(1))
                
                if problematicos:
                    logger.error(f"Campos problemáticos detectados: {', '.join(problematicos)}")
                    
                    
                    for campo in problematicos:
                        if campo in row:
                            del row[campo]
                    
                    logger.info("Reintentando con campos corregidos:", list(row.keys()))
                    
                    try:
                        errors = bigquery_client.insert_rows_json(table, [row])
                        if not errors:
                            user_data["queja_actual"]["guardada"] = True
                            logger.info("✅ Datos guardados en la tabla después de corrección")
                            return True
                        else:
                            logger.error(f"❌ Error en segundo intento: {errors}")
                    except Exception as retry_error:
                        logger.error(f'❌ Error en segundo intento: {retry_error}')
            
            return False
    except Exception as e:
        logger.error(f'Error general preparando datos para BigQuery: {e}')
        return False

def procesar_respuesta_para_extraccion_datos(respuesta: str, user_session: Dict[str, Any]) -> None:
    
    respuesta_lower = respuesta.lower()
    
    if ("actualizado tu ciudad" in respuesta_lower or 
            ("ciudad" in respuesta_lower and "actualizado" in respuesta_lower)):
        
        ciudad_match = re.search(r"ciudad(?:.+?)(?:a|como|por)\s+([A-Za-zÁáÉéÍíÓóÚúÜüÑñ\s]+)(?:\.|\!)", respuesta, re.I)
        if ciudad_match and ciudad_match.group(1) and len(ciudad_match.group(1).strip()) > 2:
            actualizar_datos_contexto(user_session, "ciudad", ciudad_match.group(1).strip())
    
    if ("régimen" in respuesta_lower and 
            ("contributivo" in respuesta_lower or "subsidiado" in respuesta_lower)):
        
        if "contributivo" in respuesta_lower:
            actualizar_datos_contexto(user_session, "regimen", "Contributivo")
        elif "subsidiado" in respuesta_lower:
            actualizar_datos_contexto(user_session, "regimen", "Subsidiado")
    
    if ("he registrado" in respuesta_lower and 
            "medicamentos" in respuesta_lower and 
            "faltan" in respuesta_lower):
        
        medicamento_match = re.search(r"faltan(?:.+?):\s+(.+?)(?:\.|\!|\n)", respuesta, re.I)
        if medicamento_match and medicamento_match.group(1):
            actualizar_datos_contexto(user_session, "medicamentos", medicamento_match.group(1).strip())
    
    if "dirección" in respuesta_lower and "registrado" in respuesta_lower:
        direccion_match = re.search(r"dirección(?:.+?)(?:como|:)\s+([A-Za-zÁáÉéÍíÓóÚúÜüÑñ\s0-9#\-\.]+)(?:\.|\!|\n)", respuesta, re.I)
        if direccion_match and direccion_match.group(1):
            actualizar_datos_contexto(user_session, "direccion", direccion_match.group(1).strip())
    
    if "farmacia" in respuesta_lower and "es" in respuesta_lower:
        farmacia_match = re.search(r"farmacia(?:.+?)es\s+([A-Za-zÁáÉéÍíÓóÚúÜüÑñ\s]+)(?:\.|\!|\n)", respuesta, re.I)
        if farmacia_match and farmacia_match.group(1):
            actualizar_datos_contexto(user_session, "farmacia", farmacia_match.group(1).strip())
    
    if "celular" in respuesta_lower and "registrado" in respuesta_lower:
        celular_match = re.search(r"celular(?:.+?)(?:como|:)\s+([0-9+\s()-]+)(?:\.|\!|\n)", respuesta, re.I)
        if celular_match and celular_match.group(1):
            actualizar_datos_contexto(user_session, "celular", celular_match.group(1).strip().replace(r"[\s()-]", ""))
    
    if (("próximas horas" in respuesta_lower or "registrado toda" in respuesta_lower) and 
            "queja" in respuesta_lower and 
            ("tramitaremos" in respuesta_lower or "será tramitada" in respuesta_lower)):
        
        user_session["data"]["current_step"] = ConversationSteps.COMPLETADO
        logger.info("Conversación marcada como COMPLETADA")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    
    user_id = str(update.effective_user.id)
    user_session = get_user_session(user_id)
    
    user_session["data"]["has_greeted"] = True
    user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_FORMULA
    
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Puedo ayudarte a radicar quejas cuando no te entregan medicamentos en tu EPS. "
        "Aquí hay algunos comandos útiles:\n\n"
        "/start - Iniciar una nueva conversación\n"
        "/reset - Reiniciar el proceso actual\n"
        "/help - Mostrar esta ayuda\n\n"
        "Para comenzar, simplemente envíame una foto de tu fórmula médica o escribe cualquier mensaje. 📋📸"
    )
    await update.message.reply_text(help_text)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    
    user_id = str(update.effective_user.id)
    user_session = get_user_session(user_id)
    
    reset_session(user_session)
    
    await update.message.reply_text("He reiniciado nuestra conversación. ¿En qué puedo ayudarte ahora? 🔄")

async def process_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    
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
                await save_user_data(user_session["data"], True)

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
                base64_image = await download_telegram_photo(update, context)
                await update.message.reply_text("Estoy analizando tu fórmula médica, dame un momento... 🔍")
                
                formula_result = await process_medical_formula(base64_image)
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
                base64_image = await download_telegram_photo(update, context)
                formula_result = await process_medical_formula(base64_image)
                
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
            base64_image = await download_telegram_photo(update, context)
            formula_result = await process_medical_formula(base64_image)
            
            actualizar_datos_formula(user_session, formula_result)
            user_session["data"]["current_step"] = ConversationSteps.FORMULA_ANALIZADA
            
            resumen = mostrar_resumen_formula(user_session)
            await update.message.reply_text(resumen)
            
        except Exception as e:
            logger.error(f"Error procesando la imagen: {e}")
            await update.message.reply_text(MENSAJE_FORMULA_MAL_LEIDA)
            
    except Exception as e:
        logger.error(f"Error general en process_photo_message: {e}")
        await update.message.reply_text("Lo siento, tuve un problema al procesar tu imagen. ¿Podrías intentar enviarla de nuevo o con mejor iluminación? 📸✨")

async def process_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    
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
                await save_user_data(user_session["data"], True)
            
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
            respuesta = manejar_consentimiento(user_session, text)
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
            resultado = await procesar_seleccion_medicamentos(text, user_session)
            
            if resultado["exito"]:
                
                user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_CIUDAD
                siguiente_pregunta = get_next_question(user_session["data"])
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
            fecha_extraida = extraer_fecha(text)
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
                resumen = generar_resumen_final(user_session["data"])
                await update.message.reply_text(resumen)
                user_session["data"]["conversation_history"].append({"role": "assistant", "content": resumen})

                await save_user_data(user_session["data"], True)
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
                    
                    siguiente_pregunta = get_next_question(user_session["data"])
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
                    await save_user_data(user_session["data"], True)
                return
            
            user_session["data"]["current_step"] = ConversationSteps.COMPLETADO
        
        prompt_generator = SystemPromptGenerator(user_session)
        system_prompt = prompt_generator.generate()
        
        gpt_response = await ask_openai(system_prompt, user_session["data"]["conversation_history"][-10:])
        
        response_text = gpt_response
        user_session["data"]["conversation_history"].append({"role": "assistant", "content": response_text})
        await update.message.reply_text(response_text)

        procesar_respuesta_para_extraccion_datos(response_text, user_session)

        if ("próximas 24 horas" in response_text and
                "tramitaremos" in response_text and
                "queja" in response_text and
                not user_session["data"]["queja_actual"].get("guardada", False)):
            
            logger.info("Detectado mensaje de queja en trámite, guardando datos...")
            await save_user_data(user_session["data"], True)
        
    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await update.message.reply_text("Disculpa, ocurrió un error inesperado. Por favor, intenta nuevamente o escribe /reset para reiniciar la conversación. 🔄")

def setup_telegram_bot(token: str) -> Application:

    application = Application.builder().token(token).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_command))

    application.add_handler(MessageHandler(filters.PHOTO, process_photo_message))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_text_message))

    application.add_error_handler(lambda update, context: logger.error(f"Error en el bot: {context.error}"))
    
    return application