import { useEffect, useMemo, useState } from "react";
import { saveDataSource, testDataSource } from "../api/ragAdminApi";

const emptyForm = {
  source_name: "",
  source_type: "jira",

  // common
  source_url: "",
  auth_type: "basic",
  chunk_size: 1000,
  chunk_overlap: 150,
  collection_name: "KB_All",
  is_enabled: true,
  sync_frequency: "daily",

  // jira
  username: "",
  password: "",
  token: "",
  api_key: "",
  project_key: "",
  jql: "",
  issue_start: "",
  issue_end: "",

  // sharepoint (API)
  site_id: "",
  drive_id: "",
  list_id: "",
  folder_id: "",
  folder_path: "",
  client_id: "",
  client_secret: "",
  tenant_id_secret: "",
};

function normalizeSource(source) {
  return {
    ...emptyForm,
    ...source,
    chunk_size: Number(source?.chunk_size ?? 1000),
    chunk_overlap: Number(source?.chunk_overlap ?? 150),
    is_enabled: source?.is_enabled ?? true,
    source_type: source?.source_type || "jira",
    auth_type:
      source?.auth_type ||
      ((source?.source_type || "jira") === "sharepoint"
        ? "oauth"
        : source?.source_type === "sharepoint_local"
        ? "local"
        : "basic"),
    issue_start:
      source?.issue_start === null || source?.issue_start === undefined
        ? ""
        : source.issue_start,
    issue_end:
      source?.issue_end === null || source?.issue_end === undefined
        ? ""
        : source.issue_end,
  };
}

export default function DataSourceForm({
  tenantId,
  ragSetup,
  firstSource,
  onSaved,
}) {
  const [sourcesByType, setSourcesByType] = useState({});
  const [selectedSourceType, setSelectedSourceType] = useState("jira");
  const [form, setForm] = useState(emptyForm);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);

  // 🔥 Load JSON → map by source_type
  useEffect(() => {
    const loadedSources =
      ragSetup?.data_sources || (firstSource ? [firstSource] : []);

    const grouped = {};
    loadedSources.forEach((src) => {
      const type = (src.source_type || "").toLowerCase();
      if (type) grouped[type] = src;
    });

    setSourcesByType(grouped);

    let initialType = "jira";

    if (grouped["jira"]) initialType = "jira";
    else if (grouped["sharepoint"]) initialType = "sharepoint";
    else if (grouped["sharepoint_local"]) initialType = "sharepoint_local";

    setSelectedSourceType(initialType);

    if (grouped[initialType]) {
      setForm(normalizeSource(grouped[initialType]));
    }
  }, [ragSetup, firstSource]);

  const sourceOptions = useMemo(
    () => [
      { label: "Jira", value: "jira" },
      { label: "SharePoint", value: "sharepoint" },
      { label: "SharePoint Local", value: "sharepoint_local" },
    ],
    []
  );

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;

    setForm((prev) => ({
      ...prev,
      [name]:
        type === "checkbox"
          ? checked
          : ["chunk_size", "chunk_overlap"].includes(name)
          ? Number(value)
          : value,
    }));
  };

  // 🔥 Switch source type → load from JSON
  const handleSourceTypeChange = (e) => {
    const newType = e.target.value.toLowerCase();
    setSelectedSourceType(newType);
    setStatus("");

    const sourceFromJson = sourcesByType[newType];

    if (sourceFromJson) {
      setForm(normalizeSource(sourceFromJson));
      return;
    }

    // new empty form for that type
    setForm({
      ...emptyForm,
      source_type: newType,
      auth_type:
        newType === "sharepoint"
          ? "oauth"
          : newType === "sharepoint_local"
          ? "local"
          : "basic",
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setStatus("");

    try {
      const payload = {
        ...form,
        issue_start: form.issue_start === "" ? null : Number(form.issue_start),
        issue_end: form.issue_end === "" ? null : Number(form.issue_end),
      };

      const data = await saveDataSource(tenantId, payload);
      setStatus("Saved successfully");

      // update local state
      setSourcesByType((prev) => ({
        ...prev,
        [payload.source_type]: payload,
      }));

      onSaved?.(data);
    } catch (err) {
      setStatus(err?.message || "Save failed");
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setStatus("");

    try {
      await testDataSource(tenantId, form);
      setStatus("Connection successful");
    } catch (err) {
      setStatus(err?.message || "Connection failed");
    } finally {
      setTesting(false);
    }
  };

  return (
    <form className="setup-form" onSubmit={handleSubmit}>
      <h3>Data Source Configuration</h3>

      <div className="form-grid">
        <label>
          Source Type
          <select
            value={selectedSourceType}
            onChange={handleSourceTypeChange}
          >
            {sourceOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          Source Name
          <input
            name="source_name"
            value={form.source_name}
            onChange={handleChange}
          />
        </label>

        <label>
          Source URL / Folder Path
          <input
            name="source_url"
            value={form.source_url}
            onChange={handleChange}
          />
        </label>

        <label>
          Auth Type
          <input name="auth_type" value={form.auth_type} readOnly />
        </label>

        {/* 🔥 Jira */}
        {form.source_type === "jira" && (
          <>
            <input name="username" value={form.username} onChange={handleChange} placeholder="Username" />
            <input name="token" value={form.token} onChange={handleChange} placeholder="Token" />
            <input name="project_key" value={form.project_key} onChange={handleChange} placeholder="Project Key" />
            <input name="jql" value={form.jql} onChange={handleChange} placeholder="JQL" />
          </>
        )}

        {/* 🔥 SharePoint API */}
        {form.source_type === "sharepoint" && (
          <>
            <input name="site_id" value={form.site_id} onChange={handleChange} placeholder="Site ID" />
            <input name="drive_id" value={form.drive_id} onChange={handleChange} placeholder="Drive ID" />
            <input name="folder_path" value={form.folder_path} onChange={handleChange} placeholder="Folder Path" />
          </>
        )}

        {/* 🔥 SharePoint Local */}
        {form.source_type === "sharepoint_local" && (
          <>
            <input
              name="source_url"
              value={form.source_url}
              onChange={handleChange}
              placeholder="C:/Users/.../SharePointDocs"
            />
          </>
        )}

        <input
          type="number"
          name="chunk_size"
          value={form.chunk_size}
          onChange={handleChange}
          placeholder="Chunk Size"
        />

        <input
          type="number"
          name="chunk_overlap"
          value={form.chunk_overlap}
          onChange={handleChange}
          placeholder="Chunk Overlap"
        />

        <input
          name="collection_name"
          value={form.collection_name}
          onChange={handleChange}
          placeholder="Collection Name"
        />

        <label>
          <input
            type="checkbox"
            name="is_enabled"
            checked={form.is_enabled}
            onChange={handleChange}
          />
          Enabled
        </label>
      </div>

      <div className="action-row">
        <button type="button" onClick={handleTest}>
          {testing ? "Testing..." : "Test"}
        </button>

        <button type="submit">
          {loading ? "Saving..." : "Save"}
        </button>
      </div>

      {status && <p>{status}</p>}
    </form>
  );
}