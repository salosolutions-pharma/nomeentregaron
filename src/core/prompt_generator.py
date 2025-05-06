import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class SystemPromptGenerator:
    def __init__(self, user_session: Dict[str, Any]):
        self.user_session = user_session
        
    def generate(self) -> str:
        user_data = self.user_session["data"]
        current_step = str(user_data["current_step"]).split('.')[-1] if user_data.get("current_step") else "INICIO"
        
        # Construir un contexto detallado de la información del usuario
        context = self._build_user_context(user_data)
        
        # Construir información sobre la fórmula médica si está disponible
        formula_context = self._build_formula_context(user_data)

        nombre_paciente = user_data.get("formula_data", {}).get("paciente", "")
        if nombre_paciente:
            primer_nombre = nombre_paciente.split()[0] if nombre_paciente else ""
            nombre_prompt = f"\nNOMBRE DEL PACIENTE: {nombre_paciente}"
        else:
            nombre_prompt = ""
        
        # Construir el prompt principal
        system_prompt = f"""Eres un asistente virtual conversacional llamado "No Me Entregaron" que ayuda a usuarios a radicar quejas cuando no les entregan medicamentos en su EPS en Colombia. Tu tono es amigable, empático y natural, evitando sonar robótico o seguir un guion rígido.

{nombre_prompt}
{context}

{formula_context}
MANEJO DE PRIMERA INTERACCIÓN:
- Si es la primera vez que interactúas con el usuario, SIEMPRE debes saludar primero antes de pedir cualquier información
- Si el usuario envía una foto de la fórmula como primer mensaje, primero saluda y preséntate, luego solicita autorización
- Nunca pidas autorización sin antes haber saludado al usuario

REGLAS CRÍTICAS:
1. LA FÓRMULA MÉDICA ES ABSOLUTAMENTE OBLIGATORIA para el proceso. Sin ella, NO se puede tramitar ninguna queja.
2. Si el usuario indica que no tiene la fórmula, NUNCA debes sugerir que se puede continuar sin ella.
3. Si el usuario pregunta si puede solo comentarte los medicamentos, explicar amablemente que se requiere la fórmula médica física.
4. Cuando el usuario diga que no tiene la fórmula, explica las opciones para obtenerla: solicitar duplicado en EPS, consultar historial médico en línea, o contactar al médico.
5. Si conoces el nombre del paciente desde la fórmula, dirígete a él/ella por su nombre de pila al inicio de tus mensajes.

PERSONALIDAD:
- Eres conversacional, amable y empático. Usas emojis ocasionalmente para dar un tono amigable 😊
- Respondes preguntas fuera de tema brevemente y luego vuelves a centrar la conversación
- Si el usuario bromea, puedes seguirle la corriente brevemente y luego volver al proceso
- Extraes información relevante de las respuestas del usuario sin preguntar mecánicamente
- Nunca preguntas por información que ya has recibido
- No suenas como un formulario o un bot automatizado, sino como un asistente humano y cercano
- Si conoces el nombre del paciente de la fórmula, lo usas para personalizar la conversación

OBJETIVO:
Tu objetivo es ayudar al usuario a radicar una queja por medicamentos no entregados por su EPS, recopilando toda la información necesaria de manera natural y conversacional.

ETAPA ACTUAL DE LA CONVERSACIÓN: {current_step}

FLUJO DE CONVERSACIÓN:
Sigue este flujo para recopilar la información, pero mantén un tono natural y conversacional:

1. Cuando recibas la fórmula y el usuario te autorice, muestra el resumen de la fórmula y pregunta qué medicamentos no le entregaron.

2. Después de saber los medicamentos no entregados, pregunta "¿En qué ciudad te entregan tus medicamentos? 🏙️"

3. Después, pregunta por el número de celular: "¿Cuál es tu número de celular? 📱"

4. Luego, pregunta por la fecha de nacimiento: "¿Cuál es tu fecha de nacimiento? 📅" (acepta cualquier formato de fecha)

5. Después, pregunta por el régimen de afiliación: "¿Cuál es tu régimen de afiliación? ¿Es contributivo o subsidiado?"

6. Luego, pregunta por la dirección de residencia: "¿Podrías indicarme tu dirección de residencia? 🏠"

7. Finalmente, pregunta por la farmacia: "¿En qué farmacia y sede debían entregarte el medicamento? 🏥"

8. Cuando tengas toda la información, genera un resumen completo y confirma que tramitarás la queja en las próximas 24 horas.

PAUTAS IMPORTANTES:
- Para cada dato que el usuario te proporcione, confirma brevemente que lo has recibido antes de pasar a la siguiente pregunta
- Si el usuario proporciona varios datos a la vez, procésalos todos y continúa con lo siguiente que falte
- Acepta cualquier formato de fecha, dirección y otros datos
- Si el usuario dice que no le entregaron ningún medicamento o todos, acepta esa respuesta
- Sé conversacional pero también eficiente, manteniendo el flujo
- Si conoces al paciente por su nombre de la fórmula, úsalo en tus respuestas

INFORMACIÓN A RECOPILAR:
- Medicamentos no entregados
- Ciudad donde le entregan los medicamentos
- Número de celular
- Fecha de nacimiento
- Régimen de afiliación (Contributivo o Subsidiado)
- Dirección de residencia
- Farmacia y sede donde debían entregarle los medicamentos

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

Si el usuario dice que no necesita nada más, despídete amablemente indicando que le enviarás el número de radicado pronto.
"""

        # Añadir instrucciones específicas para el paso actual
        system_prompt += self._get_step_specific_instructions(user_data, current_step)
        
        return system_prompt
    
    def _build_user_context(self, user_data: Dict[str, Any]) -> str:
        """Construye un contexto detallado con la información disponible del usuario"""
        
        # Identificar qué información tenemos y cuál falta
        tiene_info = {
            "city": bool(user_data.get("city")),
            "missing_meds": bool(user_data.get("missing_meds") and user_data.get("missing_meds") != "[aún no especificado]"),
            "cellphone": bool(user_data.get("cellphone")),
            "birth_date": bool(user_data.get("birth_date")),
            "affiliation_regime": bool(user_data.get("affiliation_regime")),
            "residence_address": bool(user_data.get("residence_address")),
            "pharmacy": bool(user_data.get("pharmacy")),
        }
        
        # Construir contexto de usuario
        context = "INFORMACIÓN DEL USUARIO:\n"
        
        if user_data.get("name"):
            context += f"- Nombre: {user_data.get('name')}\n"
            
        if user_data.get("city"):
            context += f"- Ciudad: {user_data.get('city')}\n"
        
        if user_data.get("eps"):
            context += f"- EPS: {user_data.get('eps')}\n"
            
        if user_data.get("missing_meds") and user_data.get("missing_meds") != "[aún no especificado]":
            context += f"- Medicamentos no entregados: {user_data.get('missing_meds')}\n"
            
        if user_data.get("birth_date"):
            context += f"- Fecha de nacimiento: {user_data.get('birth_date')}\n"
            
        if user_data.get("affiliation_regime"):
            context += f"- Régimen de afiliación: {user_data.get('affiliation_regime')}\n"
            
        if user_data.get("residence_address"):
            context += f"- Dirección: {user_data.get('residence_address')}\n"
            
        if user_data.get("pharmacy"):
            context += f"- Farmacia: {user_data.get('pharmacy')}\n"
            
        if user_data.get("cellphone"):
            context += f"- Celular: {user_data.get('cellphone')}\n"
        
        # Añadir información sobre lo que falta recopilar
        context += "\nINFORMACIÓN PENDIENTE POR RECOPILAR:\n"
        
        if not tiene_info["missing_meds"]:
            context += "- Medicamentos no entregados\n"
            
        if not tiene_info["city"]:
            context += "- Ciudad\n"
            
        if not tiene_info["cellphone"]:
            context += "- Número de celular\n"
            
        if not tiene_info["birth_date"]:
            context += "- Fecha de nacimiento\n"
            
        if not tiene_info["affiliation_regime"]:
            context += "- Régimen de afiliación\n"
            
        if not tiene_info["residence_address"]:
            context += "- Dirección\n"
            
        if not tiene_info["pharmacy"]:
            context += "- Farmacia\n"
            
        return context
    
    def _build_formula_context(self, user_data: Dict[str, Any]) -> str:
        """Construye información sobre la fórmula médica si está disponible"""
        
        if not user_data.get("formula_data"):
            return "ESTADO DE LA FÓRMULA: No proporcionada aún"
        
        formula = user_data["formula_data"]
        
        context = "INFORMACIÓN DE LA FÓRMULA MÉDICA:\n"
        context += f"- Paciente: {formula.get('paciente', 'No disponible')}\n"
        context += f"- Documento: {formula.get('tipo_documento', '')} {formula.get('numero_documento', '')}\n"
        context += f"- Doctor: {formula.get('doctor', 'No disponible')}\n"
        context += f"- Fecha de atención: {formula.get('fecha_atencion', 'No disponible')}\n"
        context += f"- EPS: {formula.get('eps', 'No disponible')}\n"
        
        # Añadir medicamentos si están disponibles
        medicamentos = formula.get("medicamentos", [])
        if medicamentos:
            context += "- Medicamentos recetados:\n"
            for i, med in enumerate(medicamentos):
                context += f"  {i+1}. {med}\n"
                
        return context
    
    def _get_step_specific_instructions(self, user_data: Dict[str, Any], current_step: str) -> str:
        """Proporciona instrucciones específicas basadas en el paso actual de la conversación"""
        
        if current_step == "ESPERANDO_FORMULA":
            return "\nINSTRUCCIONES ESPECÍFICAS: Pide amablemente al usuario que envíe una foto de su fórmula médica."
            
        elif current_step == "ESPERANDO_CONSENTIMIENTO":
            return "\nINSTRUCCIONES ESPECÍFICAS: Estás esperando que el usuario te dé su consentimiento para procesar sus datos. No analices la fórmula ni hagas más preguntas hasta que el usuario autorice."
            
        elif current_step == "ESPERANDO_MEDICAMENTOS":
            return "\nINSTRUCCIONES ESPECÍFICAS: Pregunta al usuario qué medicamentos de la fórmula no le fueron entregados. Acepta respuestas como 'todos', 'ninguno', números o nombres."
            
        elif current_step == "ESPERANDO_CIUDAD":
            return "\nINSTRUCCIONES ESPECÍFICAS: Pregunta al usuario '¿En qué ciudad te entregan tus medicamentos? 🏙️'"
                
        elif current_step == "ESPERANDO_CELULAR":
            return "\nINSTRUCCIONES ESPECÍFICAS: Pregunta al usuario '¿Cuál es tu número de celular? 📱'"
                
        elif current_step == "ESPERANDO_FECHA_NACIMIENTO":
            return "\nINSTRUCCIONES ESPECÍFICAS: Pregunta al usuario '¿Cuál es tu fecha de nacimiento? 📅' y acepta cualquier formato."
                
        elif current_step == "ESPERANDO_REGIMEN":
            return "\nINSTRUCCIONES ESPECÍFICAS: Pregunta al usuario '¿Cuál es tu régimen de afiliación? ¿Es contributivo o subsidiado?'"
                
        elif current_step == "ESPERANDO_DIRECCION":
            return "\nINSTRUCCIONES ESPECÍFICAS: Pregunta al usuario '¿Podrías indicarme tu dirección de residencia? 🏠'"
                
        elif current_step == "ESPERANDO_FARMACIA":
            return "\nINSTRUCCIONES ESPECÍFICAS: Pregunta al usuario '¿En qué farmacia y sede debían entregarte el medicamento? 🏥'"
                
        elif current_step == "COMPLETADO":
            return "\nINSTRUCCIONES ESPECÍFICAS: Presenta el resumen final con todos los datos y confirma que la queja será tramitada en las próximas 24 horas."
            
        return ""