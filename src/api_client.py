import json
import logging
import random
import time
from typing import Dict, Any
from urllib import request, error

from .config import GROQ_API_BASE_URL, GROQ_API_KEY, MODEL_NAME, HTTP_TIMEOUT, SYSTEM_PROMPT

def call_groq_api(context: str) -> Dict[str, Any]:
    """
    Envia o contexto para a API da Groq com retentativa e exponential backoff.
    """
    if not GROQ_API_KEY:
        raise ValueError("A variável de ambiente GROQ_API_KEY não está definida.")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context}
        ],
        "temperature": 0.7,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"}
    }

    req_data = json.dumps(payload).encode('utf-8')
    req = request.Request(
        f"{GROQ_API_BASE_URL}/chat/completions",
        data=req_data,
        headers=headers,
        method="POST"
    )

    max_retries = 5
    base_delay = 1.0
    assistant_response_str = ""

    for attempt in range(max_retries):
        try:
            with request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
                # Erros 4xx são erros do cliente e não devem ser tentados novamente.
                if 400 <= response.status < 500:
                    logging.error(f"Erro do cliente na API Groq: Status {response.status} - {response.read().decode()}")
                    return {"error": f"Client error: {response.status}"}

                # Erros 5xx são erros do servidor e podem ser tentados novamente.
                if response.status >= 500:
                    raise error.HTTPError(response.url, response.status, "Server Error", response.headers, response.fp)

                response_body = json.loads(response.read().decode('utf-8'))
                assistant_response_str = response_body['choices'][0]['message']['content']
                return json.loads(assistant_response_str)

        except (error.URLError, error.HTTPError) as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logging.warning(f"Erro na API ({e}), tentativa {attempt + 1}/{max_retries}. Tentando novamente em {delay:.2f}s...")
                time.sleep(delay)
            else:
                logging.error(f"Erro final na API após {max_retries} tentativas: {e}")
                return {"error": f"Final API error after {max_retries} retries: {e}"}

        except json.JSONDecodeError as e:
            logging.error(f"Erro ao decodificar JSON da resposta da API: {e}")
            logging.error(f"String recebida: {assistant_response_str}")
            return {"error": f"JSON decode error: {e}", "raw_response": assistant_response_str}

        except Exception as e:
            logging.error(f"Erro inesperado ao chamar a API: {e}")
            return {"error": f"Unexpected API error: {e}"}

    return {"error": "Falha na chamada da API após múltiplas tentativas."}

def validate_response(response: Dict[str, Any]) -> bool:
    """Valida o schema do JSON recebido da API."""
    if "action" not in response or response["action"] not in ["replace_file", "append", "replace_block", "noop"]:
        logging.warning(f"Resposta da IA inválida: 'action' ausente ou inválido. Resposta: {response}")
        return False

    action = response["action"]
    if action in ["replace_file", "append", "replace_block"]:
        if "target_path" not in response or "code" not in response:
             logging.warning(f"Resposta da IA inválida: 'target_path' ou 'code' ausente para a ação '{action}'.")
             return False

    if action == "replace_block" and "marker" not in response:
        logging.warning("Resposta da IA inválida: 'marker' ausente para a ação 'replace_block'.")
        return False

    return True
