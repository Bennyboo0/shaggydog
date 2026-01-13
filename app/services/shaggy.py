# app/services/shaggy.py

import tempfile
from PIL import Image, ImageDraw, ImageFilter

from ..config import IMAGE_MODEL
from ..openai_client import edit_image_with_prompt, generate_image_from_prompt


def _square_png_under_4mb(src_path: str) -> str:
    """
    Edits require: square PNG < 4MB.
    Create a 1024x1024 RGB PNG with a solid background (no transparency).
    Returns a temp file path.
    """
    img = Image.open(src_path).convert("RGB")
    w, h = img.size
    side = max(w, h)

    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2))

    canvas = canvas.resize((1024, 1024))

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp.close()
    canvas.save(tmp.name, format="PNG", optimize=True)

    # If somehow >4MB, shrink more
    if _filesize(tmp.name) > 4 * 1024 * 1024:
        canvas = canvas.resize((768, 768))
        canvas.save(tmp.name, format="PNG", optimize=True)

    return tmp.name


def _filesize(path: str) -> int:
    import os
    return os.path.getsize(path)


def _make_face_mask(square_png_path: str) -> str:
    """
    Creates a PNG mask the same size as the square image.
    OPAQUE = keep, TRANSPARENT = editable region (face ellipse).
    Returns a temp file path.
    """
    im = Image.open(square_png_path).convert("RGBA")
    w, h = im.size

    mask = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(mask)

    left = int(w * 0.16)
    right = int(w * 0.84)
    top = int(h * 0.04)
    bottom = int(h * 0.82)

    draw.ellipse([left, top, right, bottom], fill=(0, 0, 0, 0))

    alpha = mask.split()[-1].filter(ImageFilter.GaussianBlur(radius=4))
    mask.putalpha(alpha)

    out = tempfile.NamedTemporaryFile(delete=False, suffix="_mask.png")
    out.close()
    mask.save(out.name, format="PNG")
    return out.name


def generate_transition_prompts(breed: str) -> dict[str, str]:
    t1 = (
        f"Edit ONLY the face area. Keep the same person, same body, same clothes, same background. "
        f"Do NOT add any extra animals, extra faces, or split-screen/comparison panels. "
        f"One subject only. "
        f"Subtle (30%) {breed} traits: faint fur texture on cheeks, slightly wider/darker canine nose, "
        f"very slight muzzle lengthening, tiny ear hints near hairline."
    )

    t2 = (
        f"Edit ONLY the face area. Keep the same person, same body, same clothes, same background. "
        f"Do NOT add any extra animals, extra faces, or split-screen/comparison panels. "
        f"One subject only. "
        f"Stronger (70%) {breed} traits: visible fur on face/neck, clearly canine nose, noticeably longer muzzle, "
        f"dog ears formed, jaw reshaped to canine proportions."
    )

    dog = (
        f"Single {breed} dog headshot portrait, studio lighting, centered, one dog only, no collage, no text."
    )

    return {"t1": t1, "t2": t2, "dog": dog}


def generate_images_multithreaded(
    original_path: str,
    breed: str,
    image_model: str = IMAGE_MODEL,
) -> dict[str, bytes]:
    """
    Returns dict: {kind: image_bytes}

    - Transition 1: masked EDIT of the uploaded image
    - Transition 2: masked EDIT of transition 1 (sequential progression)
    - Dog: text-to-image GENERATE

    IMPORTANT:
    - No disk persistence (Render Free). We return raw bytes for DB storage.
    - No multithreading because t2 depends on t1.
    """
    prompts = generate_transition_prompts(breed)

    base_path = _square_png_under_4mb(original_path)
    mask_path = _make_face_mask(base_path)

    out: dict[str, bytes] = {}

    # --- Transition 1 ---
    t1_bytes = edit_image_with_prompt(
        base_path,
        prompts["t1"],
        model=image_model,
        mask_path=mask_path,
    )
    out["t1"] = t1_bytes

    # Write t1 to temp file so we can edit it for Transition 2
    t1_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    t1_tmp.close()
    with open(t1_tmp.name, "wb") as f:
        f.write(t1_bytes)

    # --- Transition 2 ---
    t2_bytes = edit_image_with_prompt(
        t1_tmp.name,
        prompts["t2"],
        model=image_model,
        mask_path=mask_path,
    )
    out["t2"] = t2_bytes

    # --- Dog ---
    dog_bytes = generate_image_from_prompt(prompts["dog"], model=image_model)
    out["dog"] = dog_bytes

    return out
