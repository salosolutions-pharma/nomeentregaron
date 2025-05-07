import os
import time
import logging
import re
from typing import Dict, Any
from google.cloud import bigquery
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

class BigQueryService:
    def __init__(self, project_id: str = None, dataset_id: str = None, table_id: str = None, credentials_path: str = None):
        
        self.project_id = project_id or os.getenv('BIGQUERY_PROJECT_ID')
        self.dataset_id = dataset_id or os.getenv('BIGQUERY_DATASET_ID', 'solutions2pharma_data')
        self.table_id = table_id or os.getenv('BIGQUERY_TABLE_ID', 'quejas')
        
        try:
            if credentials_path and os.path.exists(credentials_path):
                # Usar credenciales desde archivo para Windows
                logger.info(f"Usando credenciales desde archivo: {credentials_path}")
                credentials = service_account.Credentials.from_service_account_file(credentials_path)
                self.client = bigquery.Client(project=self.project_id, credentials=credentials)
            else:
                # Intentar usar credenciales del ambiente
                logger.info("Usando credenciales del ambiente")
                self.client = bigquery.Client(project=self.project_id)
                
            # Verificar conexión con BigQuery
            self._verificar_conexion()
        except Exception as e:
            logger.error(f"Error al inicializar el cliente BigQuery: {e}")
            raise
    
    def _verificar_conexion(self):
        """Verifica que la conexión a BigQuery esté funcionando y que la tabla exista"""
        try:
            table_ref = f"{self.project_id}.{self.dataset_id}.{self.table_id}"
            self.client.get_table(table_ref)
            logger.info(f"✅ Conexión a BigQuery verificada. Tabla {table_ref} accesible.")
        except Exception as e:
            logger.error(f"⚠️ Error verificando conexión a BigQuery: {e}")
            raise
        
    async def save_user_data(self, user_data: Dict[str, Any], force_save: bool = False) -> bool:
        try:
            # Comprobar si tenemos los datos mínimos necesarios
            datos_obligatorios_completos = (
                user_data.get("formula_data") and
                user_data.get("missing_meds") and
                user_data.get("missing_meds") != "[aún no especificado]"
            )

            if not datos_obligatorios_completos and not force_save:
                logger.info("Datos incompletos, no se guarda en BigQuery todavía")
                return False

            logger.info("Preparando datos para BigQuery...")

            # Formatear fecha de atención
            fecha_atencion = None
            if user_data.get("formula_data", {}).get("fecha_atencion"):
                fecha_parts = user_data["formula_data"]["fecha_atencion"].split('/')
                if len(fecha_parts) == 3:
                    dia, mes, anio = fecha_parts
                    fecha_atencion = f"{anio}-{mes.zfill(2)}-{dia.zfill(2)}"

            nombre_paciente = user_data.get("formula_data", {}).get("paciente", "No disponible")
            logger.info(f"Nombre del paciente desde la fórmula: {nombre_paciente}")
            
            # Limpiar los datos antes de guardarlos
            city = user_data.get("city", "")
            if city.lower() in ["contributivo", "subsidiado", "ese fue"]:
                city = "No disponible"
            
            pharmacy = user_data.get("pharmacy", "")
            # Limpiar valores de farmacia
            pharmacy = re.sub(r'donde.*te|y la sede donde|donde no te|sede|y\s+debían|debían', '', pharmacy, flags=re.I).strip()
            if not pharmacy or pharmacy.lower() in ["y", "la", "el", "los", "las", "donde"]:
                pharmacy = "No disponible"
            
            logger.info(f"Ciudad original: {user_data.get('city', '')}, Ciudad limpia: {city}")
            logger.info(f"Farmacia original: {user_data.get('pharmacy', '')}, Farmacia limpia: {pharmacy}")
            
            # Crear un ID único para la queja si no existe
            if not user_data.get("queja_actual", {}).get("id"):
                user_data["queja_actual"] = {
                    "id": f"{user_data.get('user_id', 'unknown')}_{int(time.time())}",
                    "guardada": False
                }

            # Verificar si la queja ya fue guardada
            if user_data.get("queja_actual", {}).get("guardada", False):
                logger.info(f"La queja {user_data['queja_actual']['id']} ya fue guardada anteriormente.")
                return True
            
            # Preparar fila para inserción con valores depurados
            row = {
                "PK": user_data["queja_actual"]["id"],
                "tipo_documento": user_data.get("formula_data", {}).get("tipo_documento", "No disponible"),
                "numero_documento": user_data.get("formula_data", {}).get("numero_documento", "No disponible"),
                "paciente": nombre_paciente,
                "fecha_atencion": fecha_atencion,
                "eps": user_data.get("formula_data", {}).get("eps", "No disponible"),
                "doctor": user_data.get("formula_data", {}).get("doctor", "No disponible"),
                "ips": user_data.get("formula_data", {}).get("ips", "No disponible"),
                "diagnostico": user_data.get("formula_data", {}).get("diagnostico", "No disponible"),
                "medicamentos": ", ".join(user_data.get("formula_data", {}).get("medicamentos", [])) or "No disponible",
                "image_url": "",
                "no_entregado": user_data.get("missing_meds", "No especificado"),
                "fecha_nacimiento": user_data.get("birth_date", "No disponible"),
                "telefono": user_data.get("cellphone", user_data.get("user_id", "No disponible")),
                "regimen": user_data.get("affiliation_regime", "No disponible"),
                # Usar los valores limpios
                "municipio": city,
                "direccion": user_data.get("residence_address", "No proporcionada"),
                "farmacia": pharmacy
            }
                
            table_ref = f"{self.project_id}.{self.dataset_id}.{self.table_id}"

            try:
                logger.info(f"Enviando datos a BigQuery con los campos: {list(row.keys())}")
                
                # Obtener referencia a la tabla
                table = self.client.get_table(table_ref)
                
                # Obtener esquema de la tabla
                schema_fields = [field.name for field in table.schema]
                logger.info(f"Campos en la tabla: {schema_fields}")
                
                # Filtrar campos que no existen en el esquema
                filtered_row = {k: v for k, v in row.items() if k in schema_fields}
                
                # Si se filtraron campos, registrar cuáles
                if len(filtered_row) != len(row):
                    removed_fields = set(row.keys()) - set(filtered_row.keys())
                    logger.warning(f"Se filtraron campos que no existen en el esquema: {removed_fields}")
                
                # Realizar una última verificación de valores inválidos
                for key, value in filtered_row.items():
                    if isinstance(value, str) and (not value.strip() or value.strip() in ["y", "la", "el", "los", "las"]):
                        filtered_row[key] = "No disponible"
                
                # Insertar datos filtrados
                logger.info("Ejecutando inserción en BigQuery...")
                logger.info(f"Farmacia final: {filtered_row.get('farmacia', 'No disponible')}")
                logger.info(f"Municipio final: {filtered_row.get('municipio', 'No disponible')}")
                
                errors = self.client.insert_rows_json(table, [filtered_row])
                
                if not errors:
                    user_data["queja_actual"]["guardada"] = True
                    logger.info("✅ Datos guardados exitosamente en BigQuery!")
                    
                    # Guardar esta queja en el historial general
                    if "quejas_anteriores" not in user_data:
                        user_data["quejas_anteriores"] = []
                        
                    user_data["quejas_anteriores"].append({
                        "id": user_data["queja_actual"]["id"],
                        "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "paciente": nombre_paciente,
                        "medicamentos": user_data.get("missing_meds", "")
                    })
                    
                    # Guardar información en el historial del paciente
                    paciente_id = user_data.get("formula_data", {}).get("numero_documento", "")
                    
                    if paciente_id:
                        if "patient_history" not in user_data:
                            user_data["patient_history"] = {}
                            
                        if paciente_id not in user_data["patient_history"]:
                            user_data["patient_history"][paciente_id] = {
                                "nombre": nombre_paciente,
                                "quejas": []
                            }
                        
                        # Guardar esta queja en el historial del paciente
                        user_data["patient_history"][paciente_id]["quejas"].append({
                            "id": user_data["queja_actual"]["id"],
                            "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "medicamentos": user_data.get("missing_meds", ""),
                            "eps": user_data.get("formula_data", {}).get("eps", ""),
                            "diagnostico": user_data.get("formula_data", {}).get("diagnostico", "")
                        })
                        
                        logger.info(f"✅ Historial de paciente actualizado para: {nombre_paciente}")

                    return True
                else:
                    logger.error(f"❌ Errores al insertar en BigQuery: {errors}")
                    return False
                    
            except Exception as error:
                logger.error(f'❌ Error guardando en BigQuery: {error}')
                import traceback
                logger.error(traceback.format_exc())
                return False
        except Exception as e:
            logger.error(f'Error general preparando datos para BigQuery: {e}')
            import traceback
            logger.error(traceback.format_exc())
            return False