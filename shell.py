from transformers import BartForConditionalGeneration, BartTokenizer
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
import torch, os

# # ---------------- Load Model ---------------- #
# def load_bart_model(model_dir="./jarvis/bart_autocomplete_model", base_model="facebook/bart-base"):
#     if os.path.isdir(model_dir):
#         print(f"🔍 Loading fine-tuned model from: {model_dir}")
#         tokenizer = BartTokenizer.from_pretrained(model_dir)
#         model = BartForConditionalGeneration.from_pretrained(model_dir)
#     else:
#         print(f"⚠️ Fine-tuned model not found at {model_dir}, using {base_model}")
#         tokenizer = BartTokenizer.from_pretrained(base_model)
#         model = BartForConditionalGeneration.from_pretrained(base_model)
#     return tokenizer, model

def load_bart_model(
    model_dir=None,
    hf_repo="Bharadwaj26/jarvis-bart-autocomplete-finetuned",
    subfolder="bart_autocomplete_model",
    base_model="facebook/bart-base"
):
    try:
        if model_dir is not None and os.path.isdir(model_dir):
            print(f"🔍 Loading fine-tuned model from local directory: {model_dir}")
            tokenizer = BartTokenizer.from_pretrained(model_dir)
            model = BartForConditionalGeneration.from_pretrained(model_dir)

        else:
            print(f"🌐 Loading fine-tuned model from HuggingFace: {hf_repo}/{subfolder}")
            tokenizer = BartTokenizer.from_pretrained(hf_repo, subfolder=subfolder)
            model = BartForConditionalGeneration.from_pretrained(hf_repo, subfolder=subfolder)

    except Exception as e:
        print(f"⚠️ Failed to load fine-tuned model. Falling back to base model: {base_model}")
        print(f"Error: {e}")
        tokenizer = BartTokenizer.from_pretrained(base_model)
        model = BartForConditionalGeneration.from_pretrained(base_model)

    return tokenizer, model

tokenizer, model = load_bart_model()
device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)
model.eval()

# ---------------- Suggestion Generator ---------------- #
def generate_suggestions(text, num_return_sequences=3, max_length=32):
    inputs = tokenizer(text, return_tensors="pt").to(device)
    outputs = model.generate(
        **inputs,
        max_length=max_length,
        num_beams=5,
        num_return_sequences=num_return_sequences,
        early_stopping=True
    )
    return [tokenizer.decode(o, skip_special_tokens=True) for o in outputs]

# ---------------- PromptToolkit Completer ---------------- #
class BartCompleter(Completer):
    def get_completions(self, document, complete_event):
        prefix = document.text
        if not prefix.strip():
            return
        try:
            suggestions = generate_suggestions(prefix)
            for s in suggestions:
                # Only show completions that extend the prefix
                if s.lower().startswith(prefix.lower()):
                    yield Completion(s, start_position=-len(prefix))
        except Exception as e:
            print(f"⚠️ Error generating suggestions: {e}")

# ---------------- Run Interactive CLI ---------------- #
def run_cli():
    session = PromptSession(completer=BartCompleter())
    print("💡 Autocomplete CLI (type partial text, press Tab for suggestions, Ctrl+C to quit)")
    while True:
        try:
            text = session.prompt("> ")
            print(f"✅ You typed: {text}\n")
        except KeyboardInterrupt:
            break
        except EOFError:
            break

if __name__ == "__main__":
    run_cli()
