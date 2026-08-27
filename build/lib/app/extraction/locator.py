import argparse
import base64
import json
from pathlib import Path
from time import perf_counter

import httpx
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field, model_validator

from app.core.config import get_settings


class OfferRegion(BaseModel):
    id: int = Field(ge=1, description="Sequential offer identifier in reading order")
    x: int = Field(ge=0, le=1000, description="Normalized left edge")
    y: int = Field(ge=0, le=1000, description="Normalized top edge")
    width: int = Field(gt=0, le=1000, description="Normalized box width")
    height: int = Field(gt=0, le=1000, description="Normalized box height")

    @model_validator(mode="after")
    def stays_inside_page(self) -> "OfferRegion":
        if self.x + self.width > 1000 or self.y + self.height > 1000:
            raise ValueError("region exceeds normalized page bounds")
        return self


class LocatedOffers(BaseModel):
    regions: list[OfferRegion]


LOCATOR_PROMPT = """Voce localiza ofertas individuais em encartes brasileiros.
Inspecione visualmente a imagem inteira antes de responder. Nao copie valores das instrucoes.
Retorne SOMENTE o JSON compacto exigido pelo schema fornecido pela API.
As coordenadas usam uma grade normalizada de 0 a 1000: x cresce da esquerda para a direita e y de cima para baixo.
Crie exatamente uma regiao para cada oferta individual completa. Cada caixa deve conter junto nome do produto, imagem, todos os precos, unidade e condicoes da oferta.
Inclua margem suficiente, principalmente abaixo do produto, para nunca deixar o preco de fora.
Quando sabores ou produtos compartilham um unico nome/preco, use uma unica regiao.
Nao marque titulos de categoria, logos, slogans, validade, rodapes, QR codes, textos legais, fundos ou anuncios sem preco de supermercado.
Nao sobreponha regioes de ofertas diferentes. Numere em ordem de leitura, da esquerda para a direita e de cima para baixo.
Esta pagina e densa e organizada em uma grade regular; percorra todas as linhas ate a borda inferior para nao omitir ofertas.
Nao extraia textos ou precos no JSON; retorne somente id e coordenadas."""


def _json_response(raw: str) -> LocatedOffers:
    value = raw.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1].rsplit("```", 1)[0]
    return LocatedOffers.model_validate_json(value)


def locate_offers(image_path: Path) -> tuple[LocatedOffers, str, int]:
    settings = get_settings()
    payload = {
        "model": settings.ollama_model,
        "prompt": LOCATOR_PROMPT,
        "images": [base64.b64encode(image_path.read_bytes()).decode("ascii")],
        "stream": False,
        "format": LocatedOffers.model_json_schema(),
        "options": {
            "temperature": 0,
            "num_ctx": settings.qwen_context_size,
            "num_predict": 8192,
        },
    }
    started = perf_counter()
    response = httpx.post(
        f"{settings.ollama_base_url}/api/generate",
        json=payload,
        timeout=max(settings.qwen_request_timeout_seconds, 600),
    )
    response.raise_for_status()
    raw = response.json().get("response", "")
    return _json_response(raw), raw, round((perf_counter() - started) * 1000)


def render_regions(image_path: Path, located: LocatedOffers, output_path: Path) -> None:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(14, image.width // 45))
    line_width = max(3, image.width // 250)
    for region in located.regions:
        left = round(region.x * image.width / 1000)
        top = round(region.y * image.height / 1000)
        right = round((region.x + region.width) * image.width / 1000)
        bottom = round((region.y + region.height) * image.height / 1000)
        draw.rounded_rectangle(
            (left, top, right, bottom), radius=line_width * 2, outline="#39ff14", width=line_width
        )
        label = str(region.id)
        label_box = draw.textbbox((left, top), label, font=font, stroke_width=1)
        label_width = label_box[2] - label_box[0] + line_width * 3
        label_height = label_box[3] - label_box[1] + line_width * 2
        draw.rectangle((left, top, left + label_width, top + label_height), fill="#19b51d")
        draw.text(
            (left + line_width, top + line_width // 2),
            label,
            fill="white",
            font=font,
            stroke_width=1,
            stroke_fill="white",
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=95)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-image", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    located, raw, duration = locate_offers(args.image)
    render_regions(args.image, located, args.output_image)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(
            {
                "model": get_settings().ollama_model,
                "duration_ms": duration,
                "located": located.model_dump(),
                "raw_response": raw,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"regions": len(located.regions), "duration_ms": duration}))


if __name__ == "__main__":
    main()
