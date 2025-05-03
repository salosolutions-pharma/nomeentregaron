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
        except Exception as e:
            logger.error(f"Error al inicializar el cliente BigQuery: {e}")
            raise
        
    async def save_user_data(self, user_data: Dict[str, Any], force_save: bool = False) -> bool:
        
        try:
            datos_obligatorios_completos = (
                user_data.get("formula_data") and
                user_data.get("missing_meds") and
                user_data.get("missing_meds") != "[aún no especificado]"
            )

            if not datos_obligatorios_completos and not force_save:
                logger.info("Datos incompletos, no se guarda en BigQuery todavía")
                return False

            logger.info("Preparando datos para BigQuery...")

            fecha_atencion = None
            if user_data.get("formula_data", {}).get("fecha_atencion"):
                fecha_parts = user_data["formula_data"]["fecha_atencion"].split('/')
                if len(fecha_parts) == 3:
                    dia, mes, anio = fecha_parts
                    fecha_atencion = f"{anio}-{mes.zfill(2)}-{dia.zfill(2)}"

            nombre_paciente = user_data.get("formula_data", {}).get("paciente", "No disponible")
            logger.info(f"Nombre del paciente desde la fórmula: {nombre_paciente}")

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
                "municipio": user_data.get("city", "No disponible"),
                "direccion": user_data.get("residence_address", "No disponible"),
                "farmacia": user_data.get("pharmacy", "No disponible")
            }

            if user_data["queja_actual"].get("guardada", False):
                logger.info(f"La queja {user_data['queja_actual']['id']} ya fue guardada anteriormente.")
                return True
                
            table_ref = f"{self.project_id}.{self.dataset_id}.{self.table_id}"

            try:
                logger.info(f"Enviando datos a BigQuery con los campos: {list(row.keys())}")
                logger.info(f"Datos que se enviarán: {row}")
                
                table = self.client.get_table(table_ref)
                errors = self.client.insert_rows_json(table, [row])
                
                if not errors:
                    user_data["queja_actual"]["guardada"] = True
                    user_data["quejas_anteriores"].append({
                        "id": user_data["queja_actual"]["id"],
                        "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "paciente": nombre_paciente,
                        "medicamentos": user_data.get("missing_meds", "")
                    })

                    logger.info(f"✅ Datos guardados correctamente en BigQuery para el paciente: {nombre_paciente}")
                    return True
                else:
                    logger.error(f"❌ Errores al insertar en BigQuery: {errors}")
                    return False

            except Exception as error:
                logger.error(f'❌ Error guardando en BigQuery: {error}')
                
                if hasattr(error, 'errors'):
                    problematicos = []
                    for err in getattr(error, 'errors', []):
                        for detail in getattr(err, 'errors', []):
                            match = re.search(r"no such field: ([^.]+)", getattr(detail, 'message', ''))
                            if match and match.group(1):
                                problematicos.append(match.group(1))
                    
                    if problematicos:
                        logger.error(f"Campos problemáticos detectados: {', '.join(problematicos)}")
                        
                        for campo in problematicos:
                            if campo in row:
                                del row[campo]
                        
                        logger.info("Reintentando con campos corregidos:", list(row.keys()))
                        
                        try:
                            errors = self.client.insert_rows_json(table, [row])
                            if not errors:
                                user_data["queja_actual"]["guardada"] = True
                                logger.info("✅ Datos guardados en la tabla después de corrección")
                                return True
                            else:
                                logger.error(f"❌ Error en segundo intento: {errors}")
                        except Exception as retry_error:
                            logger.error(f'❌ Error en segundo intento: {retry_error}')
                
                return False
        except Exception as e:
            logger.error(f'Error general preparando datos para BigQuery: {e}')
            return False