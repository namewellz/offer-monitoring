import base64
from pathlib import Path
from time import perf_counter

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.exceptions import ExtractionError
from app.extraction.schemas import FlyerExtraction


class OllamaVisionClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.settings.ollama_base_url}/api/tags")
                return response.is_success
        except httpx.HTTPError:
            return False

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(get_settings().extraction_max_retries),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    async def extract(self, image_path: Path, prompt: str) -> tuple[FlyerExtraction, str, int]:
        started = perf_counter()
        image = base64.b64encode(image_path.read_bytes()).decode("ascii")
        payload = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "images": [image],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.settings.qwen_temperature,
                "num_ctx": self.settings.qwen_context_size,
                "num_predict": self.settings.qwen_num_predict,
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.qwen_request_timeout_seconds
            ) as client:
                response = await client.post(
                    f"{self.settings.ollama_base_url}/api/generate", json=payload
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExtractionError(str(exc)) from exc
        raw = response.json().get("response", "")
        try:
            parsed = FlyerExtraction.model_validate_json(raw)
        except Exception as exc:
            raise ExtractionError(f"Model returned invalid extraction JSON: {exc}") from exc
        return parsed, raw, round((perf_counter() - started) * 1000)
