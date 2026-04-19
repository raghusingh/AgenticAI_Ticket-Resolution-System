from google import genai


class GoogleEmbeddingProvider:
    def __init__(self, model, api_key):
        if not api_key:
            raise ValueError("Embedding API key missing")

        self.client = genai.Client(api_key=api_key)
        self.model = model

    def embed_documents(self, texts):
        embeddings = []

        for text in texts:
            response = self.client.models.embed_content(
                model=self.model,
                contents=text
            )
            embeddings.append(response.embedding)

        return embeddings

    def model_name(self):
        return self.model