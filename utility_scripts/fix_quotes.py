#!/usr/bin/env python3
"""
Script to fix escaped quotes in views.py
"""
import re

def fix_quotes():
    file_path = 'website/views.py'
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix escaped triple quotes
    content = re.sub(r'\\"""([^"]+?)\\"""', r'"""\\1"""', content)
    content = re.sub(r'\\"\\"\\"([^"]+?)\\"\\"\\"', r'"""\\1"""', content)
    
    # Fix escaped single quotes in strings
    content = re.sub(r'\\"([^"]*?)\\"', r'"\\1"', content)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Fixed quotes in views.py")

if __name__ == '__main__':
    fix_quotes()