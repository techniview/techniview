"""Check that the configured Ollama endpoint and model are ready."""

import json
import os
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen


def request_json(url: str, payload: dict | None = None, timeout: int = 10) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def main() -> None:
    base_url = os.environ.get("BIG_O_OLLAMA_URL", "").rstrip("/")
    model = os.environ.get("BIG_O_OLLAMA_MODEL", "qwen3.8:27b")
    warm = "--warm" in sys.argv[1:]
    if not base_url:
        print("AI complexity estimates disabled (BIG_O_OLLAMA_URL is empty).")
        return

    try:
        response = request_json(f"{base_url}/api/tags")
        available = {item.get("name") for item in response.get("models", [])}
        if model not in available:
            raise SystemExit(
                f"Ollama is reachable, but model {model!r} is not installed. "
                f"Available models: {', '.join(sorted(available)) or '(none)'}"
            )
        print(f"Ollama is reachable and model {model} is installed.")
        if warm:
            request_json(
                f"{base_url}/api/generate",
                {
                    "model": model,
                    "prompt": "Reply with the word ready.",
                    "stream": False,
                    "keep_alive": "10m",
                    "options": {"num_predict": 1},
                },
                timeout=600,
            )
            print(f"Model {model} is warm and will remain loaded for 10 minutes.")
    except (OSError, URLError, TimeoutError) as error:
        raise SystemExit(f"Cannot reach Ollama at {base_url}: {error}") from None


if __name__ == "__main__":
    main()
