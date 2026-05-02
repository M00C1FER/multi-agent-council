"""Example: implement CLIBackend for a local Ollama model."""
import subprocess
from multi_agent_council import CLIBackend, Message


class OllamaBackend(CLIBackend):
    """Run a local Ollama model as a council participant."""
    name = "ollama"

    def __init__(self, model: str = "llama3"):
        self.model = model

    def send(self, message: Message) -> str:
        result = subprocess.run(
            ["ollama", "run", self.model, message.content],
            capture_output=True, text=True, timeout=120,
        )
        return result.stdout.strip()
