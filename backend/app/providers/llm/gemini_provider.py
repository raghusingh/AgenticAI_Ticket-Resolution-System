from google import genai


class GeminiProvider:
    def __init__(
        self,
        model: str,
        api_key: str,
        temperature: float = 0,
        max_tokens: int = 1000,
        top_k: int = 5,
        top_p: float = 0.9,
        **kwargs  # 🔥 absorbs any extra future params
    ):
        if not api_key:
            raise ValueError("LLM API key missing")

        self.client = genai.Client(api_key=api_key)
        self.model = model

        # Store configs
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_k = top_k
        self.top_p = top_p

    def generate(self, question: str, context=None):
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=question,
                config={
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_tokens,
                    "top_k": self.top_k,
                    "top_p": self.top_p,
                }
            )

            return response.text

        except Exception as e:
            return f"LLM Error: {str(e)}"

    def model_name(self):
        return self.model