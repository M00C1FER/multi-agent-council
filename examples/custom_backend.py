"""Example: implement CLIBackend for a local Ollama model."""
import subprocess
from multi_agent_council import CLIBackend


class OllamaBackend(CLIBackend):
    """Run a local Ollama model as a council participant."""

    def __init__(self, model: str = "llama3"):
        self._model = model

    @property
    def name(self) -> str:
        return f"ollama-{self._model}"

    def query(self, prompt: str, timeout: int = 120) -> str:
        result = subprocess.run(
            ["ollama", "run", self._model, prompt],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip()
