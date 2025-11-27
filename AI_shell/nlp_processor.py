# ai_shell/nlp_processor.py
import platform
import ollama
import re
import os
import json
import shlex
import logging
from typing import Dict, Any, Optional

# --- Logging ---
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Existing maps (kept from teammate) ---
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

# --- Safety / destructive verbs to require confirmation ---
DANGEROUS_PATTERNS = [
    r"\brm\b", r"\brm -rf\b", r"\brm -r\b", r"\bdel\b", r"\bRemove-Item\b", r"\bformat\b",
    r"\bdd\b", r"\bshutdown\b", r"\breboot\b", r"\bmkfs\b", r"\b: > /dev/sda\b"
]
DANGEROUS_REGEX = re.compile("|".join(DANGEROUS_PATTERNS), re.IGNORECASE)

def looks_dangerous(command_str: str) -> bool:
    return bool(DANGEROUS_REGEX.search(command_str))

def get_smart_command(text: str) -> str:
    current_os = platform.system()
    clean_text = text.strip().lower()

    # --- Layer 1: Bidirectional Map ---
    # ... (Your existing Layer 1 code here) ...
    parts = text.strip().split()
    base_command = " ".join(parts[0:3]) if "new-item" in parts else parts[0]
    if base_command in ALIAS_MAP:
        concept = ALIAS_MAP[base_command]
        if current_os in COMMAND_MAP.get(concept, {}):
            logger.info("Used Layer 1: Bidirectional Cache ⚡️")
            translated_base = COMMAND_MAP[concept][current_os]
            args = text.strip().split()[1:]
            if "new-item" in base_command:
                args = text.strip().split()[3:]
            return f"{translated_base} {' '.join(args)}".strip()

    # --- Layer 2: Rules Engine ---
    # ... (Your existing Layer 2 code here) ...
    creation_pattern = re.compile(r"(create|make)\s.*(file|folder|directory)\s*[\"']?(.+?)[\"']?")
    location_pattern = re.compile(r"on\s(desktop|documents|downloads)")

    creation_match = creation_pattern.search(clean_text)
    location_match = location_pattern.search(clean_text)

    home_dir = os.path.expanduser("~")
    desktop_path = os.path.join(home_dir, "OneDrive", "Desktop") if current_os == "Windows" and "OneDrive" in home_dir else os.path.join(home_dir, "Desktop")
    location_map = {
        "desktop": desktop_path,
        "documents": os.path.join(home_dir, "Documents"),
        "downloads": os.path.join(home_dir, "Downloads")
    }

    if creation_match:
        item_type = creation_match.group(2)
        item_name = creation_match.group(3).strip()
        logger.debug(f"Matched Layer2 creation. Type: '{item_type}', Name: '{item_name}'")

        base_path = "."
        if location_match:
            location_keyword = location_match.group(1)
            if location_keyword in location_map:
                base_path = location_map[location_keyword]
        
        full_path = os.path.join(base_path, item_name)
        
        logger.info("Used Layer 2: Create Rule")
        if current_os == "Windows":
            ps_item_type = "Directory" if item_type in ["folder", "directory"] else "File"
            return f'New-Item -Path "{full_path}" -ItemType {ps_item_type}'
        else: # Linux/macOS
            command = "mkdir" if item_type in ["folder", "directory"] else "touch"
            return f'{command} "{full_path}"'
            
    # --- Layer 3: LLM Fallback ---
    logger.info("Command not in cache or rules, using LLM...")
    return call_ollama_model(text)

# --- The refined Layer 3 ---
def call_ollama_model(text: str) -> str:
    current_os = platform.system()
    shell_type = "PowerShell" if current_os == "Windows" else "bash/zsh"
    
    # We dynamically create few-shot examples inside the prompt.
    home_dir = os.path.expanduser("~")
    desktop_path = os.path.join(home_dir, "OneDrive", "Desktop") if current_os == "Windows" and "OneDrive" in home_dir else os.path.join(home_dir, "Desktop")

    # The simplified, highly-focused prompt
    # The enhanced, highly-focused prompt
    system_prompt = f"""
You are an expert command-line interpreter. Your single purpose is to convert a user's natural language request into one and only one executable shell command.

Follow these strict rules without exception:
1. Provide ONLY the executable command. Nothing else.
2. DO NOT include any conversational text, explanations, or notes.
3. DO NOT hallucinate, invent, or guess commands.
4. If you cannot generate a valid command, return the exact string 'COMMAND_NOT_FOUND'.

Regarding your output generation:
* Your output must be deterministic and confident.
* The sampling method is designed to prioritize the single most probable token at each step.

Here are some examples of user requests and the exact, single-line command you must generate:
- User request: "What's my current location?" -> Your response: "{COMMAND_MAP['show_location'][current_os]}"
- User request: "What's my username?" -> Your response: "{'$env:USERNAME' if current_os == 'Windows' else 'whoami'}"
- User request: "Check the system memory usage" -> Your response: "{'free -h' if current_os != 'Windows' else 'Get-Counter "\\Memory\\Available MBytes"'}"
- User request: "Show me ip address" -> Your response: "{'ipconfig' if current_os == 'Windows' else 'ip addr show'}"
- User request: "List all running processes" -> Your response: "{'Get-Process | Format-Table -AutoSize' if current_os == 'Windows' else 'ps aux'}"
- User request: "Show the top 10 processes consuming the most memory" -> Your response: "{'Get-Process | Sort-Object -Property WorkingSet -Descending | Select-Object -First 10' if current_os == 'Windows' else 'ps aux --sort -rss | head -n 11'}"
- User request: "List all files in the current directory, including hidden ones" -> Your response: "{COMMAND_MAP['list_all_items'][current_os]}"
- User request: "Create a new folder called 'reports'" -> Your response: "{COMMAND_MAP['make_directory'][current_os]} 'reports'"
- User request: "Make a file named 'notes.txt' on my desktop" -> Your response: "{COMMAND_MAP['create_file'][current_os]} '{os.path.join(desktop_path, 'notes.txt')}'"
- User request: "How can I see my recent commands?" -> Your response: "{'history' if current_os != 'Windows' else 'Get-History'}"
- User request: "delete the 'old_photos' folder" -> Your response: "{'rm -r old_photos' if current_os != 'Windows' else 'Remove-Item -Recurse -Force old_photos'}"
- User request: "show me all the text files on my desktop" -> Your response: "{'ls -l ' + os.path.join(desktop_path, '*.txt') if current_os != 'Windows' else 'Get-ChildItem -Path "' + desktop_path + '" -Filter *.txt'}"
- User request: "rename the file 'document.doc' to 'report.docx'" -> Your response: "{'mv document.doc report.docx' if current_os != 'Windows' else 'Rename-Item -Path "document.doc" -NewName "report.docx"'}"
- User request: "What time is it?" -> Your response: "{'Get-Date' if current_os == 'Windows' else 'date'}"
- User request: "reboot the system" -> Your response: "{'Restart-Computer' if current_os == 'Windows' else 'sudo reboot'}"
- User request: "how much disk space do I have?" -> Your response: "{'Get-PSDrive -PSProvider FileSystem | Format-Table Name, Used, Free' if current_os == 'Windows' else 'df -h'}"
"""
    

    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': text}
            ],
            options={'temperature': 0.1}
        )
        raw_output = response['message']['content']
        logger.debug(f"Raw LLM output: {raw_output}")
        
        # Post-process the output
        command = extract_command_from_output(raw_output)
        
        # Check for dangerous commands
        # if looks_dangerous(command):
        #     logger.warning(f"LLM generated a potentially dangerous command: {command}")
        #     # A more robust system would ask for confirmation here.
        #     # For this simple shell, we'll return a safe "echo" command.
        #     return f'echo "Warning: Potentially dangerous command generated. Please review manually: {command}"'

        if command == 'COMMAND_NOT_FOUND':
            logger.info("LLM was unable to generate a command.")
            return 'echo "I am not able to generate a command for that request."'

        # This is where we return the clean, single-line command
        return command

    except Exception as e:
        logger.exception("Error communicating with local model")
        return f"echo 'Error with LLM service: {e}'"

def extract_command_from_output(content: str) -> str:
    """
    Extracts the command from the LLM's response. It is highly defensive.
    """
    # 1. Look for a markdown code block first. This is the cleanest output format.
    code_block_regex = re.compile(r"```(?:\w+\n)?(.*?)```", re.DOTALL)
    match = code_block_regex.search(content)
    if match:
        command = match.group(1).strip()
        logger.debug("Extracted command from code block.")
        return command

    # 2. If no code block, try to find the last meaningful line or the first line.
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    if lines:
        # A simple heuristic: take the last line, as it's often the final answer.
        final_line = lines[-1]
        logger.debug(f"Using final line of output: {final_line}")
        return final_line

    # 3. Fallback: return the original content, sanitized.
    sanitized = content.strip().replace("`", "")
    logger.debug("Falling back to sanitized raw content.")
    return sanitized