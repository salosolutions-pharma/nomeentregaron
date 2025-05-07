import logging
import re
from typing import Dict, Any, Optional
from core.session_manager import actualizar_datos_contexto
from core.data_extractor import DataExtractor

logger = logging.getLogger(__name__)

class IntentHandler:
    def __init__(self, openai_service):
        """Initialize the intent handler with OpenAI service"""
        self.openai_service = openai_service
    
    async def procesar_mensaje(self, text: str, user_session: Dict[str, Any]) -> str:
        """
        Process user message using AI-driven approach instead of explicit state management
        """
        try:
            # Add user message to conversation history
            user_message = {"role": "user", "content": text}
            
            # Extract information from user message 
            DataExtractor.extraer_datos_de_mensaje_usuario(text, user_session)
            
            # Check if all required information is available to complete the process
            self._verificar_informacion_completa(user_session)
            
            # Special case for formula missing
            if re.search(r"(perd[ií] la f[oó]rmula|no tengo la f[oó]rmula|se me perd[ií]|no la tengo|se me dañó|se me mojó|no la encuentro)", text.lower(), re.I):
                # Instead of hardcoded message, let the AI explain the options
                if not user_session["data"].get("has_greeted", False):
                    user_session["data"]["has_greeted"] = True
                
                # Add the message to conversation history and generate response
                user_session["data"]["conversation_history"].append(user_message)
                response = await self.openai_service.ask_openai(user_session)
                
                # Extract any information from AI response
                DataExtractor.extraer_datos_de_respuesta(response, user_session)
                
                return response
            
            # Special case for consent handling
            if user_session["data"].get("awaiting_approval", False):
                text_lower = text.lower()
                affirmative = bool(re.search(r"(si|sí|claro|ok|dale|autorizo|acepto|por supuesto|listo|adelante)", text_lower))
                
                if affirmative:
                    user_session["data"]["consented"] = True
                    user_session["data"]["awaiting_approval"] = False
                    
                    # Process pending formula if available
                    if user_session["data"].get("pending_media"):
                        formula_result = user_session["data"]["pending_media"]
                        await self.actualizar_datos_formula(user_session, formula_result)
                        user_session["data"]["pending_media"] = None
                        
                        # Add user message to history and generate response
                        user_session["data"]["conversation_history"].append(user_message)
                        
                        # Have the AI generate a formula summary instead of using a template
                        return await self.openai_service.ask_openai(user_session)
                else:
                    user_session["data"]["awaiting_approval"] = False
                    user_session["data"]["pending_media"] = None
                    
                    # Add user message to history
                    user_session["data"]["conversation_history"].append(user_message)
                    
                    # Let the AI generate a response for denial of consent
                    return await self.openai_service.ask_openai(user_session)
            
            # Detect if this is a closing message
            if re.search(r"(gracias|adios|chao|hasta luego|muchas gracias|listo)", text.lower()):
                logger.info("Mensaje de despedida o agradecimiento detectado")
                # Force process completion if we have enough data
                if (user_session["data"].get("formula_data") and 
                    user_session["data"].get("missing_meds") and 
                    user_session["data"].get("city") and 
                    user_session["data"].get("cellphone")):
                    user_session["data"]["process_completed"] = True
                    logger.info("Proceso marcado como completado debido a mensaje de despedida")
            
            # For all other messages, use the AI-driven approach
            user_session["data"]["conversation_history"].append(user_message)
            response = await self.openai_service.ask_openai(user_session)
            
            # Extract information from AI response
            DataExtractor.extraer_datos_de_respuesta(response, user_session)
            
            # Check again if all information is available after processing response
            self._verificar_informacion_completa(user_session)
            
            # Detect if the response contains a final summary
            if ("próximas" in response.lower() and 
                "horas" in response.lower() and 
                "tramitaremos" in response.lower() and 
                "queja" in response.lower()):
                user_session["data"]["process_completed"] = True
                logger.info("Proceso marcado como completado debido a resumen final")
            
            # Mark first interaction completed if it was first
            if user_session["data"].get("is_first_interaction", True):
                user_session["data"]["is_first_interaction"] = False
                user_session["data"]["has_greeted"] = True
            
            return response
        
        except Exception as e:
            logger.error(f"Error en procesar_mensaje: {e}")
            return "Disculpa, ocurrió un error inesperado. Por favor, intenta nuevamente."
    
    def _verificar_informacion_completa(self, user_session: Dict[str, Any]) -> None:
        """Verifica si se ha completado toda la información necesaria para la queja"""
        data = user_session["data"]
        
        # Log the current state for debugging
        logger.info("Verificando información completa:")
        logger.info(f"- Formula data: {bool(data.get('formula_data'))}")
        logger.info(f"- Consented: {bool(data.get('consented'))}")
        logger.info(f"- Missing meds: {bool(data.get('missing_meds') and data.get('missing_meds') != '[aún no especificado]')}")
        logger.info(f"- City: {bool(data.get('city'))}")
        logger.info(f"- Cellphone: {bool(data.get('cellphone'))}")
        logger.info(f"- Birth date: {bool(data.get('birth_date'))}")
        logger.info(f"- Affiliation regime: {bool(data.get('affiliation_regime'))}")
        logger.info(f"- Residence address: {bool(data.get('residence_address'))}")
        logger.info(f"- Pharmacy: {bool(data.get('pharmacy'))}")
        
        # Verificar y limpiar datos problemáticos
        if data.get("city") and data.get("city").lower() in ["contributivo", "subsidiado", "ese fue"]:
            logger.info(f"Limpiando ciudad inválida: {data.get('city')}")
            data["city"] = ""
        
        if data.get("pharmacy"):
            valor_original = data["pharmacy"]
            valor_limpio = re.sub(r'donde.*te|y la sede donde|donde no te|sede|y\s+debían|debían', '', valor_original, flags=re.I).strip()
            if valor_limpio != valor_original:
                logger.info(f"Limpiando farmacia: '{valor_original}' -> '{valor_limpio}'")
                data["pharmacy"] = valor_limpio if len(valor_limpio) >= 3 else ""
        
        # Verificar si tenemos todos los datos necesarios
        if (data.get("formula_data") and 
            data.get("consented") and
            data.get("missing_meds") and 
            data.get("missing_meds") != "[aún no especificado]" and
            data.get("city") and 
            data.get("cellphone") and 
            data.get("birth_date") and 
            data.get("affiliation_regime") and
            data.get("pharmacy")):
            
            # Si la dirección de residencia está vacía, asignarle un valor por defecto
            if not data.get("residence_address"):
                data["residence_address"] = "No proporcionada"
                logger.info("Asignando dirección por defecto: 'No proporcionada'")
            
            # Marcar como completado inmediatamente si tenemos todos los datos necesarios
            data["process_completed"] = True
            logger.info("✅ PROCESO MARCADO COMO COMPLETADO - Todos los datos requeridos fueron recopilados")
    
    async def actualizar_datos_formula(self, user_session: Dict[str, Any], formula_result: Dict[str, Any]) -> None:
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
            if "context_variables" not in user_session["data"]:
                user_session["data"]["context_variables"] = {}
                
            # Store the medications in the context variables
            user_session["data"]["context_variables"]["medicamentos_array"] = medicamentos
    
    async def manejar_imagen_formula(self, formula_result: Dict[str, Any], user_session: Dict[str, Any]) -> str:
        """Handle prescription image processing results with AI-driven approach"""
        
        # Update formula data in user session
        await self.actualizar_datos_formula(user_session, formula_result)
        
        # If this is first interaction, need to greet first
        if not user_session["data"].get("has_greeted", False):
            user_session["data"]["has_greeted"] = True
            
            # Create a greeting message in the history
            greeting = "¡Hola! 👋 Bienvenido a No Me Entregaron. Soy tu asistente virtual y estoy aquí para ayudarte a radicar quejas cuando no te entregan tus medicamentos en la EPS. 💊"
            user_session["data"]["conversation_history"].append({
                "role": "assistant",
                "content": greeting
            })
            
            # Add a message indicating that formula was received
            user_session["data"]["conversation_history"].append({
                "role": "user", 
                "content": "[Imagen de fórmula médica]"
            })
            
            # Set awaiting approval to true
            user_session["data"]["awaiting_approval"] = True
            user_session["data"]["pending_media"] = formula_result
            
            # Let the AI generate a response requesting consent
            return await self.openai_service.ask_openai(user_session)
        
        # If we've already greeted, check for consent
        if not user_session["data"].get("consented", False):
            user_session["data"]["awaiting_approval"] = True
            user_session["data"]["pending_media"] = formula_result
            
            # Add the message to conversation history
            # Add the message to conversation history
            user_session["data"]["conversation_history"].append({
                "role": "user", 
                "content": "[Imagen de fórmula médica]"
            })
            
            # Let the AI generate a response requesting consent
            return await self.openai_service.ask_openai(user_session)
        
        # If we have consent, process the formula immediately
        user_session["data"]["conversation_history"].append({
            "role": "user", 
            "content": "[Imagen de fórmula médica]"
        })
        
        # Let the AI generate a response with formula summary
        return await self.openai_service.ask_openai(user_session)
    
    async def consultar_historial_paciente(self, user_session: Dict[str, Any]) -> str:
        """Consulta el historial de quejas del paciente actual usando AI"""
        
        # Add a system instruction to generate patient history
        user_session["data"]["conversation_history"].append({
            "role": "user", 
            "content": "Por favor, muéstrame mi historial de quejas anteriores."
        })
        
        # Let the AI generate a response for patient history
        return await self.openai_service.ask_openai(user_session)