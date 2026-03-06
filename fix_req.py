import sys
import re
import os

req_path = 'requirements.txt'

try:
    with open(req_path, 'r', encoding='utf-16le') as f:
        lines = f.readlines()
except UnicodeError:
    # 혹시 이미 utf-8로 되어있다면 다시 읽음
    with open(req_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

new_lines = []
for line in lines:
    line = line.strip()
    if not line:
        continue
    # "패키지명 @ file:///..." 와 같은 부분을 찾아, 패키지 이름만 남깁니다.
    if '@ file:///' in line:
        pkg_name = line.split('@')[0].strip()
        new_lines.append(pkg_name)
    else:
        new_lines.append(line)

# Anaconda 및 불필요한 로컬 패키지 배제 리스트
exclude_prefixes = [
    'anaconda-', 'conda', 'archspec', 'libmambapy', 'menuinst', 
    'truststore', 'ruamel.yaml', 'win-inet-pton', 'boltons'
]

filtered_lines = []
for line in new_lines:
    pkg_name = line.split('==')[0].strip()
    if any(pkg_name.lower().startswith(prefix) for prefix in exclude_prefixes):
        continue
    filtered_lines.append(line)

new_lines = filtered_lines

# 백업용으로 기존 파일 복사본 생성 후, 원본을 덮어씀 (utf-8)
import shutil
shutil.copy(req_path, 'requirements_backup.txt')

with open(req_path, 'w', encoding='utf-8') as f:
    for line in new_lines:
        f.write(line + '\n')

print(f"✅ requirements.txt가 정상적으로 정리되었으며, UTF-8로 인코딩되었습니다.")
