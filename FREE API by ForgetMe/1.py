from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("API_KEY")
BASE_URL = "https://api.sree.shop/v1"


client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL
)


"""
ДОСТУПНЫЕ МОДЕЛИ:

claude-3-5-sonnet-20240620
claude-3-5-sonnet
deepseek-ai/DeepSeek-R1-Distill-Qwen-32B
deepseek-r1
deepseek-v3
gpt-4o
gpt-4o-2024-05-13
Meta-Llama-3.3-70B-Instruct-Turbo

by ForgetMe
tg: @forgetmeai
"""

# ТЕКУЩАЯ МОДЕЛЬ
model = "gpt-4o"


def chat_with_openai(prompt, model=model):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error during API call: {e}")
        return None


if __name__ == "__main__":
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
        print("Диалог начат, для выхода напишите 'выход'")
        user_prompt = input("Вы: ")
        if user_prompt.lower() == "выход":
            break

        response = chat_with_openai(user_prompt)
        if response:
            print("ИИ:", response)