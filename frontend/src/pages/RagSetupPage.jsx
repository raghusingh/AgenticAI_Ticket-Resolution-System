import { useEffect, useState } from "react";
import ModelConfigForm from "../components/ModelConfigForm";
import DataSourceForm from "../components/DataSourceForm";
import SecretConfigForm from "../components/SecretConfigForm";
import { getRagSetup } from "../api/ragAdminApi";

export default function RagSetupPage({ tenantId }) {
  const [setup, setSetup] = useState(null);
  const [loading, setLoading] = useState(true);

  async function loadSetup() {
    try {
      setLoading(true);
      const data = await getRagSetup(tenantId);
      setSetup(data);
    } catch (err) {
      console.error("Failed to load setup:", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (tenantId) loadSetup();
  }, [tenantId]);

  if (loading || !setup) {
    return (
      <div className="chat-window">
        <p>Loading RAG setup...</p>
      </div>
    );
  }

  return (
    <div className="chat-window">
      <h2>⚙ RAG Setup</h2>

      <p style={{ opacity: 0.7, marginBottom: "20px" }}>
        Configure providers, sources, and secrets for tenant{" "}
        <strong>{tenantId}</strong>
      </p>

      <ModelConfigForm
        tenantId={tenantId}
        initialData={setup.models}
        onSaved={loadSetup}
      />

      <DataSourceForm
        tenantId={tenantId}
        ragSetup={setup}
        firstSource={setup?.data_sources?.[0]}
        onSaved={loadSetup}
      />

      <SecretConfigForm
        tenantId={tenantId}
        initialData={setup.secrets}
        onSaved={loadSetup}
      />

      <div style={{ marginTop: 20 }}>
        <h3>Current Configuration</h3>
        <pre style={{
          background: "#111",
          color: "#00ff88",
          padding: "10px",
          borderRadius: "8px",
          overflowX: "auto"
        }}>
          {JSON.stringify(setup, null, 2)}
        </pre>
      </div>
    </div>
  );
}