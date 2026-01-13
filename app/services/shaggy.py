import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config import IMAGE_MODEL
from ..openai_client import edit_image_with_prompt, generate_image_from_prompt
from PIL import Image, ImageDraw, ImageFilter

def _make_face_mask(square_png_path: str) -> str:
    """
    Creates a PNG mask the same size as the square image.
    OPAQUE = keep, TRANSPARENT = editable region (the face ellipse).
    """
    im = Image.open(square_png_path).convert("RGBA")
    w, h = im.size

    # Fully opaque mask (keep everything)
    mask = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(mask)

    # Ellipse region that becomes TRANSPARENT (editable)
    # These numbers assume a headshot-ish framing.
    left   = int(w * 0.16)
    right  = int(w * 0.84)
    top    = int(h * 0.04)
    bottom = int(h * 0.82)


    draw.ellipse([left, top, right, bottom], fill=(0, 0, 0, 0))

    # Feather the edge so it blends nicer
    alpha = mask.split()[-1].filter(ImageFilter.GaussianBlur(radius=4))
    mask.putalpha(alpha)

    out_path = square_png_path.replace(".png", "_mask.png")
    mask.save(out_path, format="PNG")
    return out_path



def _center_square_crop(input_path: str) -> str:
    im = Image.open(input_path).convert("RGB")
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    im = im.crop((left, top, left + side, top + side))
    out_path = (
        input_path.replace(".png", "_sq.png")
        .replace(".jpg", "_sq.png")
        .replace(".jpeg", "_sq.png")
    )
    im.save(out_path, format="PNG", optimize=True)
    return out_path


def _square_png_under_4mb(src_path: str) -> str:
    """
    DALL·E 2 edits require: square PNG < 4MB.
    Create a 1024x1024 RGB PNG with a SOLID background (no transparency).
    """
    img = Image.open(src_path).convert("RGB")
    w, h = img.size
    side = max(w, h)

    # Solid white background (prevents black bars from alpha)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2))

    canvas = canvas.resize((1024, 1024))

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp.close()
    canvas.save(tmp.name, format="PNG", optimize=True)

    # if somehow too large, shrink
    if os.path.getsize(tmp.name) > 4 * 1024 * 1024:
        canvas = canvas.resize((768, 768))
        canvas.save(tmp.name, format="PNG", optimize=True)

    return tmp.name



def generate_transition_prompts(breed: str) -> dict:
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
    image_model: str = IMAGE_MODEL
) -> dict:
    """
    Returns dict: {kind: image_bytes}

    Recommended behavior:
    - Transition 1: masked EDIT of the uploaded image
    - Transition 2: masked EDIT of transition 1 (sequential progression)
    - Dog: text-to-image GENERATE

    Note: no multithreading, because transition2 depends on transition1.
    """
    prompts = generate_transition_prompts(breed)

    # DALL·E 2 edits require square PNG (<4MB). This helper already handles it.
    base_path = _square_png_under_4mb(original_path)

    # Make a face mask for the square image
    mask_path = _make_face_mask(base_path)

    out: dict[str, bytes] = {}

    # --- Transition 1: edit the base image ---
    t1_bytes = edit_image_with_prompt(
        base_path,
        prompts["t1"],
        model=image_model,
        mask_path=mask_path,   # <-- key part
    )
    out["t1"] = t1_bytes

    # Write t1 to a temp file so we can edit it for Transition 2
    t1_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    t1_tmp.close()
    with open(t1_tmp.name, "wb") as f:
        f.write(t1_bytes)

    # --- Transition 2: edit Transition 1 (sequential progression) ---
    t2_bytes = edit_image_with_prompt(
        t1_tmp.name,
        prompts["t2"],
        model=image_model,
        mask_path=mask_path,   # same mask works because both are 1024x1024
    )
    out["t2"] = t2_bytes

    # --- Dog: generate from scratch (text-to-image) ---
    dog_bytes = generate_image_from_prompt(prompts["dog"], model=image_model)
    out["dog"] = dog_bytes

    return out
