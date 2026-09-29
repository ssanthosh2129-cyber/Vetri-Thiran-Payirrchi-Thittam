import json
import os
import re
import sqlite3
import urllib.parse
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from passlib.context import CryptContext
from PIL import Image
from pydantic import BaseModel, EmailStr, Field


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

DATABASE_PATH = Path(
    os.getenv(
        "DATABASE_PATH",
        str(BASE_DIR / "pocketsmart.db")
    )
)

UPLOAD_DIR = Path(
    os.getenv(
        "UPLOAD_DIR",
        str(BASE_DIR / "uploads")
    )
)

if not UPLOAD_DIR.is_absolute():
    UPLOAD_DIR = BASE_DIR / UPLOAD_DIR

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "dev-only-change-this-secret"
)

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "60"
    )
)

MAX_UPLOAD_MB = int(
    os.getenv(
        "MAX_UPLOAD_MB",
        "5"
    )
)

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY",
    ""
).strip()

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.0-flash"
)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="PocketSmart AI",
    description="AI-powered smart budget and recommendation assistant",
    version="1.0.0",
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

app.mount(
    "/uploads",
    StaticFiles(directory=str(UPLOAD_DIR)),
    name="uploads",
)

templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)


# ============================================================
# AUTHENTICATION
# ============================================================

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/login",
    auto_error=False,
)

# Simple in-memory blacklist for logged-out tokens.
blacklisted_tokens: set[str] = set()


# ============================================================
# DATABASE
# ============================================================

def db() -> sqlite3.Connection:
    """
    Create a SQLite database connection.
    """
    conn = sqlite3.connect(DATABASE_PATH)

    conn.row_factory = sqlite3.Row

    return conn


def init_db() -> None:
    """
    Create database tables if they don't already exist.
    """

    with db() as conn:

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                recommendation_type TEXT NOT NULL,
                input_data TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


@app.on_event("startup")
async def startup() -> None:
    init_db()


# ============================================================
# PYDANTIC MODELS
# ============================================================

class UserCreate(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=40
    )

    email: EmailStr

    password: str = Field(
        min_length=6,
        max_length=128
    )


class LoginInput(BaseModel):
    username: str
    password: str


class HomeBudgetInput(BaseModel):
    total_budget: float = Field(gt=0)

    num_lights: int = Field(
        default=0,
        ge=0,
        le=100
    )

    num_fans: int = Field(
        default=0,
        ge=0,
        le=100
    )

    num_furniture: int = Field(
        default=0,
        ge=0,
        le=100
    )

    num_dining_tables: int = Field(
        default=0,
        ge=0,
        le=20
    )

    rooms: List[str] = Field(
        default_factory=list
    )

    special_requirements: str = ""


class PartyBudgetInput(BaseModel):
    total_budget: float = Field(gt=0)

    party_type: str = Field(
        min_length=2,
        max_length=80
    )

    num_guests: int = Field(
        gt=0,
        le=10000
    )

    venue_preference: str = ""

    food_preference: str = ""

    entertainment: str = ""

    special_requirements: str = ""


class JewelryBudgetInput(BaseModel):
    total_budget: float = Field(gt=0)

    occasion: str = Field(
        min_length=2,
        max_length=80
    )

    preferences: str = ""


# ============================================================
# AUTH FUNCTIONS
# ============================================================

def verify_password(
    plain_password: str,
    hashed_password: str
) -> bool:

    return pwd_context.verify(
        plain_password,
        hashed_password
    )


def get_password_hash(password: str) -> str:

    return pwd_context.hash(password)


def create_access_token(username: str) -> str:

    expires = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    payload = {
        "sub": username,
        "exp": expires,
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def get_user(
    username: str
) -> Optional[sqlite3.Row]:

    with db() as conn:

        return conn.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()


def get_user_by_email(
    email: str
) -> Optional[sqlite3.Row]:

    with db() as conn:

        return conn.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (email.lower(),),
        ).fetchone()


def get_current_user_from_token(
    token: Optional[str]
) -> sqlite3.Row:

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    if token in blacklisted_tokens:
        raise HTTPException(
            status_code=401,
            detail="Session has been logged out",
        )

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        username = payload.get("sub")

        if not username:
            raise HTTPException(
                status_code=401,
                detail="Invalid token",
            )

    except JWTError as exc:

        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        ) from exc

    user = get_user(username)

    if not user:

        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    return user


def get_current_active_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
) -> sqlite3.Row:

    cookie_token = request.cookies.get(
        "access_token"
    )

    return get_current_user_from_token(
        cookie_token or token
    )


def browser_user(
    request: Request
) -> Optional[sqlite3.Row]:

    token = request.cookies.get(
        "access_token"
    )

    if not token:
        return None

    try:

        return get_current_user_from_token(
            token
        )

    except HTTPException:

        return None


def page_context(
    request: Request,
    **extra: Any
) -> Dict[str, Any]:

    return {
        "request": request,
        "user": browser_user(request),
        **extra,
    }


# ============================================================
# AI / GEMINI FUNCTIONS
# ============================================================

def extract_json_from_response(
    text: str
) -> Dict[str, Any]:

    cleaned = (
        text
        .strip()
        .replace("```json", "")
        .replace("```", "")
        .strip()
    )

    match = re.search(
        r"\{.*\}",
        cleaned,
        flags=re.DOTALL,
    )

    if not match:
        raise ValueError(
            "AI response did not contain JSON."
        )

    return json.loads(
        match.group(0)
    )


def gemini_json(
    prompt: str,
    image: Optional[Image.Image] = None
) -> Optional[Dict[str, Any]]:

    if not GEMINI_API_KEY:
        return None

    try:

        import google.generativeai as genai

        genai.configure(
            api_key=GEMINI_API_KEY
        )

        model = genai.GenerativeModel(
            GEMINI_MODEL
        )

        content: Any = [prompt]

        if image is not None:
            content.append(image)

        response = model.generate_content(
            content
        )

        return extract_json_from_response(
            response.text
        )

    except Exception:

        # If Gemini is unavailable,
        # application uses the local fallback engine.
        return None


# ============================================================
# RECOMMENDATION HELPERS
# ============================================================

def money(value: float) -> float:

    return round(
        max(0.0, float(value)),
        2
    )


def finalize_result(
    result: Dict[str, Any],
    budget: float
) -> Dict[str, Any]:

    result["total_budget"] = money(
        budget
    )

    result.setdefault(
        "budget_breakdown",
        []
    )

    # Calculate current total.
    total = sum(
        float(
            item.get(
                "estimated_price",
                0
            )
        )
        for category in result["budget_breakdown"]
        for item in category.get(
            "items",
            []
        )
    )

    # Scale recommendation if it exceeds budget.
    if total > budget and total > 0:

        factor = budget / total

        for category in result["budget_breakdown"]:

            for item in category.get(
                "items",
                []
            ):

                item["estimated_price"] = money(
                    float(
                        item.get(
                            "estimated_price",
                            0
                        )
                    ) * factor
                )

    for category in result["budget_breakdown"]:

        category.setdefault(
            "category",
            "Other"
        )

        category.setdefault(
            "items",
            []
        )

        category["items_count"] = len(
            category["items"]
        )

        category["total_cost"] = money(
            sum(
                float(
                    item.get(
                        "estimated_price",
                        0
                    )
                )
                for item in category["items"]
            )
        )

        category["percentage_of_budget"] = round(
            (
                category["total_cost"]
                / budget
                * 100
            )
            if budget
            else 0,
            2,
        )

        for item in category["items"]:

            item.setdefault(
                "description",
                "Practical option selected for your budget.",
            )

            item.setdefault(
                "search_terms",
                item.get(
                    "name",
                    category["category"]
                ),
            )

            item["estimated_price"] = money(
                item.get(
                    "estimated_price",
                    0
                )
            )

            query = urllib.parse.quote_plus(
                str(
                    item["search_terms"]
                )
            )

            item["shopping_links"] = {
                "amazon": (
                    "https://www.amazon.in/s?k="
                    + query
                ),
                "flipkart": (
                    "https://www.flipkart.com/search?q="
                    + query
                ),
                "ikea": (
                    "https://www.ikea.com/in/en/search/?q="
                    + query
                ),
                "myntra": (
                    "https://www.myntra.com/search?q="
                    + query
                ),
            }

    result["remaining_budget"] = money(
        budget
        - sum(
            category["total_cost"]
            for category in result["budget_breakdown"]
        )
    )

    result.setdefault(
        "additional_suggestions",
        [
            "Compare at least two sellers before purchasing."
        ],
    )

    return result


# ============================================================
# FALLBACK HOME RECOMMENDATION
# ============================================================

def fallback_home(
    budget: HomeBudgetInput
) -> Dict[str, Any]:

    specifications = [
        (
            "Lighting",
            budget.num_lights,
            0.08,
            "LED ceiling/wall light",
        ),
        (
            "Fans",
            budget.num_fans,
            0.10,
            "Energy-efficient ceiling fan",
        ),
        (
            "Furniture",
            budget.num_furniture,
            0.35,
            "Multi-purpose storage furniture",
        ),
        (
            "Dining",
            budget.num_dining_tables,
            0.18,
            "Compact dining table",
        ),
    ]

    categories = []

    for (
        category,
        count,
        share,
        name,
    ) in specifications:

        if count:

            categories.append(
                {
                    "category": category,
                    "items": [
                        {
                            "name": name,
                            "description": (
                                f"Suggested for "
                                f"{count} unit(s)."
                            ),
                            "estimated_price": (
                                budget.total_budget
                                * share
                            ),
                            "search_terms": name,
                        }
                    ],
                }
            )

    if not categories:

        categories = [
            {
                "category": "Essentials",
                "items": [
                    {
                        "name": (
                            "Smart home essentials bundle"
                        ),
                        "description": (
                            "Balanced starter set "
                            "for a practical home plan."
                        ),
                        "estimated_price": (
                            budget.total_budget
                            * 0.55
                        ),
                        "search_terms": (
                            "home essentials India"
                        ),
                    }
                ],
            }
        ]

    return {
        "budget_breakdown": categories,
        "additional_suggestions": [
            "Measure rooms before buying furniture.",
            "Prioritize energy-efficient appliances.",
            "Keep 10–15% as a contingency buffer.",
        ],
    }


# ============================================================
# FALLBACK PARTY RECOMMENDATION
# ============================================================

def fallback_party(
    budget: PartyBudgetInput
) -> Dict[str, Any]:

    shares = [
        (
            "Venue",
            0.25,
            "Affordable event venue",
        ),
        (
            "Catering",
            0.40,
            "Per-person catering package",
        ),
        (
            "Decoration",
            0.10,
            "Party decoration set",
        ),
        (
            "Entertainment",
            0.10,
            "Music and entertainment",
        ),
        (
            "Gifts",
            0.08,
            "Guest return gifts",
        ),
    ]

    breakdown = []

    for (
        category,
        share,
        name,
    ) in shares:

        breakdown.append(
            {
                "category": category,
                "items": [
                    {
                        "name": name,
                        "description": (
                            f"Plan for "
                            f"{budget.num_guests} guests."
                        ),
                        "estimated_price": (
                            budget.total_budget
                            * share
                        ),
                        "search_terms": name,
                    }
                ],
            }
        )

    return {
        "budget_breakdown": breakdown,
        "additional_suggestions": [
            "Confirm venue and catering headcount early.",
            "Keep a small emergency reserve.",
            "Compare package pricing before booking.",
        ],
    }


# ============================================================
# FALLBACK JEWELRY RECOMMENDATION
# ============================================================

def fallback_jewelry(
    budget: JewelryBudgetInput
) -> Dict[str, Any]:

    return {
        "outfit_analysis": {
            "colors": [],
            "style": (
                "Not analyzed without "
                "an outfit image"
            ),
            "formality": budget.occasion,
        },

        "budget_breakdown": [
            {
                "category": "Jewelry",
                "items": [
                    {
                        "name": "Statement earrings",
                        "description": (
                            "Versatile option suited "
                            "to many occasions."
                        ),
                        "estimated_price": (
                            budget.total_budget
                            * 0.35
                        ),
                        "search_terms": (
                            "statement earrings India"
                        ),
                    },
                    {
                        "name": "Bracelet or bangles",
                        "description": (
                            "Complements the main piece "
                            "without using the full budget."
                        ),
                        "estimated_price": (
                            budget.total_budget
                            * 0.25
                        ),
                        "search_terms": (
                            "bangles bracelet India"
                        ),
                    },
                    {
                        "name": "Necklace",
                        "description": (
                            "Choose a style matching "
                            "the neckline and occasion."
                        ),
                        "estimated_price": (
                            budget.total_budget
                            * 0.30
                        ),
                        "search_terms": (
                            "occasion necklace India"
                        ),
                    },
                ],
            }
        ],

        "additional_suggestions": [
            "Match metal tone with outfit details.",
            "Check return policies and seller ratings.",
        ],
    }


# ============================================================
# HOME AI
# ============================================================

def get_home_recommendations(
    budget: HomeBudgetInput
) -> Dict[str, Any]:

    prompt = f"""
You are PocketSmart, an India-focused budget
recommendation assistant.

Create a practical home budget plan in INR.

Total budget:
{budget.total_budget}

Number of lights:
{budget.num_lights}

Number of fans:
{budget.num_fans}

Furniture pieces:
{budget.num_furniture}

Dining tables:
{budget.num_dining_tables}

Rooms:
{budget.rooms}

Special requirements:
{budget.special_requirements}

Return ONLY valid JSON:

{{
    "budget_breakdown": [
        {{
            "category": "Category",
            "items": [
                {{
                    "name": "Item",
                    "description": "Description",
                    "estimated_price": 1000,
                    "search_terms": "search phrase"
                }}
            ]
        }}
    ],
    "additional_suggestions": []
}}

Keep the recommendation within the requested budget.
"""

    result = (
        gemini_json(prompt)
        or fallback_home(budget)
    )

    return finalize_result(
        result,
        budget.total_budget
    )


# ============================================================
# PARTY AI
# ============================================================

def get_party_recommendations(
    budget: PartyBudgetInput
) -> Dict[str, Any]:

    prompt = f"""
You are PocketSmart, an India-focused
party budget assistant.

Total budget:
{budget.total_budget}

Party type:
{budget.party_type}

Guests:
{budget.num_guests}

Venue:
{budget.venue_preference}

Food:
{budget.food_preference}

Entertainment:
{budget.entertainment}

Special requirements:
{budget.special_requirements}

Return ONLY valid JSON:

{{
    "budget_breakdown": [
        {{
            "category": "Category",
            "items": [
                {{
                    "name": "Item",
                    "description": "Description",
                    "estimated_price": 1000,
                    "search_terms": "search phrase"
                }}
            ]
        }}
    ],
    "additional_suggestions": []
}}

Keep the total within budget.
"""

    result = (
        gemini_json(prompt)
        or fallback_party(budget)
    )

    return finalize_result(
        result,
        budget.total_budget
    )


# ============================================================
# JEWELRY AI
# ============================================================

def get_jewelry_recommendations(
    budget: JewelryBudgetInput,
    image_path: Optional[Path] = None,
) -> Dict[str, Any]:

    prompt = f"""
You are PocketSmart, an India-focused
jewelry recommendation assistant.

Total budget:
{budget.total_budget}

Occasion:
{budget.occasion}

Preferences:
{budget.preferences or "Not specified"}

If an outfit image is provided, analyze only
visible clothing colors, style and formality.

Do not identify the person.

Return ONLY valid JSON:

{{
    "outfit_analysis": {{
        "colors": [],
        "style": "",
        "formality": ""
    }},
    "budget_breakdown": [
        {{
            "category": "Jewelry",
            "items": [
                {{
                    "name": "Item",
                    "description": "Description",
                    "estimated_price": 1000,
                    "search_terms": "search phrase"
                }}
            ]
        }}
    ],
    "additional_suggestions": []
}}

Keep the recommendation within budget.
"""

    image = None

    if image_path:

        try:

            image = Image.open(
                image_path
            ).convert("RGB")

        except Exception:

            image = None

    result = (
        gemini_json(
            prompt,
            image
        )
        or fallback_jewelry(budget)
    )

    return finalize_result(
        result,
        budget.total_budget
    )


# ============================================================
# HISTORY
# ============================================================

def save_to_history(
    username: str,
    recommendation_type: str,
    input_data: Dict[str, Any],
    result: Dict[str, Any],
) -> None:

    with db() as conn:

        conn.execute(
            """
            INSERT INTO recommendations
            (
                username,
                recommendation_type,
                input_data,
                result,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                username,
                recommendation_type,
                json.dumps(input_data),
                json.dumps(result),
                datetime.now(
                    timezone.utc
                ).isoformat(),
            ),
        )


def load_history(
    username: str
) -> List[Dict[str, Any]]:

    with db() as conn:

        rows = conn.execute(
            """
            SELECT *
            FROM recommendations
            WHERE username = ?
            ORDER BY id DESC
            """,
            (username,),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# HTML PAGES
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
async def index(request: Request):

    return templates.TemplateResponse(
        "index.html",
        page_context(request),
    )


@app.get(
    "/login",
    response_class=HTMLResponse
)
async def login_page(request: Request):

    return templates.TemplateResponse(
        "login.html",
        page_context(request),
    )


@app.get(
    "/register",
    response_class=HTMLResponse
)
async def register_page(request: Request):

    return templates.TemplateResponse(
        "register.html",
        page_context(request),
    )


@app.get(
    "/dashboard",
    response_class=HTMLResponse
)
async def dashboard(request: Request):

    user = browser_user(request)

    if not user:
        return RedirectResponse(
            "/login"
        )

    history = load_history(
        user["username"]
    )

    return templates.TemplateResponse(
        "dashboard.html",
        page_context(
            request,
            history=history[:5],
        ),
    )


@app.get(
    "/home-planner",
    response_class=HTMLResponse
)
async def home_planner(
    request: Request
):

    if not browser_user(request):
        return RedirectResponse(
            "/login"
        )

    return templates.TemplateResponse(
        "home_planner.html",
        page_context(request),
    )


@app.get(
    "/party-planner",
    response_class=HTMLResponse
)
async def party_planner(
    request: Request
):

    if not browser_user(request):
        return RedirectResponse(
            "/login"
        )

    return templates.TemplateResponse(
        "party_planner.html",
        page_context(request),
    )


@app.get(
    "/jewelry-planner",
    response_class=HTMLResponse
)
async def jewelry_planner(
    request: Request
):

    if not browser_user(request):
        return RedirectResponse(
            "/login"
        )

    return templates.TemplateResponse(
        "jewelry_planner.html",
        page_context(request),
    )


@app.get(
    "/history",
    response_class=HTMLResponse
)
async def history_page(
    request: Request
):

    user = browser_user(request)

    if not user:
        return RedirectResponse(
            "/login"
        )

    return templates.TemplateResponse(
        "history.html",
        page_context(
            request,
            history=load_history(
                user["username"]
            ),
        ),
    )


# ============================================================
# API - REGISTER
# ============================================================

@app.post("/api/register")
async def register(
    payload: UserCreate
):

    username = payload.username.strip()
    email = str(payload.email).lower()

    if get_user(username):

        raise HTTPException(
            status_code=400,
            detail="Username already exists",
        )

    if get_user_by_email(email):

        raise HTTPException(
            status_code=400,
            detail="Email already exists",
        )

    with db() as conn:

        conn.execute(
            """
            INSERT INTO users
            (
                username,
                email,
                password_hash,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                username,
                email,
                get_password_hash(
                    payload.password
                ),
                datetime.now(
                    timezone.utc
                ).isoformat(),
            ),
        )

    return {
        "message": "Account created",
        "username": username,
    }


# ============================================================
# API - LOGIN
# ============================================================

@app.post("/api/login")
async def login(
    payload: LoginInput
):

    user = get_user(
        payload.username.strip()
    )

    if (
        not user
        or not verify_password(
            payload.password,
            user["password_hash"],
        )
    ):

        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
        )

    token = create_access_token(
        user["username"]
    )

    response = JSONResponse(
        {
            "message": "Login successful",
            "username": user["username"],
        }
    )

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return response


# ============================================================
# LOGOUT
# ============================================================

@app.post("/logout")
async def logout(
    request: Request
):

    token = request.cookies.get(
        "access_token"
    )

    if token:
        blacklisted_tokens.add(
            token
        )

    response = RedirectResponse(
        url="/login",
        status_code=status.HTTP_302_FOUND,
    )

    response.delete_cookie(
        "access_token"
    )

    return response


# ============================================================
# CURRENT USER
# ============================================================

@app.get("/api/me")
async def me(
    current_user: sqlite3.Row = Depends(
        get_current_active_user
    )
):

    return {
        "username": current_user["username"],
        "email": current_user["email"],
    }


# ============================================================
# HOME BUDGET API
# ============================================================

@app.post("/home-budget")
async def plan_home_budget(
    budget_input: HomeBudgetInput,
    current_user: sqlite3.Row = Depends(
        get_current_active_user
    ),
):

    result = get_home_recommendations(
        budget_input
    )

    save_to_history(
        current_user["username"],
        "home",
        budget_input.model_dump(),
        result,
    )

    return result


# ============================================================
# PARTY BUDGET API
# ============================================================

@app.post("/party-budget")
async def plan_party_budget(
    budget_input: PartyBudgetInput,
    current_user: sqlite3.Row = Depends(
        get_current_active_user
    ),
):

    result = get_party_recommendations(
        budget_input
    )

    save_to_history(
        current_user["username"],
        "party",
        budget_input.model_dump(),
        result,
    )

    return result


# ============================================================
# JEWELRY BUDGET API
# ============================================================

@app.post("/jewelry-budget")
async def plan_jewelry_budget(
    total_budget: float = Form(...),
    occasion: str = Form(...),
    preferences: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    current_user: sqlite3.Row = Depends(
        get_current_active_user
    ),
):

    if total_budget <= 0:

        raise HTTPException(
            status_code=422,
            detail="Budget must be greater than zero",
        )

    image_path: Optional[Path] = None
    filename = None

    if image and image.filename:

        allowed_types = {
            "image/jpeg",
            "image/png",
            "image/webp",
        }

        if image.content_type not in allowed_types:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Please upload a JPG, "
                    "PNG, or WEBP image"
                ),
            )

        data = await image.read()

        if len(data) > (
            MAX_UPLOAD_MB * 1024 * 1024
        ):

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Image must be "
                    f"{MAX_UPLOAD_MB} MB or smaller"
                ),
            )

        try:

            checked = Image.open(
                BytesIO(data)
            )

            checked.verify()

        except Exception as exc:

            raise HTTPException(
                status_code=400,
                detail="Invalid image file",
            ) from exc

        safe_name = re.sub(
            r"[^a-zA-Z0-9_.-]",
            "_",
            image.filename,
        )

        image_path = (
            UPLOAD_DIR
            / (
                datetime.now().strftime(
                    "%Y%m%d%H%M%S"
                )
                + "_"
                + safe_name
            )
        )

        image_path.write_bytes(data)

        filename = image_path.name

    budget_input = JewelryBudgetInput(
        total_budget=total_budget,
        occasion=occasion,
        preferences=preferences or "",
    )

    result = get_jewelry_recommendations(
        budget_input,
        image_path,
    )

    input_data = budget_input.model_dump()

    if filename:
        input_data["image"] = filename

    save_to_history(
        current_user["username"],
        "jewelry",
        input_data,
        result,
    )

    return result


# ============================================================
# HISTORY API
# ============================================================

@app.get(
    "/recommendation-history"
)
async def recommendation_history(
    current_user: sqlite3.Row = Depends(
        get_current_active_user
    )
):

    rows = load_history(
        current_user["username"]
    )

    for row in rows:

        row["input_data"] = json.loads(
            row["input_data"]
        )

        row["result"] = json.loads(
            row["result"]
        )

    return rows


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():

    return {
        "status": "ok",
        "ai_enabled": bool(
            GEMINI_API_KEY
        ),
        "database": DATABASE_PATH.name,
    }