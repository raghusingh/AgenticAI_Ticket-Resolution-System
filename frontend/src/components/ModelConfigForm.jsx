import { useEffect, useState } from "react";
import { saveModelConfig } from "../api/ragAdminApi";

export default function ModelConfigForm({ tenantId, initialData, onSaved }) {
  const [form, setForm] = useState({
    llm_provider: "openai",
    llm_model_name: "gpt-4.1-mini",
    embedding_provider: "huggingface",
    embedding_model_name: "sentence-transformers/all-MiniLM-L6-v2",
    temperature: 0.2,
    top_k: 5,
    max_tokens: 1000,
  });
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (initialData) setForm(initialData);
  }, [initialData]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: ["temperature", "top_k", "max_tokens"].includes(name) ? Number(value) : value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const data = await saveModelConfig(tenantId, form);
    setStatus("Saved model configuration.");
    onSaved?.(data);
  };

  return (
    <form className="setup-form" onSubmit={handleSubmit}>
      <h3>Model configuration</h3>
      <div className="form-grid">
          <label>
            LLM Provider
            <select name="llm_provider" value={form.llm_provider} onChange={handleChange}>
              <option value="Google">Google</option>
              <option value="OpenAI">OpenAI</option>
            </select>
          </label>

          <label>
            LLM Model
            <input
              name="llm_model_name"
              value={form.llm_model_name}
              onChange={handleChange}
            />
          </label>

          <label>
            Embedding Provider
            <select
              name="embedding_provider"
              value={form.embedding_provider}
              onChange={handleChange}
            >
              <option value="Google">Google</option>
              <option value="OpenAI">OpenAI</option>
            </select>
          </label>

          <label>
            Embedding Model
            <input
              name="embedding_model_name"
              value={form.embedding_model_name}
              onChange={handleChange}
            />
          </label>

          <label>
            Temperature
            <input
              name="temperature"
              type="number"
              value={form.temperature}
              onChange={handleChange}
            />
          </label>

          <label>
            Top K
            <input
              name="top_k"
              type="number"
              value={form.top_k}
              onChange={handleChange}
            />
          </label>

          <label>
            Max Tokens
            <input
              name="max_tokens"
              type="number"
              value={form.max_tokens}
              onChange={handleChange}
            />
          </label>

        </div>
      <button type="submit">Save model config</button>
      {status && <p className="status-ok">{status}</p>}
    </form>
  );
}
