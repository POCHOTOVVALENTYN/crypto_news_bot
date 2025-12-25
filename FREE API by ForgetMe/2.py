import json
import requests
import logging


BASE_URL = "https://text.pollinations.ai"


"""
ДОСТУПНЫЕ МОДЕЛИ:

"openai" - OpenAI GPT-4o-mini
"openai-large" - OpenAI GPT-4o
"openai-reasoning" - OpenAI o1-mini
"qwen-coder" - Qwen 2.5 Coder 32B
"llama" - Llama 3.3 70B
"mistral" - Mistral Nemo
"unity" - Unity with Mistral Large by Unity AI Lab
"midijourney" - Midijourney musical transformer
"rtist" - Rtist image generator by @bqrio
"searchgpt" - SearchGPT with realtime news and web search
"evil" - Evil Mode - Experimental
"deepseek" - DeepSeek-V3
"claude-hybridspace" - Claude Hybridspace
"deepseek-r1" - DeepSeek-R1 Distill Qwen 32B
"deepseek-reasoner" - DeepSeek R1 - Full
"llamalight" - Llama 3.1 8B Instruct
"llamaguard" - Llamaguard 7B AWQ
"gemini" - Gemini 2.0 Flash
"gemini-thinking" - Gemini 2.0 Flash Thinking
"hormoz" - Hormoz 8b by Muhammadreza Haghiri
"hypnosis-tracy" - Hypnosis Tracy - Your Self-Help AI
"sur" - Sur AI Assistant
"sur-mistral" - Sur AI Assistant (Mistral)
"llama-scaleway" - Llama (Scaleway)


by ForgetMe
tg: @forgetmeai
"""

# ТЕКУЩАЯ МОДЕЛЬ
MODEL = "openai-large"


class SearchGPTAdapter:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.api_url = f"{BASE_URL}/openai"
        self.headers = {
            "Content-Type": "application/json",
        }

    def chat_completions(self, messages):
        try:
            payload = {
                "model": MODEL,
                "messages": messages
            }

            response = requests.post(
                self.api_url,
                headers=self.headers,
                data=json.dumps(payload),
                timeout=60.0
            )
            response.raise_for_status()
            api_response = response.json()

            model_name = api_response.get("model")
            response_content = api_response["choices"][0]["message"]["content"]

            return model_name, response_content

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request error: {e}")
            return None, None
        except (KeyError, IndexError) as e:
            self.logger.error(f"Error parsing API response: {e}")
            return None, None
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON response: {e}")
            return None, None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    adapter = SearchGPTAdapter()

    while True:
        print("""
██████╗ ██╗   ██╗    ███████╗ ██████╗ ██████╗  ██████╗ ███████╗████████╗███╗   ███╗███████╗                        
██╔══██╗╚██╗ ██╔╝    ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝╚══██╔══╝████╗ ████║██╔════╝                        
██████╔╝ ╚████╔╝     █████╗  ██║   ██║██████╔╝██║  ███╗█████╗     ██║   ██╔████╔██║█████╗                          
██╔══██╗  ╚██╔╝      ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝     ██║   ██║╚██╔╝██║██╔══╝                          
██████╔╝   ██║       ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗   ██║   ██║ ╚═╝ ██║███████╗                        
╚═════╝    ╚═╝       ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝     ╚═╝╚══════╝                        
                                                                                                                   
████████╗ ██████╗         ██████╗ ███████╗ ██████╗ ██████╗  ██████╗ ███████╗████████╗███╗   ███╗███████╗ █████╗ ██╗
╚══██╔══╝██╔════╝ ██╗    ██╔═══██╗██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝╚══██╔══╝████╗ ████║██╔════╝██╔══██╗██║
   ██║   ██║  ███╗╚═╝    ██║██╗██║█████╗  ██║   ██║██████╔╝██║  ███╗█████╗     ██║   ██╔████╔██║█████╗  ███████║██║
   ██║   ██║   ██║██╗    ██║██║██║██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝     ██║   ██║╚██╔╝██║██╔══╝  ██╔══██║██║
   ██║   ╚██████╔╝╚═╝    ╚█║████╔╝██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗   ██║   ██║ ╚═╝ ██║███████╗██║  ██║██║
   ╚═╝    ╚═════╝         ╚╝╚═══╝ ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝     ╚═╝╚══════╝╚═╝  ╚═╝╚═╝                                                                                                        
        """)
        user_prompt = input("You: ")
        if user_prompt.lower() == "exit":
            break

        messages = [{"role": "user", "content": user_prompt}]

        model_name, response_content = adapter.chat_completions(messages)

        if model_name and response_content:
            print(f"Model: {model_name}")
            print(f"Response: {response_content}")
        else:
            print("An error occurred during the API call.")