import base64
import json
from openai import OpenAI
from .config import OPENAI_API_KEY, VISION_MODEL


def get_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=OPENAI_API_KEY)

def detect_breed_from_headshot(image_bytes: bytes) -> dict:
    """
    Uses Chat Completions with an image input to guess which dog breed resembles the face.
    Returns dict with keys: breed, confidence, reasoning.
    """
    client = get_client()
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    prompt = (
        "Given a HUMAN HEADSHOT, pick the single dog breed that most closely resembles the person's face shape/features. "
        "Return STRICT JSON with keys: breed (string), confidence (0-1 float), reasoning (short string). "
        "No markdown."
    )

    rsp = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }
        ],
    )

    text = (rsp.choices[0].message.content or "").strip()
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                pass
    return {"breed": "Golden Retriever", "confidence": 0.3, "reasoning": "Fallback due to parsing error."}






def edit_image_with_prompt(input_path: str, prompt: str, *, model: str, mask_path: str | None = None) -> bytes:
    """
    Calls Images API 'edit' with a single image (+ optional mask) and prompt.
    Returns image bytes (downloaded from returned URL, or decoded from b64_json).
    """
    import httpx

    client = get_client()

    with open(input_path, "rb") as f:
        if mask_path:
            with open(mask_path, "rb") as mf:
                result = client.images.edit(
                    model=model,
                    image=f,
                    mask=mf,
                    prompt=prompt,
                    size="1024x1024",
                )
        else:
            result = client.images.edit(
                model=model,
                image=f,
                prompt=prompt,
                size="1024x1024",
            )

    data0 = result.data[0]

    url = getattr(data0, "url", None)
    if url:
        r = httpx.get(url, timeout=60.0)
        r.raise_for_status()
        return r.content

    b64 = getattr(data0, "b64_json", None)
    if b64:
        return base64.b64decode(b64)

    raise RuntimeError("Images API returned neither url nor b64_json.")


def generate_image_from_prompt(prompt: str, *, model: str) -> bytes:
    """
    Calls Images API 'generate' with a prompt.
    Returns image bytes (downloaded from the returned URL, or decoded from b64_json).
    """
    import httpx

    client = get_client()
    result = client.images.generate(
        model=model,
        prompt=prompt,
        size="1024x1024",
        # NOTE: no response_format here
    )

    data0 = result.data[0]

    url = getattr(data0, "url", None)
    if url:
        r = httpx.get(url, timeout=60.0)
        r.raise_for_status()
        return r.content

    b64 = getattr(data0, "b64_json", None)
    if b64:
        return base64.b64decode(b64)

    raise RuntimeError("Images API returned neither url nor b64_json.")
