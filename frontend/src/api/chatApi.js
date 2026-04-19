import client from "./client";

export async function searchTickets(payload) {
  try {
    const response = await client.post("/api/v1/chat", payload);
    return response.data;
  } catch (error) {
    console.log("AXIOS ERROR:", error.response);

    // 🔥 return backend response even if 500
    if (error.response && error.response.data) {
      return error.response.data;
    }

    throw error;
  }
}

export async function loginUser(payload) {
  console.log("login api call successfully")
  console.log(payload)
  const res = await client.post("/api/v1/login", payload)
  return res.data
}

export async function closeTicket(payload) {
  // payload: { tenant_id, ticket_id, reason }
  const res = await client.post("/api/v1/tickets/close", payload)
  return res.data
}
