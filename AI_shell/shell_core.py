# ai_shell/shell_core.py
import subprocess
import platform

def execute_command(command: str) -> str:
    """Executes a shell command and returns its output or error."""
    if not command:
        return "No command to execute."

    try:
        # On Windows, we must explicitly use powershell to run the command.
        if platform.system() == "Windows":
            # Using a list of arguments is more secure than shell=True
            executable = ["powershell.exe", "-Command", command]
            shell_mode = False # Not needed when passing an executable list
        else:
            # On Linux/macOS, the default shell is usually fine.
            executable = command
            shell_mode = True

        result = subprocess.run(
            executable,
            shell=shell_mode,
            check=True,
            text=True,
            capture_output=True,
            encoding='utf-8' # Good practice for handling different characters
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return e.stderr
    except FileNotFoundError:
        return f"Command not found: {command.split()[0]}"