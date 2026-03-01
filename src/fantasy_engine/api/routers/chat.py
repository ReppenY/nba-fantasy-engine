"""
Chat endpoint: talk to AI fantasy coaches (Claude and/or GPT-4).

POST /chat with a message and optional provider choice.
"""
import os
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from fantasy_engine.coach.engine import ClaudeCoach, GPTCoach

router = APIRouter()

_coaches: dict = {}


class ChatRequest(BaseModel):
    message: str
    provider: str = "claude"  # "claude" or "openai"
    reset: bool = False


class ChatResponse(BaseModel):
    response: str
    provider: str
    conversation_length: int


class DualChatRequest(BaseModel):
    message: str


class DualChatResponse(BaseModel):
    claude: str
    openai: str


def _get_coach(provider: str):
    if provider not in _coaches:
        if provider == "claude":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                raise HTTPException(500, "ANTHROPIC_API_KEY not set in .env")
            _coaches["claude"] = ClaudeCoach(api_key=api_key)
        elif provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                raise HTTPException(500, "OPENAI_API_KEY not set in .env")
            _coaches["openai"] = GPTCoach(api_key=api_key)
        else:
            raise HTTPException(400, f"Unknown provider: {provider}. Use 'claude' or 'openai'")
    return _coaches[provider]


@router.post("", response_model=ChatResponse,
             description="Chat with an AI coach. Choose 'claude' or 'openai' as provider.")
def chat(req: ChatRequest):
    coach = _get_coach(req.provider)
    if req.reset:
        coach.reset()
    try:
        response = coach.chat(req.message)
    except Exception as e:
        err_msg = str(e)
        if "credit balance" in err_msg or "insufficient_quota" in err_msg or "billing" in err_msg.lower():
            response = (
                f"**{req.provider.upper()} API has no credits.** "
                f"Add billing at: {'https://console.anthropic.com/settings/billing' if req.provider == 'claude' else 'https://platform.openai.com/settings/organization/billing'}"
            )
        else:
            response = f"Error from {req.provider}: {err_msg[:200]}"
        coach.reset()
    conv_len = len(coach.conversation)
    return ChatResponse(response=response, provider=req.provider, conversation_length=conv_len)


@router.post("/both", response_model=DualChatResponse,
             description="Get advice from BOTH Claude and GPT-4 on the same question. Compare their takes.")
def chat_both(req: DualChatRequest):
    results = {}
    for provider in ["claude", "openai"]:
        try:
            coach = _get_coach(provider)
            coach.reset()
            results[provider] = coach.chat(req.message)
        except Exception as e:
            err = str(e)
            if "credit" in err or "quota" in err or "billing" in err.lower():
                results[provider] = f"**No API credits.** Add billing to use {provider}."
            else:
                results[provider] = f"Error: {err[:200]}"

    return DualChatResponse(claude=results.get("claude", ""), openai=results.get("openai", ""))


@router.post("/reset", description="Clear conversation history for a provider.")
def reset_chat(provider: str = Query("all", description="'claude', 'openai', or 'all'")):
    if provider == "all":
        for coach in _coaches.values():
            coach.reset()
    elif provider in _coaches:
        _coaches[provider].reset()
    return {"status": f"reset {provider}"}
