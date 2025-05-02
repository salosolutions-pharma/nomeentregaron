import re
import time
import logging
from typing import Dict, Any, Optional
from src.models.user_session import actualizar_datos_contexto, get_user_session
from src.services.openai_service import OpenAIService, SystemPromptGenerator

logger = logging.getLogger(__name__)

class IntentHandler:
    def __init__(self, openai_service: OpenAIService):
        
        self.openai_service = openai_service
        
    def generar_resumen_formula(self, formula_data: Dict[str, Any]) -> str:
        
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
        
    def mostrar_resumen_formula(self, user_session: Dict[str, Any]) -> str:
        
        from src.config import ConversationSteps
        
        user_session["data"]["summary_shown"] = True
        resumen = self.generar_resumen_formula(user_session["data"]["formula_data"])
        user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_MEDICAMENTOS
        user_session["data"]["conversation_history"].append({"role": "assistant", "content": resumen})
        return resumen
        
    def 
        from src.config import ConversationSteps
        
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
    
    def actualizar_datos_formula(self, user_session: Dict[str, Any], formula_result: Dict[str, Any]) -> None:
        
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
    
    def manejar_consentimiento(self, user_session: Dict[str, Any], text: str) -> str:
        
        from src.config import ConversationSteps
        
        affirmative = bool(re.search(r"(si|sí|claro|ok|dale|autorizo|acepto|por supuesto|listo|adelante)", text, re.I))
        
        if affirmative:
            user_session["data"]["consented"] = True
            user_session["data"]["awaiting_approval"] = False
            
            if user_session["data"]["pending_media"]:
                try:
                    formula_result = user_session["data"]["pending_media"]
                    self.actualizar_datos_formula(user_session, formula_result)
                    user_session["data"]["current_step"] = ConversationSteps.FORMULA_ANALIZADA
                    user_session["data"]["pending_media"] = None
                    return self.mostrar_resumen_formula(user_session)
                except Exception as e:
                    logger.error(f"Error al procesar fórmula pendiente: {e}")
                    user_session["data"]["pending_media"] = None
                    from src.config import MENSAJE_FORMULA_MAL_LEIDA
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
    
    async def procesar_seleccion_medicamentos(self, text: str, user_session: Dict[str, Any]) -> Dict[str, Any]:
        
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
    
    def get_next_question(self, user_data: Dict[str, Any]) -> Optional[str]:
        
        from src.config import ConversationSteps
        
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
        return self.generar_resumen_final(user_data)
    
    def extraer_fecha(self, texto: str) -> Optional[str]:
        
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
    
    def procesar_respuesta_para_extraccion_datos(self, respuesta: str, user_session: Dict[str, Any]) -> None:
        
        from src.config import ConversationSteps
        
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