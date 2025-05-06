import re
import time
import logging
from typing import Dict, Any, Optional
from config import ConversationSteps
from core.session_manager import actualizar_datos_contexto, get_user_session
from services.openai_service import OpenAIService
from core.prompt_generator import SystemPromptGenerator
from core.data_extractor import DataExtractor
# At the top of your file, ensure the import is correct
from config import (
    ConversationSteps, 
    WELCOME_MESSAGE,  # Make sure this import exists and is not commented out
    MENSAJE_CONSENTIMIENTO,
    MENSAJE_FORMULA_MAL_LEIDA,
    MENSAJE_FORMULA_PERDIDA,
    MENSAJE_SOLICITUD_FORMULA
)

logger = logging.getLogger(__name__)

class IntentHandler:
    def __init__(self, openai_service: OpenAIService):
        self.openai_service = openai_service
        
    async def procesar_mensaje(self, text: str, user_session: Dict[str, Any]) -> str:
        """
        Procesa cualquier mensaje del usuario usando OpenAI para entender la intención
        y extraer la información relevante de manera conversacional.
        """

        # Si el usuario menciona que no tiene la fórmula, dar una respuesta específica
        if re.search(r"no tengo la f[óo]rmula|no necesito la f[óo]rmula|sin la f[óo]rmula", text.lower()):
            response = (
                "Lo siento, pero la fórmula médica es indispensable para poder tramitar tu queja. 📋 "
                "Sin ella no podemos verificar qué medicamentos te fueron recetados ni proceder con el trámite.\n\n"
                "Puedes:\n"
                "• Solicitar un duplicado en tu EPS 🏥\n"
                "• Consultar tu historial médico en la página web de tu EPS 💻\n"
                "• Contactar a tu médico tratante para una nueva fórmula 👨‍⚕️\n\n"
                "Cuando tengas la fórmula, por favor envíame una foto clara y podré ayudarte con tu queja. ¡Estaré aquí esperándote! 👍"
            )
            user_session["data"]["conversation_history"].append({
                "role": "assistant",
                "content": response
            })
            return response
        # Si estamos en el paso de selección de medicamentos, intentar procesar directamente
        if user_session["data"]["current_step"] == ConversationSteps.ESPERANDO_MEDICAMENTOS:
            medicamentos_array = user_session["data"]["context_variables"].get("medicamentos_array", [])
            
            if medicamentos_array:
                # Buscar coincidencias exactas o parciales con nombres de medicamentos
                text_lower = text.lower().strip()
                medicamentos_mencionados = []
                
                # Verificar si menciona medicamentos específicos
                for med in medicamentos_array:
                    nombres_med = med.lower().split()
                    for nombre in nombres_med:
                        if len(nombre) > 3 and nombre in text_lower:
                            medicamentos_mencionados.append(med)
                            break
                
                # Si encontramos medicamentos mencionados
                if medicamentos_mencionados:
                    medicamentos_faltantes = ", ".join(medicamentos_mencionados)
                    actualizar_datos_contexto(user_session, "medicamentos", medicamentos_faltantes)
                    user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_CIUDAD
                    
                    # Añadimos respuesta al historial
                    respuesta = f"Entiendo que no te entregaron: {medicamentos_faltantes}. ¿En qué ciudad te entregan tus medicamentos? 🏙️"
                    user_session["data"]["conversation_history"].append({
                        "role": "assistant",
                        "content": respuesta
                    })
                    return respuesta
        
        # Continuar con el procesamiento normal usando OpenAI
        # Añadimos el mensaje al historial de conversación
        user_session["data"]["conversation_history"].append({
            "role": "user",
            "content": text
        })
        
        # Generamos un prompt dinámico según el estado actual y contexto
        prompt_generator = SystemPromptGenerator(user_session)
        system_prompt = prompt_generator.generate()
        
        # Utilizamos OpenAI para generar una respuesta conversacional
        response = await self.openai_service.ask_openai(
            system_prompt, 
            user_session["data"]["conversation_history"][-15:]
        )
        
        # Almacenamos la respuesta en el historial
        user_session["data"]["conversation_history"].append({
            "role": "assistant",
            "content": response
        })
        
        # Procesamos la respuesta para extraer datos relevantes
        DataExtractor.extraer_datos_de_respuesta(response, user_session)
        DataExtractor.extraer_datos_de_mensaje_usuario(text, user_session)
        
        # Actualizamos el estado de la conversación basado en el contexto
        self.actualizar_estado_conversacion(user_session)
        
        return response
    
    def actualizar_estado_conversacion(self, user_session: Dict[str, Any]) -> None:
        """Actualiza el estado de la conversación basado en los datos recopilados"""
        
        data = user_session["data"]
        
        # Si estamos esperando medicamentos y ya los tenemos, avanzamos
        if (data["current_step"] == ConversationSteps.ESPERANDO_MEDICAMENTOS 
            and data.get("missing_meds")):
            data["current_step"] = ConversationSteps.ESPERANDO_CIUDAD
            logger.info("Avanzando a ESPERANDO_CIUDAD")
        
        # Si estamos esperando ciudad y ya la tenemos, avanzamos
        elif (data["current_step"] == ConversationSteps.ESPERANDO_CIUDAD 
              and data.get("city")):
            data["current_step"] = ConversationSteps.ESPERANDO_CELULAR
            logger.info("Avanzando a ESPERANDO_CELULAR")
        
        # Si estamos esperando celular y ya lo tenemos, avanzamos
        elif (data["current_step"] == ConversationSteps.ESPERANDO_CELULAR 
              and data.get("cellphone")):
            data["current_step"] = ConversationSteps.ESPERANDO_FECHA_NACIMIENTO
            logger.info("Avanzando a ESPERANDO_FECHA_NACIMIENTO")
        
        # Si estamos esperando fecha de nacimiento y ya la tenemos, avanzamos
        elif (data["current_step"] == ConversationSteps.ESPERANDO_FECHA_NACIMIENTO 
              and data.get("birth_date")):
            data["current_step"] = ConversationSteps.ESPERANDO_REGIMEN
            logger.info("Avanzando a ESPERANDO_REGIMEN")
        
        # Si estamos esperando régimen y ya lo tenemos, avanzamos
        elif (data["current_step"] == ConversationSteps.ESPERANDO_REGIMEN 
              and data.get("affiliation_regime")):
            data["current_step"] = ConversationSteps.ESPERANDO_DIRECCION
            logger.info("Avanzando a ESPERANDO_DIRECCION")
        
        # Si estamos esperando dirección y ya la tenemos, avanzamos
        elif (data["current_step"] == ConversationSteps.ESPERANDO_DIRECCION 
              and data.get("residence_address")):
            data["current_step"] = ConversationSteps.ESPERANDO_FARMACIA
            logger.info("Avanzando a ESPERANDO_FARMACIA")
        
        # Si estamos esperando farmacia y ya la tenemos, avanzamos
        elif (data["current_step"] == ConversationSteps.ESPERANDO_FARMACIA 
              and data.get("pharmacy")):
            data["current_step"] = ConversationSteps.COMPLETADO
            logger.info("Avanzando a COMPLETADO")
        
        # Verificar si tenemos toda la información necesaria para completar
        if (data.get("missing_meds") and 
            data.get("city") and 
            data.get("cellphone") and 
            data.get("birth_date") and 
            data.get("affiliation_regime") and 
            data.get("residence_address") and 
            data.get("pharmacy")):
            
            # Si tenemos todos los datos, marcamos como completado
            data["current_step"] = ConversationSteps.COMPLETADO
            logger.info("Todos los datos recopilados. Conversación COMPLETADA")
            
            # Actualizar los datos recopilados
            data["data_collected"] = {
                "ciudad": True,
                "fecha_nacimiento": True,
                "regimen": True,
                "direccion": True,
                "farmacia": True,
                "celular": True
            }

    def generar_resumen_formula(self, formula_data: Dict[str, Any]) -> str:
        nombre_completo = formula_data.get("paciente", "")
        
        # En Colombia, el formato suele ser: APELLIDO1 APELLIDO2 NOMBRE1 NOMBRE2
        partes_nombre = nombre_completo.split()
        nombre_pila = ""
        
        if len(partes_nombre) >= 3:
        
            if len(partes_nombre) >= 4:
    
                nombre_pila = " ".join(partes_nombre[2:])
            else:
                nombre_pila = partes_nombre[-1]
        elif len(partes_nombre) == 2:
            nombre_pila = partes_nombre[-1]
        else:
            nombre_pila = nombre_completo
        
        if nombre_pila:
            nombre_pila = nombre_pila.title()
        
        saludo_personalizado = f"¡Gracias por tu autorización! "
        if nombre_pila:
            saludo_personalizado = f"¡Gracias por tu autorización, {nombre_pila}! "
        
        medicamentos = formula_data.get("medicamentos", [])
        medicamentos_texto = ""
        
        if medicamentos:
            medicamentos_texto = "\n".join([f"{i + 1}. {med}" for i, med in enumerate(medicamentos)])
        else:
            medicamentos_texto = "No se identificaron medicamentos"
        
        return (
            f"{saludo_personalizado}He analizado tu fórmula médica y aquí te muestro lo que encontré:\n\n"
            f"👤 Paciente: {formula_data.get('paciente', 'No visible')}\n"
            f"📄 Documento: {formula_data.get('tipo_documento', 'No visible')} {formula_data.get('numero_documento', 'No visible')}\n"
            f"🏥 EPS: {formula_data.get('eps', 'No visible')}\n"
            f"👨‍⚕️ Doctor: {formula_data.get('doctor', 'No visible')}\n"
            f"📅 Fecha de atención: {formula_data.get('fecha_atencion', 'No visible')}\n\n"
            f"💊 Medicamentos recetados:\n{medicamentos_texto}\n\n"
            f"Por favor, dime cuáles de estos medicamentos no te entregaron."
        )
        
    def mostrar_resumen_formula(self, user_session: Dict[str, Any]) -> str:
        """Muestra el resumen de la fórmula y actualiza el estado de la conversación"""
        
        user_session["data"]["summary_shown"] = True
        resumen = self.generar_resumen_formula(user_session["data"]["formula_data"])
        user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_MEDICAMENTOS
        user_session["data"]["conversation_history"].append({"role": "assistant", "content": resumen})
        return resumen
        
    def generar_resumen_final(self, user_data: Dict[str, Any]) -> str:
        """Genera un resumen final con toda la información recopilada"""
        
        if not user_data.get("missing_meds") or user_data.get("missing_meds") == "[aún no especificado]":
            user_data["current_step"] = ConversationSteps.ESPERANDO_MEDICAMENTOS
            return "Por favor, antes de finalizar, necesito saber cuáles medicamentos no te fueron entregados. 💊"
        
        medicamentos_faltantes = user_data.get("missing_meds", "")
        
        return (
            f"¡Perfecto! Entonces, vamos a resumir lo que tengo hasta ahora:\n\n"
            f"- Medicamento(s) no entregado(s): {medicamentos_faltantes}\n"
            f"- Farmacia: {user_data.get('pharmacy', '')} en {user_data.get('city', '')}\n"
            f"- Fecha de nacimiento: {user_data.get('birth_date', '')}\n"
            f"- Régimen: {user_data.get('affiliation_regime', '')}\n"
            f"- Dirección: {user_data.get('residence_address', '')}\n"
            f"- Celular: {user_data.get('cellphone', '')}\n"
            f"\nEn las próximas 24 horas tramitaremos tu queja ante la EPS y te enviaré el número de radicado por este mismo chat. ¿Hay algo más en lo que pueda ayudarte? 😊"
        )
    
    def actualizar_datos_formula(self, user_session: Dict[str, Any], formula_result: Dict[str, Any]) -> None:
        """Actualiza los datos de la fórmula médica en la sesión del usuario"""
        
        user_session["data"]["formula_data"] = formula_result.get("datos", {})
        
        # Actualizar el nombre del usuario con el de la fórmula
        if formula_result.get("datos", {}).get("paciente"):
            user_session["data"]["name"] = formula_result["datos"]["paciente"]
            logger.info(f"Nombre del paciente actualizado a: {user_session['data']['name']}")
        
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
        """Maneja la respuesta del usuario al solicitar consentimiento para procesar sus datos"""
        
        # Check if we've greeted the user yet
        if not user_session["data"].get("has_greeted", False):
            user_session["data"]["has_greeted"] = True
            user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_CONSENTIMIENTO
            
            # Add the welcome message and then continue with consent handling
            welcome_message = WELCOME_MESSAGE
            user_session["data"]["conversation_history"].append({
                "role": "assistant",
                "content": welcome_message
            })
            
            # Continue with normal consent flow after ensuring greeting
            logger.info("Primera interacción detectada durante solicitud de consentimiento - saludando primero")
        
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
                    from config import MENSAJE_FORMULA_MAL_LEIDA
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
        """Procesa la selección de medicamentos no entregados por parte del usuario"""
        
        return await DataExtractor.procesar_seleccion_medicamentos(text, user_session)
    
    async def consultar_historial_paciente(self, user_session: Dict[str, Any]) -> str:
        """Consulta el historial de quejas del paciente actual"""
        
        # Intentar obtener el documento del paciente actual de la fórmula
        documento = user_session["data"].get("formula_data", {}).get("numero_documento", "")
        
        if not documento:
            return "No puedo consultar el historial porque no tengo el documento del paciente. Por favor, envía primero una fórmula médica."
        
        # Verificar si tenemos historial para este paciente
        if "patient_history" not in user_session["data"]:
            user_session["data"]["patient_history"] = {}
            
        if documento not in user_session["data"]["patient_history"]:
            return "No encontré quejas anteriores para este paciente en mi base de datos."
        
        historial = user_session["data"]["patient_history"][documento]
        nombre_paciente = historial.get("nombre", "este paciente")
        quejas = historial.get("quejas", [])
        
        if not quejas:
            return f"No hay quejas anteriores registradas para {nombre_paciente}."
        
        # Generar mensaje con el historial de quejas
        primer_nombre = nombre_paciente.split()[0] if nombre_paciente else "este paciente"
        respuesta = f"He encontrado {len(quejas)} queja(s) anteriores para {primer_nombre}:\n\n"
        
        for i, queja in enumerate(quejas):
            respuesta += f"{i+1}. Fecha: {queja['fecha']}\n"
            respuesta += f"   Medicamentos no entregados: {queja['medicamentos']}\n"
            respuesta += f"   EPS: {queja.get('eps', 'No registrada')}\n"
            if i < len(quejas) - 1:
                respuesta += "\n"
        
        return respuesta