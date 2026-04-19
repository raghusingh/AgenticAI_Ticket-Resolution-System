import client from "./client";

export async function getTheme(tenantId) {
  const response = await client.get(`/api/v1/theme/${tenantId}`);
  return response.data;
}
