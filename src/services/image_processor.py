import os
import json
import logging
import re
import base64
from typing import Dict, Any
from openai import OpenAI

logger = logging.getLogger(__name__)

class ImageProcessor:
    def __init__(self, api_key: str = None):
       
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key)
    
    async def process_medical_formula(self, base64_image: str) -> Dict[str, Any]:
        
        try:
            logger.info("Procesando imagen con OpenAI Vision...")
            
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

RESPONDE ÚNICAMENTE CON UN OBJETO JSON CON EXACTAMENTE ESTA ESTRUCTURA:
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

No incluyas explicaciones, análisis ni texto adicional fuera del JSON. La respuesta debe ser únicamente el objeto JSON."""

            # Llamamos a la API de OpenAI 
            response = self.client.chat.completions.create(
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
                ]
            )
            
            response_text = response.choices[0].message.content
            logger.info(f"Respuesta de OpenAI Vision recibida. Longitud: {len(response_text)}")
            
            # Intenta encontrar un JSON válido en la respuesta
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if not json_match:
                # Si no encuentra JSON, intenta crear un JSON básico con los datos que podamos extraer
                logger.warning("No se encontró un formato JSON válido en la respuesta. Intentando extraer información manualmente.")
                
                # Patrones para extraer información básica
                paciente_match = re.search(r'paciente[:\s]+"([^"]+)"', response_text, re.I)
                medicamentos_match = re.findall(r'medicamento[s]?[:\s]+([^\n\."]+)', response_text, re.I)
                
                # Crear un JSON básico con la información que podamos extraer
                datos = {
                    "paciente": paciente_match.group(1) if paciente_match else "No visible",
                    "tipo_documento": "No visible",
                    "numero_documento": "No visible",
                    "fecha_atencion": "No visible",
                    "eps": "No visible",
                    "doctor": "No visible",
                    "diagnostico": "No visible",
                    "medicamentos": medicamentos_match if medicamentos_match else ["No se detectaron medicamentos"]
                }
                
                return {"datos": datos}
            
            # Si encontramos un JSON, lo analizamos
            try:
                json_data = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                # Si el JSON no es válido, intentamos limpiarlo
                cleaned_json = json_match.group(0).replace('\n', '').replace('\r', '')
                # Reemplazar dobles comillas dentro de valores
                cleaned_json = re.sub(r'(?<=":\s*"[^"]*)"(?=[^"]*")', '\\"', cleaned_json)
                json_data = json.loads(cleaned_json)
            
            if "datos" not in json_data:
                # Si el JSON no tiene la estructura esperada, la creamos
                if any(key in json_data for key in ["tipo_documento", "paciente", "medicamentos"]):
                    json_data = {"datos": json_data}
                else:
                    raise ValueError("Estructura JSON incorrecta")
            
            datos = json_data["datos"]
            
            # Asegurarnos de que medicamentos sea una lista
            if not isinstance(datos.get("medicamentos", []), list):
                if isinstance(datos.get("medicamentos"), str):
                    datos["medicamentos"] = [datos["medicamentos"]]
                else:
                    datos["medicamentos"] = ["No se detectaron medicamentos"]
            
            # Si no hay medicamentos detectados, añadir un mensaje genérico
            if (len(datos.get("medicamentos", [])) == 0 or
                    (len(datos.get("medicamentos", [])) == 1 and 
                    datos["medicamentos"][0] == "No se detectaron medicamentos")):
                datos["medicamentos"] = ["No se detectaron medicamentos claramente. Por favor, intenta con una foto más clara."]
            
            return {"datos": datos}
            
        except Exception as e:
            logger.error(f"Error en process_medical_formula: {e}")
            # Devolver datos básicos para que el bot pueda continuar
            return {
                "datos": {
                    "paciente": "No visible",
                    "tipo_documento": "No visible",
                    "numero_documento": "No visible",
                    "fecha_atencion": "No visible",
                    "eps": "No visible",
                    "doctor": "No visible",
                    "diagnostico": "No visible",
                    "medicamentos": ["No se pudo procesar la fórmula correctamente. Por favor, intenta con una foto más clara."]
                }
            }