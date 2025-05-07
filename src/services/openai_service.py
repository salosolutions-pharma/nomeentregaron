import os
import json
import logging
from typing import Dict, Any, List
from openai import OpenAI

logger = logging.getLogger(__name__)

class OpenAIService:
    def __init__(self, api_key: str = None):
        """Initialize the OpenAI service with API key"""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key)
    
    async def ask_openai(self, user_session: Dict[str, Any], new_message: Dict[str, str] = None) -> str:
        """
        Process user message using OpenAI to drive the conversation,
        with minimal handcrafted logic or state management
        """
        try:
            # Get the most recent messages (limited to prevent token overflow)
            conversation_history = user_session["data"]["conversation_history"][-15:] if user_session["data"]["conversation_history"] else []
            
            # Add the new message to the conversation history if provided
            if new_message:
                conversation_history.append(new_message)
            
            # Generate system prompt with session context
            system_prompt = self._generate_system_prompt(user_session)
            
            # Format messages for OpenAI API
            formatted_messages = [{"role": "system", "content": system_prompt}]
            formatted_messages.extend(conversation_history)
            
            # Call OpenAI API with default settings (no custom temperature)
            response = self.client.chat.completions.create(
                model="o4-mini",
                messages=formatted_messages
            )
            
            # Extract and return the response content
            assistant_response = response.choices[0].message.content
            
            # Add the assistant's response to conversation history
            conversation_history.append({"role": "assistant", "content": assistant_response})
            user_session["data"]["conversation_history"] = conversation_history
            
            return assistant_response
            
        except Exception as e:
            logger.error(f"Error en ask_openai: {e}")
            return "Lo siento, tuve un problema al procesar tu mensaje. ¿Podrías intentarlo de nuevo?"
    
    def _generate_system_prompt(self, user_session: Dict[str, Any]) -> str:
        """
        Generate a comprehensive system prompt that includes all context and instructions
        for the AI to handle the conversation appropriately
        """
        # Extract essential context information
        session_data = user_session["data"]
        
        # Create context section of the prompt with all collected user information
        context = self._build_context_section(session_data)
        
        # Create formula section if formula data exists
        formula_section = self._build_formula_section(session_data)
        
        # Core instructions that don't change
        core_instructions = """
Eres un asistente virtual conversacional llamado "No Me Entregaron" que ayuda a usuarios a radicar quejas cuando no les entregan medicamentos en su EPS en Colombia. Tu tono es amigable, empático y natural, evitando sonar robótico o seguir un guion rígido.

OBJETIVO PRINCIPAL:
Tu objetivo es ayudar al usuario a radicar una queja por medicamentos no entregados por su EPS, recopilando toda la información necesaria de manera natural y conversacional.

PERSONALIDAD:
- Eres conversacional, amable y empático. Usas emojis ocasionalmente para dar un tono amigable 😊
- Si el usuario bromea, puedes seguirle la corriente brevemente y luego volver al proceso
- No suenas como un formulario o un bot automatizado, sino como un asistente humano y cercano
- Extraes información relevante de las respuestas del usuario sin preguntar mecánicamente
- Nunca preguntas por información que ya has recibido

REGLAS CRÍTICAS:
1. LA FÓRMULA MÉDICA ES ABSOLUTAMENTE OBLIGATORIA para el proceso. Sin ella, NO se puede tramitar ninguna queja.
2. MANEJO DE PRIMERA INTERACCIÓN:
   - Si es la primera vez que interactúas con el usuario, SIEMPRE debes saludar primero antes de pedir cualquier información
   - Si el usuario envía una foto de la fórmula como primer mensaje, primero saluda y preséntate, luego solicita autorización
   - Nunca pidas autorización sin antes haber saludado al usuario
3. Si el usuario indica que no tiene la fórmula, NUNCA debes sugerir que se puede continuar sin ella.
4. Si el usuario pregunta si puede solo comentarte los medicamentos, explica amablemente que se requiere la fórmula médica física.
5. Cuando el usuario diga que no tiene la fórmula, explica las opciones para obtenerla.
6. Si conoces el nombre del paciente desde la fórmula, dirígete a él/ella por su nombre de pila al inicio de tus mensajes.

INFORMACIÓN A RECOPILAR:
Para completar el proceso, necesitas obtener la siguiente información (en orden):
1. Foto de la fórmula médica y autorización para procesar los datos
2. Medicamentos no entregados (de la fórmula)
3. Ciudad donde le entregan los medicamentos
4. Número de celular
5. Fecha de nacimiento
6. Régimen de afiliación (Contributivo o Subsidiado)
7. Dirección de residencia
8. Farmacia y sede donde debían entregarle los medicamentos

FLUJO CONVERSACIONAL ESPERADO:
1. Saluda y solicita fórmula médica (si no la ha enviado)
2. Al recibir fórmula, pide autorización (si no la ha dado)
3. Al tener autorización, muestra resumen de la fórmula y pregunta qué medicamentos no le entregaron
4. Después solicita ciudad, celular, fecha nacimiento, régimen, dirección y farmacia
5. Al tener toda la información, muestra resumen final y confirma trámite de queja

PAUTAS IMPORTANTES:
- Para cada dato que el usuario te proporcione, confirma brevemente que lo has recibido antes de pasar a la siguiente pregunta
- Si el usuario proporciona varios datos a la vez, procésalos todos y continúa con lo siguiente que falte
- Acepta cualquier formato de fecha, dirección y otros datos
- Si el usuario dice que no le entregaron ningún medicamento o todos, acepta esa respuesta

RESUMEN FINAL:
Cuando tengas toda la información, presenta un resumen así:

"¡Perfecto! He anotado que la farmacia donde no te entregaron los medicamentos es [FARMACIA].
Aquí tienes un resumen de la información que has proporcionado:
- *Medicamentos no entregados*: [LISTA DE MEDICAMENTOS]
- *Farmacia*: [FARMACIA] en [CIUDAD]
- *Número de celular*: [CELULAR]
- *Fecha de nacimiento*: [FECHA]
- *Régimen:* [RÉGIMEN]
- *Dirección:* [DIRECCIÓN]
En las próximas 24 horas, tramitaremos tu queja ante la EPS y te enviaré el número de radicado por este mismo chat. 📄 ¿Hay algo más en lo que pueda ayudarte? 😊"
"""

        # Combine all sections into the final system prompt
        system_prompt = f"{core_instructions}\n\n{context}\n\n{formula_section}"
        
        return system_prompt
    
    def _build_context_section(self, user_data: Dict[str, Any]) -> str:
        """Build detailed context information about the user and conversation state"""
        
        context = "INFORMACIÓN DEL USUARIO Y ESTADO DE LA CONVERSACIÓN:\n"
        
        # Add user's name if available
        if user_data.get("name"):
            context += f"- Nombre del paciente: {user_data.get('name')}\n"
            primer_nombre = user_data.get("name").split()[0] if user_data.get("name") else ""
            if primer_nombre:
                context += f"- Primer nombre: {primer_nombre}\n"
        
        # Add information we already have
        if user_data.get("city"):
            context += f"- Ciudad: {user_data.get('city')}\n"
        
        if user_data.get("eps"):
            context += f"- EPS: {user_data.get('eps')}\n"
            
        if user_data.get("missing_meds"):
            context += f"- Medicamentos no entregados: {user_data.get('missing_meds')}\n"
            
        if user_data.get("cellphone"):
            context += f"- Celular: {user_data.get('cellphone')}\n"
            
        if user_data.get("birth_date"):
            context += f"- Fecha de nacimiento: {user_data.get('birth_date')}\n"
            
        if user_data.get("affiliation_regime"):
            context += f"- Régimen de afiliación: {user_data.get('affiliation_regime')}\n"
            
        if user_data.get("residence_address"):
            context += f"- Dirección: {user_data.get('residence_address')}\n"
            
        if user_data.get("pharmacy"):
            context += f"- Farmacia: {user_data.get('pharmacy')}\n"
        
        # Add information about consent and conversation state
        context += f"- Consentimiento recibido: {'Sí' if user_data.get('consented') else 'No'}\n"
        context += f"- Primera interacción: {'Sí' if user_data.get('is_first_interaction', True) else 'No'}\n"
        context += f"- Ha saludado: {'Sí' if user_data.get('has_greeted') else 'No'}\n"
        
        # Determine what information is still needed
        context += "\nINFORMACIÓN PENDIENTE POR RECOPILAR:\n"
        
        if not user_data.get("formula_data"):
            context += "- Fórmula médica\n"
        
        if not user_data.get("consented"):
            context += "- Consentimiento para procesar datos\n"
            
        if not user_data.get("missing_meds") or user_data.get("missing_meds") == "[aún no especificado]":
            context += "- Medicamentos no entregados\n"
            
        if not user_data.get("city"):
            context += "- Ciudad\n"
            
        if not user_data.get("cellphone"):
            context += "- Número de celular\n"
            
        if not user_data.get("birth_date"):
            context += "- Fecha de nacimiento\n"
            
        if not user_data.get("affiliation_regime"):
            context += "- Régimen de afiliación\n"
            
        if not user_data.get("residence_address"):
            context += "- Dirección\n"
            
        if not user_data.get("pharmacy"):
            context += "- Farmacia\n"
        
        # Add next information to request based on what's missing
        context += "\nPRÓXIMA INFORMACIÓN A SOLICITAR:\n"
        
        if not user_data.get("formula_data"):
            context += "- Solicitar foto de fórmula médica\n"
        elif not user_data.get("consented"):
            context += "- Solicitar consentimiento para procesar datos\n"
        elif not user_data.get("missing_meds") or user_data.get("missing_meds") == "[aún no especificado]":
            context += "- Preguntar por medicamentos no entregados\n"
        elif not user_data.get("city"):
            context += "- Preguntar por ciudad\n"
        elif not user_data.get("cellphone"):
            context += "- Preguntar por número de celular\n"
        elif not user_data.get("birth_date"):
            context += "- Preguntar por fecha de nacimiento\n"
        elif not user_data.get("affiliation_regime"):
            context += "- Preguntar por régimen de afiliación\n"
        elif not user_data.get("residence_address"):
            context += "- Preguntar por dirección\n"
        elif not user_data.get("pharmacy"):
            context += "- Preguntar por farmacia\n"
        else:
            context += "- Presentar resumen final\n"
        
        return context
    
    def _build_formula_section(self, user_data: Dict[str, Any]) -> str:
        """Build information about the prescription if available"""
        
        if not user_data.get("formula_data"):
            return "ESTADO DE LA FÓRMULA: No proporcionada aún"
        
        formula = user_data["formula_data"]
        
        context = "INFORMACIÓN DE LA FÓRMULA MÉDICA:\n"
        context += f"- Paciente: {formula.get('paciente', 'No disponible')}\n"
        context += f"- Documento: {formula.get('tipo_documento', '')} {formula.get('numero_documento', '')}\n"
        context += f"- Doctor: {formula.get('doctor', 'No disponible')}\n"
        context += f"- Fecha de atención: {formula.get('fecha_atencion', 'No disponible')}\n"
        context += f"- EPS: {formula.get('eps', 'No disponible')}\n"
        
        # Add medications if available
        medicamentos = formula.get("medicamentos", [])
        if medicamentos:
            context += "- Medicamentos recetados:\n"
            for i, med in enumerate(medicamentos):
                context += f"  {i+1}. {med}\n"
                
        return context