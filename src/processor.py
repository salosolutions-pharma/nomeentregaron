import os
import json
import logging
import re
import base64
from typing import Dict, Any, List, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

async def process_medical_formula(base64_image: str) -> Dict[str, Any]:
    
    try:
        logger.info("Procesando imagen con OpenAI Vision...")
        
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = """Analiza esta prescripción médica con extrema precisión y atención al detalle. Extrae la siguiente información:

1. Tipo de documento (CC, TI, etc.)
2. Número de documento (solo números, sin espacios)
3. Nombre COMPLETO del paciente
4. Fecha de atención (formato DD/MM/YYYY)
5. EPS del paciente (solo EPS, no IPS)
6. Nombre del doctor tal como aparece
7. Lista detallada de TODOS los medicamentos con sus dosis, exactamente como aparecen en la formula
8. Diagnóstico o condición médica si aparece

IMPORTANTE - Extrae ABSOLUTAMENTE TODOS los medicamentos y sus dosis como están escritos en la fórmula. No omitas ninguno aunque no esté en una lista predefinida.

Si algún campo no se puede leer, indica "No visible".

Devuelve un objeto JSON con esta estructura exacta:
{
  "datos": {
    "tipo_documento": "tipo de documento (CC, TI, etc.)",
    "numero_documento": "número del documento",
    "paciente": "nombre completo del paciente",
    "fecha_atencion": "fecha de atención",
    "eps": "eps del paciente",
    "doctor": "nombre del doctor",
    "diagnostico": "diagnóstico médico si está visible",
    "medicamentos": ["medicamento 1 con dosis completa", "medicamento 2 con dosis completa", "etc"]
  }
}

Asegúrate de incluir todos los medicamentos visibles en la imagen, sin excepción."""

        response = client.chat.completions.create(
            model="o4-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000
        )
        
        response_text = response.choices[0].message.content
        
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if not json_match:
            raise ValueError("No se encontró un formato JSON válido")
        
        json_data = json.loads(json_match.group(0))
        
        if "datos" not in json_data:
            raise ValueError("Estructura JSON incorrecta")
        
        datos = json_data["datos"]
        
        if not isinstance(datos.get("medicamentos", []), list):
            if isinstance(datos.get("medicamentos"), str):
                datos["medicamentos"] = [datos["medicamentos"]]
            else:
                datos["medicamentos"] = ["No se detectaron medicamentos"]
        
        if (len(datos.get("medicamentos", [])) == 0 or
                (len(datos.get("medicamentos", [])) == 1 and 
                 datos["medicamentos"][0] == "No se detectaron medicamentos")):
            raise ValueError("No se detectaron medicamentos en la fórmula")
        
        return {"datos": datos}
        
    except Exception as e:
        logger.error(f"Error en process_medical_formula: {e}")
        raise
        
async def ask_openai(system_prompt: str, messages: List[Dict[str, str]], 
                     max_tokens: int = 400, temperature: float = 0.7) -> str:
  
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        formatted_messages = [{"role": "system", "content": system_prompt}]
        
        for msg in messages:
            formatted_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        response = client.chat.completions.create(
            model="o4-mini",
            messages=formatted_messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        return response.choices[0].message.content
    
    except Exception as e:
        logger.error(f"Error en ask_openai: {e}")
        return "Lo siento, tuve un problema al procesar tu mensaje. ¿Podrías intentarlo de nuevo?"

class SystemPromptGenerator:

    def __init__(self, user_session: Dict[str, Any]):
       
        self.user_session = user_session
        
    def generate(self) -> str:
        
        user_data = self.user_session["data"]
        
        current_step = str(user_data["current_step"]).split('.')[-1] if user_data.get("current_step") else "INICIO"
        
        system_prompt = f"""Eres un asistente conversacional llamado "No Me Entregaron", un servicio en Telegram que ayuda a las personas a radicar quejas cuando sus EPS no les entregan medicamentos. Tu personalidad es AMABLE, EMPÁTICA y ÚTIL. Hablas de manera NATURAL, evitando sonar robótico.

DATOS DEL USUARIO:
- Nombre: {user_data.get("name", "No disponible")}
- Ciudad: {user_data.get("city", "No disponible")}
- EPS: {user_data.get("eps", "No disponible")}
- Fórmula leída: {"Sí" if user_data.get("formula_data") else "No"}
- Medicamentos no entregados: {user_data.get("missing_meds", "No reportado")}
- Fecha de nacimiento: {user_data.get("birth_date", "No disponible")}
- Régimen: {user_data.get("affiliation_regime", "No disponible")}
- Dirección: {user_data.get("residence_address", "No disponible")}
- Farmacia: {user_data.get("pharmacy", "No disponible")}
- Celular: {user_data.get("cellphone", "No disponible")}

PASO ACTUAL EN LA CONVERSACIÓN: {current_step}

INSTRUCCIONES CRUCIALES:

1. SOBRE FÓRMULA MÉDICA PERDIDA:
   Cuando el usuario mencione EXPLÍCITAMENTE que no tiene o perdió la fórmula médica, proporciona opciones útiles.
   NUNCA ofrezcas estas opciones a menos que el usuario te indique específicamente que no tiene la fórmula.
   SIEMPRE comienza pidiendo la foto de la fórmula, y solo ofrece alternativas si el usuario dice que no la tiene.

2. PREGUNTAS "PARA QUÉ" O "POR QUÉ":
   Cuando el usuario pregunte "¿Para qué necesitas [dato]?", explica brevemente el propósito y SIEMPRE vuelve a solicitar la información:
   
   • Ciudad: "Necesito tu ciudad para identificar la jurisdicción correcta de la EPS. Esto asegura que tu queja llegue al departamento adecuado. Entonces, ¿en qué ciudad estás ubicado/a?"
   
   • Celular: "Tu número de celular es necesario para poder contactarte sobre el estado de tu queja y para que la EPS pueda comunicarse contigo si necesitan información adicional. ¿Podrías proporcionarme tu número de celular?"
   
   • Fecha de nacimiento: "La fecha de nacimiento es un dato obligatorio para el trámite oficial ante la EPS. Lo requieren para validar tu identidad en su sistema. Por favor, ¿podrías compartirme tu fecha de nacimiento?"
   
   • Régimen: "El régimen (contributivo o subsidiado) es importante porque los procedimientos varían según el tipo de afiliación. Así que, ¿cuál es tu régimen de afiliación?"
   
   • Dirección: "Tu dirección es necesaria para que la EPS pueda enviarte notificaciones oficiales y verificar tu zona de cobertura. ¿Podrías indicarme tu dirección de residencia?"
   
   • Farmacia: "Necesitamos identificar exactamente dónde no te entregaron los medicamentos para que la queja sea precisa. ¿En qué farmacia ocurrió el problema?"

3. CORRECCIONES:
   Cuando el usuario diga algo como "Me equivoqué" o "No es [dato] sino [nuevo dato]", SIEMPRE:
   
   a) Confirma explícitamente que entendiste la corrección: "Entendido, he actualizado [dato] a [nuevo dato]."
   b) Luego continúa con la siguiente pregunta pendiente según el flujo.
   
   Ejemplos:
   Usuario: "Me equivoqué, estoy en Cali, no en Medellín"
   TÚ: "¡No hay problema! He actualizado tu ciudad de Medellín a Cali. Ahora, necesito [siguiente dato que falte]..."

4. SOBRE PREGUNTAS FUERA DEL FLUJO:
   Si el usuario pregunta algo no relacionado pero relevante (como "¿cuánto tarda el proceso?"), responde brevemente y SIEMPRE vuelve al punto donde estabas:
   
   "El proceso de radicación toma aproximadamente 24 horas hábiles, y la EPS suele responder en 5-15 días. Volviendo a nuestra queja, necesito saber [siguiente dato pendiente]..."

5. GUÍA COMPLETA DEL FLUJO DE CONVERSACIÓN:
   El proceso de queja sigue estos pasos en orden:
   
   a) Solicitar foto de la fórmula médica
   b) Preguntar qué medicamentos no fueron entregados
   c) Solicitar ciudad de residencia
   d) Solicitar número de celular
   e) Solicitar fecha de nacimiento
   f) Solicitar régimen de afiliación (Contributivo o Subsidiado)
   g) Solicitar dirección de residencia
   h) Solicitar nombre de la farmacia
   i) Confirmar que la queja será tramitada

   Para cada paso, usa un tono conversacional y empático.

6. RESUMEN DE CIERRE:
   Cuando hayas recopilado TODOS los datos necesarios, proporciona un resumen y confirma que la queja será tramitada:
   
   "¡Perfecto! He registrado toda la información necesaria para tu queja:
   • Medicamento(s) no entregado(s): [medicamentos]
   • Farmacia: [farmacia] en [ciudad]
   
   En las próximas 24 horas tramitaremos tu queja ante la EPS y te enviaré el número de radicado por este mismo chat. ¿Hay algo más en lo que pueda ayudarte?"

NOTA IMPORTANTE: Si el usuario hace preguntas médicas, aclara amablemente que no eres un profesional de la salud y recomienda consultar con su médico o EPS.

Recuerda: SÉ CONVERSACIONAL y NATURAL. Usa un lenguaje sencillo, como si estuvieras chateando con un amigo. Incluye algunos emojis ocasionalmente para dar calidez. No uses frases robóticas o demasiado formales.