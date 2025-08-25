
-----

# AI-Powered Conversational Shell 🤖

This project is a modern, conversational command-line shell that understands natural language. You can type plain English like "list all the folders on my desktop" or standard Linux commands like `ls -a`, and the AI will translate it into the correct command for your operating system and execute it.

The user interface is built with **Textual**, providing a rich, app-like experience in your terminal. The core intelligence is powered by a locally-run, open-source Large Language Model using **Ollama**.

-----

##  Core Features

  * **Natural Language Understanding:** Ask the shell to perform tasks in plain English.
  * **Cross-Platform Translation:** Type Linux commands like `ls` on Windows, and the AI will correctly translate them to PowerShell's `Get-ChildItem`.
  * **Multi-Layered Architecture:**
      * **Layer 1 (Cache):** Provides instant responses for common commands (`ls`, `pwd`, `dir`, etc.).
      * **Layer 2 (Rule Engine):** Uses regular expressions to quickly handle simple, structured requests (e.g., "create folder 'x' on desktop").
      * **Layer 3 (LLM):** Uses a local AI model (`phi-3:mini`) for complex and novel queries, taught via few-shot prompting.
  * **TUI Interface:** A rich, user-friendly terminal interface built with Textual.
  * **Local & Private:** All AI processing is done locally via Ollama, so your data and commands never leave your machine.

-----

##  Setup and Installation

Follow these steps to get the AI Shell running on your local machine.

###  Prerequisites

  * Python 3.8+
  * Ollama ([Download here](https://ollama.com/))

###  Installation Steps

1.  **Clone the Repository:**

    ```sh
    git clone <your-repository-url>
    cd <your-repository-name>
    ```

2.  **Set Up Virtual Environment:**

      * Create the environment:
        ```sh
        python -m venv venv
        ```
      * Activate the environment:
          * **On Windows (PowerShell):** `.\venv\Scripts\Activate.ps1`
          * **On macOS/Linux:** `source venv/bin/activate`

3.  **Install Dependencies:**

    ```sh
    pip install -r requirements.txt
    ```

4.  **Download the AI Model:**
    Pull the recommended model using Ollama. This will download a few gigabytes.

    ```sh
    ollama pull phi3:mini
    ```

-----

##  How to Use

1.  **Activate Your Virtual Environment** (if you haven't already).

2.  **Launch the Application:**
    Use the Textual runner to start the shell.

    ```sh
    textual run main.py
    ```

    *For debugging, you can use `textual run --dev main.py` and press F12 to see console output.*

3.  **Interact with the Shell:**
    Once the application is running, you can type your requests into the input box at the bottom and press Enter.

    **Example Queries:**

      * `ls -a`
      * `list all files on my desktop`
      * `create a new folder named "project_alpha" in my documents`
      * `list all text files sorted by size`
      * To leave the application, simply type `exit`.
