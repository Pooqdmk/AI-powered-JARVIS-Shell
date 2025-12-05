import platform
import ollama
import re
import os
import json
import shlex
import logging
from typing import Dict, Any, Optional

# ----------------------------------------------
# Logging
# ----------------------------------------------
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s")

# ----------------------------------------------
# ALIASES + CROSS-OS COMMAND MAP
# ----------------------------------------------
MODEL_NAME = "phi3:mini"

COMMAND_MAP = {
    'list_items': {
        'Windows': 'Get-ChildItem',
        'Linux': 'ls -l',
        'Darwin': 'ls -l'
    },
    'list_all_items': {
        'Windows': 'Get-ChildItem -Force',
        'Linux': 'ls -a',
        'Darwin': 'ls -a'
    },
    'show_location': {
        'Windows': 'Get-Location',
        'Linux': 'pwd',
        'Darwin': 'pwd'
    },
    'clear_screen': {
        'Windows': 'Clear-Host',
        'Linux': 'clear',
        'Darwin': 'clear'
    },
    'make_directory': {
        'Windows': 'New-Item -ItemType Directory',
        'Linux': 'mkdir',
        'Darwin': 'mkdir'
    },
    'create_file': {
        'Windows': 'New-Item -ItemType File',
        'Linux': 'touch',
        'Darwin': 'touch'
    }
}

ALIAS_MAP = {
    'ls': 'list_items',
    'dir': 'list_items',
    'ls -a': 'list_all_items',
    'pwd': 'show_location',
    'clear': 'clear_screen',
    'cls': 'clear_screen',
    'mkdir': 'make_directory',
    'touch': 'create_file',
    'get-childitem': 'list_items',
    'get-location': 'show_location',
    'clear-host': 'clear_screen'
}

# ----------------------------------------------
# Safety matchers (kept)
# ----------------------------------------------
DANGEROUS_PATTERNS = [
    r"\brm -rf\b",
    r"\bRemove-Item\b",
    r"\bmkfs\b",
    r"\bdd\b",
]
DANGEROUS_REGEX = re.compile("|".join(DANGEROUS_PATTERNS), re.IGNORECASE)

def looks_dangerous(cmd: str) -> bool:
    return bool(DANGEROUS_REGEX.search(cmd))


# ===========================================================================
# LAYER 1 — BIDIRECTIONAL ALIAS MAP
# ===========================================================================
def get_smart_command(text: str) -> str:
    current_os = platform.system()
    clean = text.strip().lower()

    # Extract potential base command
    parts = clean.split()
    base = parts[0] if parts else ""

    # LAYER 1
    if base in ALIAS_MAP:
        concept = ALIAS_MAP[base]
        if current_os in COMMAND_MAP[concept]:
            logger.info("Used Layer 1 (Alias Map)")
            return COMMAND_MAP[concept][current_os]

    # ===========================================================================
    # LAYER 2 — RULE ENGINE (FILE/FOLDER CREATION)
    # ===========================================================================
    pattern = re.compile(r"(create|make)\s+(file|folder|directory)\s+(.+)")
    match = pattern.search(clean)

    if match:
        logger.info("Used Layer 2 (Rule Engine)")

        kind = match.group(2)
        name = match.group(3).strip().replace('"', '')

        if current_os == "Windows":
            if kind in ["folder", "directory"]:
                return f'New-Item -ItemType Directory "{name}"'
            else:
                return f'New-Item -ItemType File "{name}"'
        else:
            return f'mkdir "{name}"' if kind in ["folder", "directory"] else f'touch "{name}"'

    # ===========================================================================
    # LAYER 3 — LLM FALLBACK
    # ===========================================================================
    logger.info("Used Layer 3 (LLM Fallback)")
    return call_ollama_model(text)


# ===========================================================================
# LLM FALLBACK (ALWAYS RETURNS A VALID COMMAND)
# ===========================================================================
def call_ollama_model(text: str) -> str:
    current_os = platform.system()
    shell = "PowerShell" if current_os == "Windows" else "bash"

    # Path setup
    home_dir = os.path.expanduser("~")
    desktop_path = os.path.join(home_dir, "OneDrive", "Desktop") if (
        current_os == "Windows" and "OneDrive" in home_dir
    ) else os.path.join(home_dir, "Desktop")

    # ===========================================================================
    # The new, fixed, ALWAYS-GENERATE-A-COMMAND prompt
    # ===========================================================================
    system_prompt = f"""
You are an expert {shell} command generator.

Your ONLY job:
➡ Convert any natural language request into ONE valid {shell} command.

STRICT RULES:
1. ALWAYS output exactly one command.
2. NEVER output explanations, markdown, quotes, code blocks, or comments.
3. NEVER output placeholders like COMMAND_NOT_FOUND.
4. NEVER output random text; always produce a real executable command.
5. If unsure, infer the MOST LIKELY correct command.
6. Output MUST be valid for the OS: {current_os}.
7. DO NOT guess file paths that don’t exist. Use safe defaults.

GENERAL KNOWLEDGE:
You know all standard PowerShell, Bash, Linux, and macOS commands.
You know how to search files, list directories, kill processes, manage services, network tools, etc.

EXAMPLES:
User: "What's my location?"
→ {COMMAND_MAP['show_location'][current_os]}

User: "Show me my IP"
→ {"ipconfig" if current_os == "Windows" else "ip addr show"}

User: "List everything here"
→ {COMMAND_MAP['list_all_items'][current_os]}

User: "List running processes"
→ {"Get-Process" if current_os == "Windows" else "ps aux"}

User: "Sort processes by memory"
→ {"Get-Process | Sort-Object -Property WorkingSet -Descending" if current_os == "Windows" else "ps aux --sort -rss"}

User: "Show wifi networks"
→ {"netsh wlan show networks" if current_os == "Windows" else "nmcli dev wifi"}

User: "Find all PDF files"
→ {"Get-ChildItem -Recurse -Filter *.pdf" if current_os == "Windows" else "find . -type f -name '*.pdf'"}

User: "Kill the process using most RAM"
→ {"Get-Process | Sort-Object -Property WorkingSet -Descending | Select-Object -First 1 | Stop-Process -Force" if current_os == "Windows" else "ps -eo pid,%mem --sort=-%mem | head -n 2 | awk 'NR==2{print $1}' | xargs kill -9"}

Now generate ONLY the command for the user's query:
"""

    # Call local Ollama
    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            options={"temperature": 0}
        )
        raw = response["message"]["content"].strip()

        cmd = extract_single_command(raw)

        if looks_dangerous(cmd):
            return f'echo "Dangerous command blocked: {cmd}"'

        return cmd

    except Exception as e:
        logger.exception("LLM communication error")
        return f'echo "Error with LLM: {e}"'


# ===========================================================================
# COMMAND EXTRACTION — MOST ROBUST VERSION
# ===========================================================================
def extract_single_command(content: str) -> str:
    """
    Extracts exactly ONE clean command from LLM output.
    Removes markdown, comments, and extra sentences.
    """
    # Remove code blocks
    content = re.sub(r"```.*?```", "", content, flags=re.DOTALL)

    # Take first non-empty line
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    if not lines:
        return "echo 'LLM returned no output'"

    # Ensure it's command-only (strip trailing punctuation)
    cmd = lines[0].replace("`", "").strip().rstrip(".")
    return cmd
