from openai import OpenAI


class OpenAIEmbeddingProvider:
    def __init__(self, model, api_key):
        if not api_key:
            raise ValueError("OpenAI API key missing")

        self.client = OpenAI(api_key=api_key)
        self.model = model

    def embed_documents(self, texts):
        response = self.client.embeddings.create(
            model=self.model,
            input=texts
        )

        return [item.embedding for item in response.data]

    def model_name(self):
        return self.model