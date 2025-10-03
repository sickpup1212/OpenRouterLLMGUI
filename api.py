import requests
from tkinter import messagebox
from models import OpenRouterAPIParameters

def fetch_openrouter_models():
    """Fetches the list of models from the OpenRouter API."""
    try:
        response = requests.get("https://openrouter.ai/api/v1/models")
        response.raise_for_status()
        return response.json().get('data', [])
    except requests.exceptions.RequestException as e:
        messagebox.showerror("API Error", f"Failed to fetch models from OpenRouter: {e}")
        return []

def call_openrouter_api(api_key, model_name, history, advanced_settings):
    """Calls the OpenRouter chat completions API and returns the response text and role."""
    api_url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}

    messages = history.copy()
    if advanced_settings.get("system_message"):
        messages.insert(0, {"role": "system", "content": advanced_settings["system_message"]})

    payload = {"model": model_name, "messages": messages}

    try:
        params = OpenRouterAPIParameters(**advanced_settings)
        payload.update(params.model_dump(exclude_none=True))
    except Exception as e:
        return f"Parameter Validation Error: {e}", "error"

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=180)
        response.raise_for_status()
        result = response.json()
        text_response = result['choices'][0]['message']['content']
        return text_response, "assistant"
    except requests.exceptions.RequestException as e:
        return f"API Request Failed: {e}", "error"
    except Exception as e:
        return f"An unexpected error occurred: {e}\n\nFull Response:\n{getattr(e, 'response', '')}", "error"