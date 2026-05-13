"""FastAPI entrypoint for nc-chatbot."""
from specialist_base.main import build_app

from .specialist import NcChatbot

app = build_app(NcChatbot())
