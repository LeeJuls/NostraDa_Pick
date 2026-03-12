import google.generativeai as genai
print("GoogleSearch:", hasattr(genai.protos, 'GoogleSearch'))
print("GoogleSearchRetrieval:", hasattr(genai.protos, 'GoogleSearchRetrieval'))
print("SDK version:", genai.__version__)

# 어떤 Tool 필드가 있는지 확인
t = genai.protos.Tool()
print("Tool descriptor fields:", [f.name for f in t.DESCRIPTOR.fields])
