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

            # Llamamos a la API de OpenAI sin especificar el límite de tokens
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
                # Eliminamos el parámetro max_tokens/max_completion_tokens
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