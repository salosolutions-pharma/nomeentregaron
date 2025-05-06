import re
import time
import logging
from typing import Dict, Any, Optional, List
from config import ConversationSteps
from core.session_manager import actualizar_datos_contexto

logger = logging.getLogger(__name__)

class DataExtractor:
    
    @staticmethod
    def extraer_datos_de_respuesta(respuesta: str, user_session: Dict[str, Any]) -> None:
        """Extrae datos estructurados de la respuesta generada por OpenAI"""
        
        # Detectar si se ha completado el proceso
        if ("próximas" in respuesta.lower() and 
            "horas" in respuesta.lower() and 
            "tramitaremos" in respuesta.lower() and 
            "queja" in respuesta.lower()):
            user_session["data"]["current_step"] = ConversationSteps.COMPLETADO
            logger.info("Conversación marcada como COMPLETADA")
            
        # Extraer datos usando procesamiento de lenguaje natural
        DataExtractor._extraer_datos_con_patrones(respuesta, user_session)
    
    @staticmethod
    def extraer_datos_de_mensaje_usuario(texto: str, user_session: Dict[str, Any]) -> None:
        """Extrae información relevante del mensaje del usuario"""
        
        # Procesar medicamentos no entregados si estamos en ese paso
        if user_session["data"]["current_step"] == ConversationSteps.ESPERANDO_MEDICAMENTOS:
            medicamentos_array = user_session["data"]["context_variables"].get("medicamentos_array", [])
            
            # Si no hay medicamentos para seleccionar, no hacemos nada
            if not medicamentos_array:
                return
                
            # Detectar si mencionó medicamentos específicos o "todos"/"ninguno"
            DataExtractor._procesar_seleccion_medicamentos(texto, medicamentos_array, user_session)
        
        # Extraer otros datos relevantes (ciudad, teléfono, etc.)
        DataExtractor._extraer_datos_con_patrones(texto, user_session)
    
    @staticmethod
    def _extraer_datos_con_patrones(texto: str, user_session: Dict[str, Any]) -> None:
        """Utiliza expresiones regulares para extraer datos específicos"""
        
        # Diccionario de patrones y sus campos correspondientes
        patrones = {
            "ciudad": r"(?:ciudad|estás en|vives en|ubicad[oa] en)[:\s]+([A-Za-zÁáÉéÍíÓóÚúÜüÑñ\s]+?)(?:\.|\!|\n|,)",
            "celular": r"(?:celular|teléfono|número)[:\s]+([0-9+\s()-]+?)(?:\.|\!|\n|,)",
            "farmacia": r"(?:farmacia)[:\s]+([A-Za-zÁáÉéÍíÓóÚúÜüÑñ\s0-9]+?)(?:\.|\!|\n|,|en)",
            "direccion": r"(?:dirección)[:\s]+([A-Za-zÁáÉéÍíÓóÚúÜüÑñ\s0-9#\-\.]+?)(?:\.|\!|\n|,)",
            "regimen": r"(?:régimen|afiliación)[:\s]+(Contributivo|Subsidiado)",
            "medicamentos": r"(?:medicamentos? no entregados?)[:\s]+(.+?)(?:\.|\!|\n|,)",
            "fecha_nacimiento": r"(?:nacimiento|nació)[:\s]+(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})"
        }
        
        # Buscar cada patrón en el texto
        for campo, patron in patrones.items():
            match = re.search(patron, texto, re.I)
            if match and match.group(1) and len(match.group(1).strip()) > 2:
                valor = match.group(1).strip()
                
                # Mapeo de campos al formato esperado por actualizar_datos_contexto
                campo_map = {
                    "ciudad": "ciudad",
                    "celular": "celular",
                    "farmacia": "farmacia",
                    "direccion": "direccion",
                    "regimen": "regimen",
                    "medicamentos": "medicamentos",
                    "fecha_nacimiento": "fechaNacimiento"
                }
                
                actualizar_datos_contexto(user_session, campo_map[campo], valor)
        
        # Extraer ciudad directamente si parece ser solo un nombre de ciudad
        ciudad_simple = re.match(r"^([A-Za-zÁáÉéÍíÓóÚúÜüÑñ\s]{3,})$", texto.strip())
        if (ciudad_simple and 
            user_session["data"]["current_step"] == ConversationSteps.ESPERANDO_CIUDAD and
            not user_session["data"].get("city")):
            actualizar_datos_contexto(user_session, "ciudad", ciudad_simple.group(1).strip())
        
        # Extraer número de teléfono directo
        telefono_directo = re.search(r"\b(\d{10})\b", texto)
        if telefono_directo:
            actualizar_datos_contexto(user_session, "celular", telefono_directo.group(1))
        
        # Buscar fechas en formato más flexible
        fecha = DataExtractor.extraer_fecha(texto)
        if fecha:
            actualizar_datos_contexto(user_session, "fechaNacimiento", fecha)
            
        # Identificar régimen directamente mencionado
        if "contributivo" in texto.lower():
            actualizar_datos_contexto(user_session, "regimen", "Contributivo")
        elif "subsidiado" in texto.lower():
            actualizar_datos_contexto(user_session, "regimen", "Subsidiado")
            
        # Detectar correcciones explícitas
        correccion = re.search(r"me equivoqu[eé][\s,]*([^,]+) es ([^\.]+)", texto, re.I)
        if correccion:
            campo = correccion.group(1).lower().strip()
            nuevo_valor = correccion.group(2).strip()
            
            if "ciudad" in campo or "vivo" in campo:
                actualizar_datos_contexto(user_session, "ciudad", nuevo_valor)
            elif "celular" in campo or "teléfono" in campo or "numero" in campo or "número" in campo:
                actualizar_datos_contexto(user_session, "celular", nuevo_valor)
            elif "direccion" in campo or "dirección" in campo or "vivo" in campo:
                actualizar_datos_contexto(user_session, "direccion", nuevo_valor)
            elif "farmacia" in campo:
                actualizar_datos_contexto(user_session, "farmacia", nuevo_valor)
            elif "nacimiento" in campo or "nací" in campo:
                fecha_corregida = DataExtractor.extraer_fecha(nuevo_valor)
                if fecha_corregida:
                    actualizar_datos_contexto(user_session, "fechaNacimiento", fecha_corregida)
            elif "regimen" in campo or "régimen" in campo:
                if "contributivo" in nuevo_valor.lower():
                    actualizar_datos_contexto(user_session, "regimen", "Contributivo")
                elif "subsidiado" in nuevo_valor.lower():
                    actualizar_datos_contexto(user_session, "regimen", "Subsidiado")
    
    @staticmethod
    def _procesar_seleccion_medicamentos(texto: str, medicamentos_array: list, user_session: Dict[str, Any]) -> None:
        """Procesa la selección de medicamentos no entregados"""
        texto_lower = texto.lower().strip()
        
        # Detectar "ninguno" o "todos" - ambos significan que no entregaron ninguno
        if (texto_lower in ["ninguno", "ninguna", "ningun", "ningún", "todos", "todo"] or 
            "no me entregaron ninguno" in texto_lower or 
            "todos los" in texto_lower or 
            "no me entregaron nada" in texto_lower):
            
            todos_los_medicamentos = ", ".join(medicamentos_array)
            actualizar_datos_contexto(user_session, "medicamentos", todos_los_medicamentos)
            return
        
        # Detectar números
        numeros_encontrados = re.findall(r"(\d+)", texto_lower)
        if numeros_encontrados:
            medicamentos_seleccionados = []
            for num in numeros_encontrados:
                index = int(num) - 1
                if 0 <= index < len(medicamentos_array):
                    medicamentos_seleccionados.append(medicamentos_array[index])
            
            if medicamentos_seleccionados:
                medicamentos_faltantes = ", ".join(medicamentos_seleccionados)
                actualizar_datos_contexto(user_session, "medicamentos", medicamentos_faltantes)
                return
        
        # Detectar nombres de medicamentos
        medicamentos_mencionados = []
        for med in medicamentos_array:
            # Extraer el nombre base del medicamento
            nombre_base = re.split(r'[\(\d]', med)[0].strip().lower()
            palabras_clave = nombre_base.split()
            
            # Verificar si alguna palabra clave del medicamento está en el texto
            if any(palabra.lower() in texto_lower for palabra in palabras_clave if len(palabra) > 3):
                medicamentos_mencionados.append(med)
        
        if medicamentos_mencionados:
            medicamentos_faltantes = ", ".join(medicamentos_mencionados)
            actualizar_datos_contexto(user_session, "medicamentos", medicamentos_faltantes)
    
    @staticmethod
    def extraer_fecha(texto: str) -> Optional[str]:
        """Extrae una fecha del texto en varios formatos posibles"""
        
        # Formato DD/MM/AAAA o DD-MM-AAAA
        formato_slash = re.search(r"(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})", texto)
        
        # Formato "DD de Mes de AAAA" o "DD de Mes"
        formato_texto = re.search(r"(\d{1,2})\s+de\s+([a-zñáéíóú]+)(?:\s+de\s+)?(\d{4})?", texto, re.I)
        
        # Formato "Mes DD, AAAA" o "Mes DD"
        formato_invertido = re.search(r"([a-zñáéíóú]+)\s+(\d{1,2})(?:,?\s+)?(\d{4})?", texto, re.I)
        
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
        
        if formato_invertido:
            mes_texto = formato_invertido.group(1).lower()
            dia = formato_invertido.group(2).zfill(2)
            anio = formato_invertido.group(3) or str(time.localtime().tm_year)
            
            meses = {
                'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04',
                'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
                'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12'
            }
            
            for nombre, numero in meses.items():
                if nombre in mes_texto:
                    return f"{dia}/{numero}/{anio}"
        
        return None
    
    @staticmethod
    async def procesar_seleccion_medicamentos(text: str, user_session: Dict[str, Any]) -> Dict[str, Any]:
        """Procesa la selección de medicamentos no entregados por parte del usuario"""
        
        text_lower = text.lower().strip()
        medicamentos_array = user_session["data"]["context_variables"].get("medicamentos_array", [])
        
        if not medicamentos_array:
            return {"exito": False, "mensaje": "No hay medicamentos para seleccionar"}
        
        # Detectar "todos" o "ninguno"
        if text_lower in ["ninguno", "ninguna", "ningun", "ningún"] or "no me entregaron ninguno" in text_lower:
            todos_los_medicamentos = ", ".join(medicamentos_array)
            actualizar_datos_contexto(user_session, "medicamentos", todos_los_medicamentos)
            return {
                "exito": True,
                "mensaje": "Entiendo que no te entregaron ninguno de los medicamentos recetados."
            }
        
        if text_lower in ["todos", "todo"] or "todos los" in text_lower or "no me entregaron nada" in text_lower:
            todos_los_medicamentos = ", ".join(medicamentos_array)
            actualizar_datos_contexto(user_session, "medicamentos", todos_los_medicamentos)
            return {
                "exito": True,
                "mensaje": "Entiendo que no te entregaron ninguno de los medicamentos recetados."
            }
        
        # Detectar números
        numeros_encontrados = re.findall(r"(\d+)", text_lower)
        if numeros_encontrados:
            medicamentos_seleccionados = []
            for num in numeros_encontrados:
                index = int(num) - 1
                if 0 <= index < len(medicamentos_array):
                    medicamentos_seleccionados.append(medicamentos_array[index])
            
            if medicamentos_seleccionados:
                medicamentos_faltantes = ", ".join(medicamentos_seleccionados)
                actualizar_datos_contexto(user_session, "medicamentos", medicamentos_faltantes)
                return {
                    "exito": True,
                    "mensaje": f"Entiendo, los medicamentos que no te entregaron son: {medicamentos_faltantes}."
                }
        
        # Detectar nombres de medicamentos
        medicamentos_mencionados = []
        for med in medicamentos_array:
            # Extraer el nombre base del medicamento (hasta el primer paréntesis o números)
            nombre_base = re.split(r'[\(\d]', med)[0].strip().lower()
            palabras_clave = nombre_base.split()
            
            # Verificar si alguna palabra clave del medicamento está en el texto
            if any(palabra.lower() in text_lower for palabra in palabras_clave if len(palabra) > 3):
                medicamentos_mencionados.append(med)
        
        if medicamentos_mencionados:
            medicamentos_faltantes = ", ".join(medicamentos_mencionados)
            actualizar_datos_contexto(user_session, "medicamentos", medicamentos_faltantes)
            return {
                "exito": True,
                "mensaje": f"Entiendo, los medicamentos que no te entregaron son: {medicamentos_faltantes}."
            }
        
        return {
            "exito": False,
            "mensaje": "No he podido identificar qué medicamentos no te entregaron. Por favor, especifica los medicamentos por su número o nombre."
        }