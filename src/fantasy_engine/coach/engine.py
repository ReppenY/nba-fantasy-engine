"""
Multi-LLM fantasy basketball coach.

Supports both Claude (Anthropic) and GPT-4 (OpenAI) with tool-use.
Both coaches access the same analytics engine, so you can compare advice.
"""
import json
import anthropic
import openai

from fantasy_engine.coach.tools import TOOLS
from fantasy_engine.coach.executor import execute_tool

SYSTEM_PROMPT = """You are an expert NBA fantasy basketball coach for a H2H 9-Category dynasty salary cap league on Fantrax.

LEAGUE: "Black Mamba Snake Pit" — 12 teams, H2H Each Category, $233 salary cap, dynasty with 3-year contracts.
YOUR TEAM: "He Who Remains"
CATEGORIES: PTS, REB, AST, STL, BLK, 3PTM, FG%, FT%, TO (lower is better)

You have powerful analytics tools. ALWAYS use them to look up data — never guess. Your tools provide:

METRICS YOU HAVE ACCESS TO:
- **Z-scores**: Standard category-by-category value (9 cats)
- **Schedule-Adjusted Z**: Z-score weighted by remaining games and consistency. More accurate than raw z-score.
- **ROS Value**: Rest-of-season value factoring schedule + playoffs
- **Consistency Rating**: 0-1 scale (1 = rock solid). Volatile players are risky in weekly H2H.
- **Category Scarcity**: BLK and AST are the scarcest categories (1.13x-1.16x). TO is least scarce (0.68x). This means BLK/AST contributors are more valuable than their raw z-scores suggest.
- **Weekly Ceiling/Floor**: Best and worst case weekly outcome
- **Games Remaining / Playoff Games**: Schedule strength matters — a +5 z-score player with 15 games left is worth less than +4 with 25 games
- **Salary Cap**: $233 total. Contracts are 3 years, extensions add $3/year.

WHEN EVALUATING PLAYERS: Always mention schedule-adjusted value alongside raw z-score. Note consistency and games remaining. Flag scarcity advantage (a +1.5 in BLK is harder to find than +1.5 in PTS).

WHEN EVALUATING TRADES: Factor in schedule (who has more remaining games?), consistency (trading volatile for reliable?), scarcity (gaining a scarce category?), salary, dynasty age curve, AND acceptance likelihood.

WHEN SUGGESTING LINEUP: Consider games this week, consistency (start reliable players when favored, high-ceiling when underdog), and matchup category targets.

TRADE INTELLIGENCE: You can access manager profiles (archetype, what they're looking for), trade probability matrix, expendable players per team, and proactive trade suggestions with acceptance likelihood scores.

KEY CONTEXT:
- 9 injured players including 3 season-ending (Walker Kessler, KCP, Thomas Sorber)
- 15 expiring contracts. Building for next season.
- Trade deadline was Jan 19 — no more trades this season, but planning for off-season.

Be direct and opinionated. The user wants clear "do this" recommendations, not "it depends" answers. Reference actual numbers from the tools."""


# Convert our tools to OpenAI format
def _tools_to_openai():
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in TOOLS
    ]


class ClaudeCoach:
    """Claude-powered coach using Anthropic API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.conversation: list[dict] = []
        self.provider = "claude"

    def chat(self, user_message: str) -> str:
        self.conversation.append({"role": "user", "content": user_message})

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=self.conversation,
        )

        while response.stop_reason == "tool_use":
            assistant_content = response.content
            self.conversation.append({"role": "assistant", "content": assistant_content})

            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            self.conversation.append({"role": "user", "content": tool_results})

            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self.conversation,
            )

        final_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                final_text += block.text

        self.conversation.append({"role": "assistant", "content": response.content})
        return final_text

    def reset(self):
        self.conversation = []


class GPTCoach:
    """GPT-4 powered coach using OpenAI API."""

    def __init__(self, api_key: str, model: str = "gpt-5.2"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.conversation: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        self.provider = "openai"

    def chat(self, user_message: str) -> str:
        self.conversation.append({"role": "user", "content": user_message})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.conversation,
            tools=_tools_to_openai(),
            max_completion_tokens=4096,
        )

        msg = response.choices[0].message

        # Process tool calls in a loop
        while msg.tool_calls:
            self.conversation.append(msg)

            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments)
                result = execute_tool(tc.function.name, args)
                self.conversation.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation,
                tools=_tools_to_openai(),
                max_completion_tokens=4096,
            )
            msg = response.choices[0].message

        final_text = msg.content or ""
        self.conversation.append({"role": "assistant", "content": final_text})
        return final_text

    def reset(self):
        self.conversation = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
