import os
import json
import logging
import re
from typing import Dict, Any, List
from openai import OpenAI

from core.prompt_generator import SystemPromptGenerator

logger = logging.getLogger(__name__)

class OpenAIService:
    def __init__(self, api_key: str = None):
        
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key)
    
    async def ask_openai(self, system_prompt: str, messages: List[Dict[str, str]], 
                         temperature: float = 1.0) -> str:
        
        try:
            formatted_messages = [{"role": "system", "content": system_prompt}]
            
            for msg in messages:
                formatted_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Usando un valor más alto de temperature para mayor naturalidad
            response = self.client.chat.completions.create(
                model="o4-mini",
                messages=formatted_messages,
                temperature=temperature
            )
            
            return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"Error en ask_openai: {e}")
            return "Lo siento, tuve un problema al procesar tu mensaje. ¿Podrías intentarlo de nuevo?"