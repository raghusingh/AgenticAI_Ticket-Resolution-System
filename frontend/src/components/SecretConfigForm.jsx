import { useEffect, useState } from "react";
import { saveSecrets, testSecrets } from "../api/ragAdminApi";

export default function SecretConfigForm({ tenantId, initialData, onSaved }) {
  const [form, setForm] = useState({
    llm_api_key: "",
    embedding_api_key: "",
    vector_db_api_key: "",
  });
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (initialData) setForm(initialData);
  }, [initialData]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    const data = await saveSecrets(tenantId, form);
    setStatus("Saved secret configuration.");
    onSaved?.(data);
  };

  const handleTest = async () => {
    const result = await testSecrets(tenantId, form);
    setStatus(result.message);
  };

  return (
    <form className="setup-form" onSubmit={handleSave}>
      <h3>API key configuration</h3>
      <div className="form-grid">
        <label>LLM API Key<input type="password" name="llm_api_key" value={form.llm_api_key || ""} onChange={handleChange} /></label>
        <label>Embedding API Key<input type="password" name="embedding_api_key" value={form.embedding_api_key || ""} onChange={handleChange} /></label>
        <label>Vector DB API Key<input type="password" name="vector_db_api_key" value={form.vector_db_api_key || ""} onChange={handleChange} /></label>
      </div>
      <div className="action-row">
        <button type="button" onClick={handleTest}>Test key</button>
        <button type="submit">Save secrets</button>
      </div>
      {status && <p className="status-ok">{status}</p>}
    </form>
  );
}
