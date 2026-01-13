import threading
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from .config import SECRET_KEY
from .db import Base, engine, get_db
from .models import User, Generation, ImageAsset
from .auth import hash_password, verify_password
from .openai_client import detect_breed_from_headshot
from .services.shaggy import generate_images_multithreaded

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
import os

MEDIA_DIR = os.environ.get("MEDIA_DIR", "/var/data/media")

app = FastAPI(title="Shaggy Dog Web App")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=False)

# Mount static/media AFTER app is created
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

Base.metadata.create_all(bind=engine)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=False)

templates_dir = Path(__file__).parent / "templates"
env = Environment(
    loader=FileSystemLoader(str(templates_dir)),
    autoescape=select_autoescape(["html", "xml"]),
)

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

def render(template: str, **ctx) -> HTMLResponse:
    tpl = env.get_template(template)
    return HTMLResponse(tpl.render(**ctx))

def get_current_user_id(request: Request) -> Optional[int]:
    return request.session.get("user_id")

def require_user(request: Request) -> int:
    uid = get_current_user_id(request)
    if not uid:
        raise HTTPException(status_code=401, detail="Not logged in")
    return uid

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    uid = get_current_user_id(request)
    if not uid:
        return RedirectResponse("/login", status_code=303)

    gens = db.execute(
        select(Generation).where(Generation.user_id == uid).order_by(desc(Generation.created_at)).limit(10)
    ).scalars().all()

    return render("index.html", request=request, generations=gens)

@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return render("register.html", request=request, error=None)

@app.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    username = username.strip()
    if not username or not password:
        return render("register.html", request=request, error="Username and password required")

    exists = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if exists:
        return render("register.html", request=request, error="Username already exists")


    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > 72:
        return render("register.html", request=request, error="Password is too long. Please use 72 bytes or fewer (try <= 50 characters, avoid emojis).")

    u = User(username=username, password_hash=hash_password(password))

    db.add(u)
    db.commit()
    db.refresh(u)

    request.session["user_id"] = u.id
    return RedirectResponse("/", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return render("login.html", request=request, error=None)

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    u = db.execute(select(User).where(User.username == username.strip())).scalar_one_or_none()
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > 72:
        return render("login.html", request=request, error="Password too long. Please use the same shorter password you registered with.")
    password = pw_bytes[:72].decode("utf-8", errors="ignore")

    if not u or not verify_password(password, u.password_hash):
        return render("login.html", request=request, error="Invalid username or password")

    request.session["user_id"] = u.id
    return RedirectResponse("/", status_code=303)

@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

def _start_generation_thread(gen_id: int, user_id: int):
    """Run generation in a background thread, generating images concurrently."""
    from .db import SessionLocal
    db = SessionLocal()
    try:
        gen = db.get(Generation, gen_id)
        if not gen or gen.user_id != user_id:
            return

        original = db.execute(
            select(ImageAsset).where(ImageAsset.generation_id == gen_id, ImageAsset.kind == "original")
        ).scalar_one()

        breed_info = detect_breed_from_headshot(original.data)
        breed = (breed_info.get("breed") or "Golden Retriever").strip()
        gen.breed = breed
        db.commit()

        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(original.data)
        tmp.close()

        try:
            images = generate_images_multithreaded(tmp.name, breed)

            for kind, url in images.items():
                db.add(ImageAsset(
                    generation_id=gen_id,
                    kind=kind,
                    mime_type="text/plain",
                    data=url.encode("utf-8"),
                ))

            gen.status = "done"
            gen.error_message = None
            db.commit()
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

    except Exception as e:
        try:
            gen = db.get(Generation, gen_id)
            if gen:
                gen.status = "error"
                gen.error_message = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()

@app.post("/generate")
async def generate(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    user_id = require_user(request)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload")

    gen = Generation(user_id=user_id, status="processing")
    db.add(gen)
    db.commit()
    db.refresh(gen)

    db.add(ImageAsset(
        generation_id=gen.id,
        kind="original",
        mime_type=file.content_type or "image/jpeg",
        data=content
    ))
    db.commit()

    t = threading.Thread(target=_start_generation_thread, args=(gen.id, user_id), daemon=True)
    t.start()

    return RedirectResponse(f"/generation/{gen.id}", status_code=303)

@app.get("/generation/{gen_id}", response_class=HTMLResponse)
def generation_page(gen_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = require_user(request)

    gen = db.get(Generation, gen_id)
    if not gen or gen.user_id != user_id:
        raise HTTPException(status_code=404, detail="Not found")

    images = db.execute(
        select(ImageAsset).where(ImageAsset.generation_id == gen_id).order_by(ImageAsset.id)
    ).scalars().all()

    by_kind = {}
    for img in images:
        if img.kind == "original":
            by_kind["original"] = f"/image/{img.id}"   # original still served from DB
        else:
            by_kind[img.kind] = img.data.decode("utf-8")  # /media/...

    return render("generation.html", request=request, gen=gen, by_kind=by_kind)

@app.get("/image/{image_id}")
def get_image(image_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = require_user(request)

    img = db.get(ImageAsset, image_id)
    if not img:
        raise HTTPException(status_code=404, detail="Not found")

    gen = db.get(Generation, img.generation_id)
    if not gen or gen.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return Response(content=img.data, media_type=img.mime_type)
