import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class SystemPromptGenerator:
    def __init__(self, user_session: Dict[str, Any]):
        self.user_session = user_session
        
    def generate(self) -> str:
        """
        Genera un prompt de sistema detallado con todo el contexto necesario
        para que el modelo de OpenAI maneje la conversación.
        """
        user_data = self.user_session["data"]
        
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
        
        # Construir el prompt principal con instrucciones detalladas
        system_prompt = f"""Eres un asistente virtual conversacional llamado "No Me Entregaron" que ayuda a usuarios a radicar quejas cuando no les entregan medicamentos en su EPS en Colombia. Tu tono es amigable, empático y natural, evitando sonar robótico o seguir un guion rígido.

{nombre_prompt}
{context}

{formula_context}

PERSONALIDAD:
- Eres conversacional, amable y empático. Usas emojis ocasionalmente para dar un tono amigable 😊
- Respondes preguntas fuera de tema brevemente y luego vuelves a centrar la conversación
- Si el usuario bromea, puedes seguirle la corriente brevemente y luego volver al proceso
- Extraes información relevante de las respuestas del usuario sin preguntar mecánicamente
- Nunca preguntas por información que ya has recibido
- No suenas como un formulario o un bot automatizado, sino como un asistente humano y cercano
- Si conoces el nombre del paciente de la fórmula, lo usas para personalizar la conversación

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

OBJETIVO:
Tu objetivo es ayudar al usuario a radicar una queja por medicamentos no entregados por su EPS, recopilando toda la información necesaria de manera natural y conversacional.

INFORMACIÓN A RECOPILAR:
- Medicamentos no entregados
- Ciudad donde le entregan los medicamentos
- Número de celular
- Fecha de nacimiento
- Régimen de afiliación (Contributivo o Subsidiado)
- Dirección de residencia
- Farmacia y sede donde debían entregarle los medicamentos

FLUJO CONVERSACIONAL INTELIGENTE:
1. Cuando recibas la fórmula y el usuario te autorice, muestra el resumen de la fórmula y pregunta qué medicamentos no le entregaron.
2. Después de saber los medicamentos no entregados, pregunta por la ciudad.
3. Luego pregunta por el número de celular, fecha de nacimiento, régimen de afiliación, dirección de residencia y farmacia.
4. Cuando tengas toda la información, genera un resumen completo y confirma que tramitarás la queja en las próximas 24 horas.

PAUTAS IMPORTANTES:
- Para cada dato que el usuario te proporcione, confirma brevemente que lo has recibido antes de pasar a la siguiente pregunta
- Si el usuario proporciona varios datos a la vez, procésalos todos y continúa con lo siguiente que falte
- Acepta cualquier formato de fecha, dirección y otros datos
- Si el usuario dice que no le entregaron ningún medicamento o todos, acepta esa respuesta
- Sé conversacional pero también eficiente, manteniendo el flujo
- Si conoces al paciente por su nombre de la fórmula, úsalo en tus respuestas

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

        return system_prompt
    
    def _build_user_context(self, user_data: Dict[str, Any]) -> str:
        """Construye un contexto detallado con la información disponible del usuario"""
        
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
        
        # Añadir estado de la conversación
        context += f"\nESTADO DE LA CONVERSACIÓN:\n"
        context += f"- Primera interacción: {'Sí' if user_data.get('is_first_interaction', True) else 'No'}\n"
        context += f"- Ha saludado: {'Sí' if user_data.get('has_greeted') else 'No'}\n"
        context += f"- Consentimiento para procesar datos: {'Sí' if user_data.get('consented') else 'No'}\n"
        context += f"- Proceso completado: {'Sí' if user_data.get('process_completed') else 'No'}\n"
        
        # Añadir información sobre lo que falta recopilar
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
        
        # Determinar próximo paso
        context += "\nPRÓXIMA ACCIÓN:\n"
        
        if not user_data.get("has_greeted", False):
            context += "- Saludar al usuario\n"
        elif not user_data.get("formula_data"):
            context += "- Solicitar foto de fórmula médica\n"
        elif not user_data.get("consented"):
            context += "- Solicitar consentimiento para procesar datos\n"
        elif not user_data.get("missing_meds") or user_data.get("missing_meds") == "[aún no especificado]":
            context += "- Preguntar medicamentos no entregados\n"
        elif not user_data.get("city"):
            context += "- Preguntar ciudad\n"
        elif not user_data.get("cellphone"):
            context += "- Preguntar número de celular\n"
        elif not user_data.get("birth_date"):
            context += "- Preguntar fecha de nacimiento\n"
        elif not user_data.get("affiliation_regime"):
            context += "- Preguntar régimen de afiliación\n"
        elif not user_data.get("residence_address"):
            context += "- Preguntar dirección\n"
        elif not user_data.get("pharmacy"):
            context += "- Preguntar farmacia\n"
        else:
            context += "- Presentar resumen final\n"
            
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