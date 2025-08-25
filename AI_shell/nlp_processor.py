# ai_shell/nlp_processor.py
import platform
import ollama
import re
import os

# ... (MODEL_NAME, COMMAND_MAP, and ALIAS_MAP remain the same) ...
MODEL_NAME = 'phi3:mini'
COMMAND_MAP = {
    'list_items': {'Windows': 'Get-ChildItem', 'Linux': 'ls -l', 'Darwin': 'ls -l'},
    'list_all_items': {'Windows': 'Get-ChildItem -Force', 'Linux': 'ls -a', 'Darwin': 'ls -a'},
    'show_location': {'Windows': 'Get-Location', 'Linux': 'pwd', 'Darwin': 'pwd'},
    'clear_screen': {'Windows': 'Clear-Host', 'Linux': 'clear', 'Darwin': 'clear'},
    'make_directory': {'Windows': 'New-Item -ItemType Directory', 'Linux': 'mkdir', 'Darwin': 'mkdir'},
    'create_file': {'Windows': 'New-Item -ItemType File', 'Linux': 'touch', 'Darwin': 'touch'}
}
ALIAS_MAP = {
    'ls': 'list_items', 'dir': 'list_items', 'ls -a': 'list_all_items', 'pwd': 'show_location',
    'clear': 'clear_screen', 'cls': 'clear_screen', 'mkdir': 'make_directory', 'touch': 'create_file',
    'get-childitem': 'list_items', 'get-location': 'show_location', 'clear-host': 'clear_screen',
    'new-item -itemtype directory': 'make_directory', 'new-item -itemtype file': 'create_file'
}

def get_smart_command(text: str) -> str:
    current_os = platform.system()
    clean_text = text.strip().lower()

    # --- Check Layer 1: Bidirectional Map ---
    # (This logic remains the same)
    parts = text.strip().split()
    base_command = " ".join(parts[0:3]) if "new-item" in parts else parts[0]
    if base_command in ALIAS_MAP:
        concept = ALIAS_MAP[base_command]
        if current_os in COMMAND_MAP.get(concept, {}):
            print("Used Layer 1: Bidirectional Cache ⚡️")
            translated_base = COMMAND_MAP[concept][current_os]
            args = text.strip().split()[1:]
            if "new-item" in base_command:
                args = text.strip().split()[3:]
            return f"{translated_base} {' '.join(args)}".strip()

    # --- FINAL, ROBUST LAYER 2 ENGINE ---
    # Define patterns
    # This simpler pattern just looks for the intent and the name
    creation_pattern = re.compile(r"(create|make)\s.*(file|folder)\s+[\"'](.+?)[\"']")
    # This simpler pattern just looks for the location keyword
    location_pattern = re.compile(r"on\s(desktop|documents|downloads)")

    creation_match = creation_pattern.search(clean_text)
    location_match = location_pattern.search(clean_text)

    home_dir = os.path.expanduser("~")
    desktop_path = os.path.join(home_dir, "OneDrive", "Desktop") if current_os == "Windows" else os.path.join(home_dir, "Desktop")
    location_map = { "desktop": desktop_path, "documents": os.path.join(home_dir, "Documents"), "downloads": os.path.join(home_dir, "Downloads") }

    if creation_match:
        # We found an intent to create something
        item_type = creation_match.group(2)
        item_name = creation_match.group(3)
        print(f"DEBUG: Matched creation. Type: '{item_type}', Name: '{item_name}'")

        base_path = "." # Default to current directory
        if location_match:
            # We also found a location keyword
            location_keyword = location_match.group(1)
            print(f"DEBUG: Matched location keyword: '{location_keyword}'")
            if location_keyword in location_map:
                base_path = location_map[location_keyword]
        
        full_path = os.path.join(base_path, item_name)
        
        print("Used Layer 2: Create Rule")
        if current_os == "Windows":
            ps_item_type = "Directory" if item_type == "folder" else "File"
            return f'New-Item -Path "{full_path}" -ItemType {ps_item_type}'
        else: # Linux/macOS
            command = "mkdir" if item_type == "folder" else "touch"
            return f'{command} "{full_path}"'
            
    # --- Layer 3: LLM Fallback ---
    print("Command not in cache or rules, using LLM...")
    return call_ollama_model(text)

# ... (call_ollama_model and extract_command functions remain the same)
def call_ollama_model(text: str) -> str:
    current_os = platform.system()
    shell_type = "PowerShell" if current_os == "Windows" else "bash/zsh"

    system_prompt = f"""
    You are an expert AI assistant that translates natural language or Linux commands into a single, executable command for the {current_os} ({shell_type}) shell. Provide only the command.

    Here are some examples of translations for a Windows PowerShell user:
    - User request: "ls" -> Your response: "Get-ChildItem"
    - User request: "ls -a" -> Your response: "Get-ChildItem -Force"
    - User request: "mkdir my_folder" -> Your response: "New-Item -ItemType Directory -Name my_folder"
    - User request: "touch new_file.txt" -> Your response: "New-Item -ItemType File -Name new_file.txt"
    - User request: "list all folders on the desktop" -> Your response: "Get-ChildItem -Path "$env:USERPROFILE\OneDrive\Desktop" -Directory"
    - User request: "list all text files sorted by size" -> Your response: "Get-ChildItem -Path . -Filter *.txt | Sort-Object -Property Length"
    - User request: "pwd" -> Your response: "Get-Location"
    """

    try:
        response = ollama.chat( model='phi3:mini', messages=[ {'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': text} ] )
        command = extract_command(response['message']['content'])
        return command
    except Exception as e:
        return f"Error communicating with local model: {e}"

def extract_command(content: str) -> str:
    code_block_regex = re.compile(r"```(?:\w+\n)?(.*?)```", re.DOTALL)
    match = code_block_regex.search(content)
    if match:
        command = match.group(1).strip()
    else:
        command = content.strip()
    return command.replace("`", "")