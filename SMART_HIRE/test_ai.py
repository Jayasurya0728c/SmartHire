import google.generativeai as genai

# Your actual key
genai.configure(api_key="AIzaSyBtWqyMPqvUFiVpTjWGYb1t27VvUEuYNzE")

print("The models you can use are:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)