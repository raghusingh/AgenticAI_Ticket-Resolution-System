from typing import Any, Dict, List
from openai import OpenAI
from app.contracts.llm_provider import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        model: str,
        api_key: str,
        temperature: float = 0,
        max_tokens: int = 1000,
        top_k: int = 5,
        top_p: float = 0.9,
        **kwargs,
    ):
        if not api_key:
            raise ValueError("LLM API key missing")

        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_k = top_k
        self.top_p = top_p

    def generate(self, question: str, context: List[Dict[str, Any]] | None = None) -> str:
        try:
            context_text = "\n\n".join(
                (item.get("metadata", {}) or {}).get("text", "")
                for item in (context or [])
            )

            final_prompt = f"""Answer based on context:

{context_text}

Question: {question}"""

            response = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {
                        "role": "system",
                        "content": "Answer from the context when possible. If context is insufficient, say so clearly.",
                    },
                    {
                        "role": "user",
                        "content": final_prompt,
                    },
                ],
                max_tokens=self.max_tokens,
            )

            return response.choices[0].message.content or ""

        except Exception as e:
            return f"LLM Error: {str(e)}"

    def model_name(self) -> str:
        return self.model