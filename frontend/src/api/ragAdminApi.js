import client from "./client";

export async function getRagSetup(tenantId) {
  const response = await client.get(`/api/v1/admin/rag-config/${tenantId}`);
  return response.data;
}

export async function saveModelConfig(tenantId, payload) {
  const response = await client.post(`/api/v1/admin/rag-config/models/${tenantId}`, payload);
  return response.data;
}

export async function saveDataSource(tenantId, payload) {
  const response = await client.post(`/api/v1/admin/rag-config/sources/${tenantId}`, payload);
  return response.data;
}

export async function testDataSource(tenantId, payload) {
  const response = await client.post(`/api/v1/admin/rag-config/sources/${tenantId}/test`, payload);
  return response.data;
}

export async function saveSecrets(tenantId, payload) {
  const response = await client.post(`/api/v1/admin/rag-config/secrets/${tenantId}`, payload);
  return response.data;
}

export async function testSecrets(tenantId, payload) {
  const response = await client.post(`/api/v1/admin/rag-config/secrets/${tenantId}/test`, payload);
  return response.data;
}
