import requests
import os
import random


"""
Достаточно просто запустить код
Доступные модели: flux и turbo

by ForgetMe
tg: @forgetmeai
"""


def download_image(image_url, filename="image.jpg"):
    try:
        response = requests.get(image_url, stream=True, timeout=60)
        response.raise_for_status()

        with open(filename, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)

        print(f'Download Completed: {filename}')
    except requests.exceptions.RequestException as e:
        print(f'Download Failed: {e}')
    except IOError as e:
        print(f'File Error: {e}')

def generate_image_url(prompt, width=1024, height=1024, seed=None, model='flux'):
    if seed is None:
        seed = random.randint(0, 1000000)
        print(f"Using random seed: {seed}")

    return f"https://pollinations.ai/p/{prompt}?width={width}&height={height}&seed={seed}&model={model}"

def main():
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
    prompt = input("Enter your prompt: ")
    while True:
        model = input("Enter the model (flux or turbo): ").lower()
        if model in ['flux', 'turbo']:
            break
        else:
            print("Invalid model. Please choose 'flux' or 'turbo'.")

    width = 1024
    height = 1024
    seed = None
    output_filename = f"{prompt.replace(' ', '_')}_{model}.jpg"

    image_url = generate_image_url(prompt, width, height, seed, model)

    if os.path.exists(output_filename):
        overwrite = input(f"File '{output_filename}' already exists. Overwrite? (y/n): ")
        if overwrite.lower() != 'y':
            print("Download cancelled.")
            return

    download_image(image_url, output_filename)

if __name__ == "__main__":
    main()