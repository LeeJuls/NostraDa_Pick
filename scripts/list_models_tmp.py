import sys
sys.path.insert(0, 'D:/WebService/NostraDa_Pick')
from dotenv import load_dotenv
load_dotenv('D:/WebService/NostraDa_Pick/.env')
import google.generativeai as genai
from config import config

out = []
key = config.GEMINI_API_KEY
out.append(f"Key found: {'yes' if key else 'NO'}")
if key:
    genai.configure(api_key=key)
    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    out.append(f"Total models: {len(models)}")
    for m in sorted(models):
        out.append(m)

with open('D:/WebService/NostraDa_Pick/scripts/models_out.txt', 'w') as f:
    f.write('\n'.join(out))
