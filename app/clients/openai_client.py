"""
OpenAI API client: check if a guess matches the correct game and generate hints.

Uses the chat completions API. Requires OPENAI_API_KEY.
"""

from app.models import HintRequest, HintResult


class OpenAIClient:
    """Client for OpenAI API (guess matching and hint generation)."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def check_guess_and_get_hint(self, request: HintRequest) -> HintResult:
        """
        Determine if the user's guess matches the correct game (fuzzy).
        If not, generate a short hint using Generation and Genre only.
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package required for OpenAIClient; install with: pip install openai")

        client = OpenAI(api_key=self._api_key)
        gen_text = ""
        if request.generation:
            gen_text = f"Generation: {request.generation.label}. Primary consoles: {', '.join(request.generation.primary_consoles)}."
        else:
            gen_text = "Generation: unknown."
        genres_text = ", ".join(request.genres) if request.genres else "unknown"

        system = (
            "You judge whether a player's guess matches the correct video game title (fuzzy match: same game, alternate titles, common abbreviations). "
            "Reply with exactly two lines: line 1 is either CORRECT or WRONG. If WRONG, line 2 is a single short hint (1 sentence). "
            "The hint must be interesting and specific to this game when possible: use the game's generation/era and genre as facts, but also add one distinctive detail—setting, theme, a well-known mechanic, studio, or legacy—that makes the hint memorable and unique. No spoilers, no game name."
        )
        user = (
            f"Correct game: {request.correct_game_name}. "
            f"Player guess: {request.guess}. "
            f"Use for hints: {gen_text} Genres: {genres_text}."
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=150,
        )
        content = (response.choices[0].message.content or "").strip()
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        first_line_upper = (lines[0].upper() if lines else "")
        # Word-boundary check: "CORRECT" as a whole word, not substring of "INCORRECT"
        correct = "CORRECT" in first_line_upper.split()
        hint_text = None
        if not correct and len(lines) >= 2:
            hint_text = lines[1].strip()
        return HintResult(correct=correct, hint_text=hint_text)
