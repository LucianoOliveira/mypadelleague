import re

# Read the file
with open('website/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix escaped docstrings
content = content.replace('\\"""', '"""')
content = content.replace('\\"', '"')

# Write back
with open('website/views.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed syntax errors in views.py')