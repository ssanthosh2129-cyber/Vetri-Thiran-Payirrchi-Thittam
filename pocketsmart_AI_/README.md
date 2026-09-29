# PocketSmart AI

PocketSmart AI is an AI-powered smart budget and recommendation assistant.

It provides budget planning for:

- Home interiors
- Parties
- Jewelry

The project uses:

- Python
- FastAPI
- SQLite
- Jinja2
- HTML
- CSS
- JavaScript
- JWT authentication
- Google Gemini
- Pillow
- REST APIs


# 1. Project Structure

```text
PocketSmart_AI/
│
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
│
├── static/
│   ├── app.js
│   └── styles.css
│
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── home_planner.html
│   ├── party_planner.html
│   ├── jewelry_planner.html
│   └── history.html
│
├── uploads/
│   └── .gitkeep
│
└── tests/
    └── test_app.py