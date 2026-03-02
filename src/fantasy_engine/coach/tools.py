"""
Tool definitions for the Claude-powered fantasy coach.

Each tool maps to an analytics function. Claude decides which tools
to call based on the user's question, then explains the results.
"""

TOOLS = [
    {
        "name": "get_team_strategy",
        "description": (
            "Get the complete team rebuilding strategy: which 5 categories to build around, "
            "which 4 to punt, position-by-position needs with target archetypes, "
            "specific trade targets, FA auction targets, rookie draft plan, "
            "players to sell, and a timeline. Use this for any strategic question: "
            "'what should I focus on?', 'what kind of players do I need?', 'what's my plan?'"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_monopolies",
        "description": (
            "Detect category monopolies: find categories where few players provide elite production "
            "and how many you control. Use when discussing trade leverage, irreplaceable players, "
            "or category advantages. Example: 'Only 8 players in the league have z>2.0 in BLK — you have 2.'"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_rotation_alerts",
        "description": (
            "Detect rotation changes across your roster: who's gaining minutes (buy signal), "
            "who's losing minutes (sell signal), who has a new starting role. "
            "Use when asked about player trends, minutes changes, or breakout candidates."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_player_rankings",
        "description": (
            "Get player rankings by z-score. Returns top N players sorted by total fantasy value. "
            "Can optionally punt (ignore) categories to see how rankings change. "
            "Use this when the user asks about best players, rankings, or player comparisons."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "top": {
                    "type": "integer",
                    "description": "Number of players to return",
                    "default": 15,
                },
                "punt_cats": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Categories to punt/ignore. Options: pts, reb, ast, stl, blk, tpm, fg_pct, ft_pct, tov",
                    "default": [],
                },
            },
        },
    },
    {
        "name": "get_player_zscores",
        "description": (
            "Get detailed z-scores for a specific player across all 9 categories. "
            "Shows exactly where a player is strong or weak. "
            "Use when the user asks about a specific player's value or category breakdown."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Player name (partial match OK, e.g. 'Giannis' or 'LeBron')",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_team_profile",
        "description": (
            "Analyze the team's category strengths and weaknesses. Shows which of the 9 categories "
            "are strong, average, or weak, and suggests which categories to punt. "
            "Use when the user asks about team strengths, weaknesses, or punt strategy."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "active_only": {
                    "type": "boolean",
                    "description": "Only analyze active roster (not reserves)",
                    "default": False,
                },
            },
        },
    },
    {
        "name": "evaluate_trade",
        "description": (
            "Evaluate a trade proposal. Analyzes per-category z-score impact, salary implications, "
            "dynasty value, and gives a verdict (strong_accept to strong_decline). "
            "Use when the user asks about a trade or wants to compare players in a trade context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "give": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Player names to give away",
                },
                "receive": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Player names to receive",
                },
                "punt_cats": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Categories being punted (ignored in evaluation)",
                    "default": [],
                },
            },
            "required": ["give", "receive"],
        },
    },
    {
        "name": "optimize_lineup",
        "description": (
            "Get the optimal weekly lineup from the full roster. Considers position eligibility "
            "and optionally punt strategy. Shows who should start and who should sit. "
            "Use when the user asks about lineup, start/sit, or who to play this week."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "punt_cats": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Categories to punt",
                    "default": [],
                },
                "injured": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Injured player names to exclude",
                    "default": [],
                },
            },
        },
    },
    {
        "name": "get_waiver_analysis",
        "description": (
            "Analyze the waiver wire: best available free agents by team need, "
            "most droppable players, and best add/drop swap pairs. "
            "Use when the user asks about pickups, drops, waiver wire, or free agents."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "punt_cats": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Categories to punt",
                    "default": [],
                },
                "top": {
                    "type": "integer",
                    "description": "Number of results per section",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "get_dynasty_rankings",
        "description": (
            "Get dynasty player rankings: age-adjusted, contract-length weighted values. "
            "Shows who has the best long-term value considering age trajectory and salary. "
            "Use when the user asks about dynasty value, long-term outlook, or contract value."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "top": {
                    "type": "integer",
                    "description": "Number of players to return",
                    "default": 15,
                },
            },
        },
    },
    {
        "name": "get_punt_strategies",
        "description": (
            "Find the optimal punt strategies for the roster. Tests all combinations of "
            "punting 0, 1, or 2 categories and ranks them by expected wins. "
            "Use when the user asks what to punt, or wants to optimize their build."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "max_punts": {
                    "type": "integer",
                    "description": "Maximum categories to punt (1 or 2)",
                    "default": 2,
                },
            },
        },
    },
    {
        "name": "get_roster",
        "description": (
            "Get the full roster with z-scores and contract details. "
            "Use when the user asks to see their roster or all their players."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter: 'Act' for active, 'Res' for reserve, '' for all",
                    "default": "",
                },
            },
        },
    },
    {
        "name": "find_trades",
        "description": (
            "Auto-scan all 12 teams in the league and find mutually beneficial trade proposals. "
            "Shows trades where both sides improve based on their category needs. "
            "Use when the user asks for trade suggestions, who to target, or trade ideas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "punt_cats": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Categories to punt",
                    "default": [],
                },
                "top": {
                    "type": "integer",
                    "description": "Number of trade proposals to return",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "get_alerts",
        "description": (
            "Get actionable alerts: injured players, better players on bench, "
            "hot free agents, trade opportunities, overpaid players. "
            "Use when the user asks what they should do, what actions to take, "
            "or for a general overview of their situation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_free_agents",
        "description": (
            "Get the best real free agents — NBA players not on any fantasy team in the league. "
            "Unlike waiver analysis (which only looks at your reserves), this shows truly available players. "
            "Use when the user asks about free agents, pickups, or who's available on the wire."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "top": {
                    "type": "integer",
                    "description": "Number of FAs to return",
                    "default": 20,
                },
            },
        },
    },
    {
        "name": "get_league_standings",
        "description": (
            "Get a summary of all 12 teams: their total z-scores, strongest and weakest categories. "
            "Use when the user asks about the league, other teams, or league standings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_weekly_lineup_plan",
        "description": (
            "Get the weekly-optimized daily lineup plan. This is the SMART lineup system that: "
            "1) Simulates both teams' full week day-by-day, "
            "2) Classifies categories as target/concede/swing, "
            "3) Strategically concedes lost-cause categories to win more swing ones, "
            "4) Each day picks 10 players maximizing END-OF-WEEK category wins. "
            "Use this instead of the basic lineup optimizer for matchup-specific advice."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "view": {
                    "type": "string",
                    "description": "'plan' for full week, 'today' for today only, 'strategy' for category strategy",
                    "default": "strategy",
                },
            },
        },
    },
    {
        "name": "get_team_context",
        "description": (
            "Get NBA team injury context: who's injured on a player's team, "
            "what stats/minutes they leave behind, and how much opportunity that creates. "
            "Use when evaluating a player's short-term value — a backup PG with the starter out "
            "is way more valuable. Also useful for streaming and waiver pickups."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {"type": "string", "description": "Player name to check opportunity for", "default": ""},
                "nba_team": {"type": "string", "description": "NBA team abbreviation to check context for", "default": ""},
            },
        },
    },
    {
        "name": "get_player_trends",
        "description": (
            "Get player trend data: last 7/14/30 day stats vs season averages, "
            "trending direction (hot/rising/stable/cooling/cold), minutes trend, "
            "and category-specific changes. Use when asked about recent form, "
            "hot/cold streaks, or whether a player is improving/declining."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {"type": "string", "description": "Player name (optional — omit for rising/falling lists)", "default": ""},
                "view": {"type": "string", "description": "'rising', 'falling', 'minutes', or empty for specific player", "default": ""},
            },
        },
    },
    {
        "name": "compare_vs_experts",
        "description": (
            "Compare our rankings vs Hashtag Basketball expert consensus. "
            "Shows buy-low candidates (we rate higher than experts) and sell-high "
            "(experts rate higher than us). Use when evaluating trade targets or "
            "when asked about player value disagreements."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "signal": {"type": "string", "description": "'buy_low', 'sell_high', or empty for all", "default": ""},
                "top": {"type": "integer", "default": 15},
            },
        },
    },
    {
        "name": "get_advanced_metrics",
        "description": (
            "Get advanced metrics for players: schedule-adjusted z-score, ROS value, "
            "consistency rating, games remaining, playoff games, weekly ceiling/floor, "
            "minutes trend. Use this when comparing players or when schedule/consistency matters. "
            "Also returns category scarcity index showing which stats are hardest to find."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {
                    "type": "string",
                    "description": "Player name (optional — omit for team overview)",
                    "default": "",
                },
                "include_scarcity": {
                    "type": "boolean",
                    "description": "Include category scarcity index",
                    "default": True,
                },
            },
        },
    },
    {
        "name": "get_trade_suggestions",
        "description": (
            "Get proactive trade recommendations from the Trade Intelligence System. "
            "Shows the best trades to propose, ranked by strategic value AND acceptance "
            "likelihood. Uses manager profiling, complementary needs, and expendable player analysis. "
            "Use when the user asks for trade ideas, who to target, or what trades to make."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "punt_cats": {"type": "array", "items": {"type": "string"}, "default": []},
                "top": {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "get_manager_profile",
        "description": (
            "Get behavioral analysis of a specific team's manager. Shows their archetype "
            "(contender/rebuilder/buyer/seller), what they're looking for, trade history, "
            "expendable players, and trade openness. Use when the user asks about a specific "
            "team, manager behavior, or trade partners."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_name": {"type": "string", "description": "Team name (partial match OK)"},
            },
            "required": ["team_name"],
        },
    },
    {
        "name": "get_position_scarcity",
        "description": (
            "Get positional scarcity analysis: replacement z-score at each position (PG/SG/SF/PF/C), "
            "and which players have the highest position scarcity bonus. A positive bonus means the "
            "player is at a thin position (harder to replace). Use when discussing player value, "
            "trade targets, or when position depth matters. Example: 'Centers have replacement z:+0.8 "
            "while PGs have replacement z:+2.1 — that means any center with z>+2 is much scarcer.'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "top": {
                    "type": "integer",
                    "description": "Number of top/bottom players to show",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "explain_system",
        "description": (
            "Explain how the fantasy analytics engine works: what modules exist, "
            "what each one takes into account, and how they connect. Use this when "
            "the user asks 'how does this work?', 'what do you consider?', 'what factors?', "
            "'explain the system', or wants to understand the methodology behind any recommendation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "module": {
                    "type": "string",
                    "description": (
                        "Specific module to explain. Options: 'all', 'zscores', 'trades', "
                        "'auction_values', 'keepers', 'add_drop', 'lineup', 'strategy', "
                        "'position_scarcity', 'dynasty', 'monopoly', 'matchups', 'trends'. "
                        "Default 'all' for overview."
                    ),
                    "default": "all",
                },
            },
        },
    },
    {
        "name": "get_trade_grades",
        "description": (
            "Get graded historical trades from this season. Shows letter grades (A+ to F) "
            "for each side, who won, and fairness rating. Use when the user asks about past trades, "
            "trade grades, or who's winning trades in the league."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]
