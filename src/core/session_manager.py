import time
import logging
from typing import Dict, Any
from config import ConversationSteps

logger = logging.getLogger(__name__)

user_sessions: Dict[str, Dict[str, Any]] = {}

def get_user_session(user_id: str) -> Dict[str, Any]:
    
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "session_id": f"telegram-session-{user_id}-{int(time.time())}",
            "data": {
                "user_id": user_id,
                "name": "",  # Se actualizará con el nombre del paciente de la fórmula
                "city": "",
                "eps": "",
                "consented": False,
                "formula_data": None,
                "missing_meds": None,
                "pending_media": None,
                "conversation_history": [],
                "last_interaction": time.time(),
                "current_step": ConversationSteps.INICIO,
                "awaiting_approval": False,
                "context_variables": {},
                "is_first_interaction": True,  # Add this flag
                "has_greeted": False,
                "summary_shown": False,
                "last_processed_time": None,
                
                "cellphone": "",
                "birth_date": "",
                "affiliation_regime": "",
                "residence_address": "",
                "pharmacy": "",
                "pharmacy_branch": "",
                
                "data_collected": {
                    "ciudad": False,
                    "fecha_nacimiento": False,
                    "regimen": False,
                    "direccion": False,
                    "farmacia": False,
                    "celular": False
                },
                
                "queja_actual": {
                    "id": f"{user_id}_{int(time.time())}",
                    "guardada": False
                },
                "quejas_anteriores": [],
                "patient_history": {}  # Para almacenar historial por paciente
            }
        }
        logger.info(f"Nueva sesión creada para {user_id}: {user_sessions[user_id]['session_id']}")
    else:
        user_sessions[user_id]["data"]["last_interaction"] = time.time()
    
    return user_sessions[user_id]

def reset_session(user_session: Dict[str, Any]) -> None:
    
    previous_user_id = user_session["data"]["user_id"]
    previous_name = user_session["data"]["name"]
    previous_conversation_history = user_session["data"]["conversation_history"]
    previous_quejas = user_session["data"]["quejas_anteriores"] or []
    previous_patient_history = user_session["data"].get("patient_history", {})

    user_session["data"] = {
        "user_id": previous_user_id,
        "name": previous_name,  # Mantener el nombre previo (si existe)
        "city": "",
        "eps": "",
        "consented": True,
        "formula_data": None,
        "missing_meds": None,
        "pending_media": None,
        "conversation_history": previous_conversation_history,
        "last_interaction": time.time(),
        "current_step": ConversationSteps.ESPERANDO_FORMULA,
        "awaiting_approval": False,
        "context_variables": {},
        "has_greeted": True,
        "summary_shown": False,
        "last_processed_time": time.time(),
        
        "cellphone": "",
        "birth_date": "",
        "affiliation_regime": "",
        "residence_address": "",
        "pharmacy": "",
        "pharmacy_branch": "",
        
        "data_collected": {
            "ciudad": False,
            "fecha_nacimiento": False,
            "regimen": False,
            "direccion": False,
            "farmacia": False,
            "celular": False
        },
        
        "queja_actual": {
            "id": f"{previous_user_id}_{int(time.time())}",
            "guardada": False
        },
        "quejas_anteriores": previous_quejas,
        "patient_history": previous_patient_history  # Mantener el historial de pacientes
    }

def iniciar_nueva_queja(user_session: Dict[str, Any], user_id: str) -> None:
    """Reinicia los datos para una nueva queja manteniendo la información básica del usuario"""
    
    # Guardar la queja actual en el historial si existe
    if user_session["data"].get("formula_data") and not user_session["data"]["queja_actual"].get("guardada", False):
        if "quejas_anteriores" not in user_session["data"]:
            user_session["data"]["quejas_anteriores"] = []
        user_session["data"]["quejas_anteriores"].append(user_session["data"]["queja_actual"])
    
    # Guardamos el nombre del paciente actual antes de reiniciar
    previous_name = user_session["data"].get("name", "")
    
    # Reiniciamos para una nueva queja
    user_session["data"]["queja_actual"] = {
        "id": f"{user_id}_{int(time.time())}",
        "guardada": False
    }

    user_session["data"]["city"] = ''
    user_session["data"]["eps"] = ''
    user_session["data"]["formula_data"] = None
    user_session["data"]["missing_meds"] = None
    user_session["data"]["current_step"] = ConversationSteps.ESPERANDO_FORMULA
    user_session["data"]["summary_shown"] = False
    user_session["data"]["birth_date"] = ''
    user_session["data"]["affiliation_regime"] = ''
    user_session["data"]["residence_address"] = ''
    user_session["data"]["pharmacy"] = ''
    user_session["data"]["pharmacy_branch"] = ''
    user_session["data"]["cellphone"] = ''
    user_session["data"]["data_collected"] = {
        "ciudad": False,
        "fecha_nacimiento": False,
        "regimen": False,
        "direccion": False,
        "farmacia": False,
        "celular": False
    }
    user_session["data"]["last_interaction"] = time.time()
    
    # Restauramos el nombre del paciente si teníamos uno
    if previous_name:
        user_session["data"]["name"] = previous_name

def actualizar_datos_contexto(user_session: Dict[str, Any], tipo: str, valor: str) -> None:
    
    if not valor or not valor.strip():
        return
    
    logger.info(f"Actualizando {tipo}: {valor}")
    
    data = user_session["data"]
    
    if tipo == "ciudad":
        data["city"] = valor
    elif tipo == "farmacia":
        data["pharmacy"] = valor
    elif tipo == "direccion":
        data["residence_address"] = valor
    elif tipo == "regimen":
        data["affiliation_regime"] = valor
    elif tipo == "fechaNacimiento":
        data["birth_date"] = valor
    elif tipo == "medicamentos":
        data["missing_meds"] = valor
    elif tipo == "celular":
        data["cellphone"] = valor
    else:
        logger.warning(f"Tipo de dato no reconocido: {tipo}")