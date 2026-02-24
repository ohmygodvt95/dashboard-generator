import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

// --- Widgets ---
export const getWidgets = () => api.get('/widgets');
export const getWidget = (id) => api.get(`/widgets/${id}`);
export const createWidget = (data) => api.post('/widgets', data);
export const updateWidget = (id, data) => api.put(`/widgets/${id}`, data);
export const deleteWidget = (id) => api.delete(`/widgets/${id}`);
export const getWidgetData = (id, params = {}) =>
  api.get(`/widgets/${id}/data`, { params });

// --- Filters ---
export const getFilterOptions = (widgetId, filterId, params = {}) =>
  api.get(`/widgets/${widgetId}/filters/${filterId}/options`, {
    params,
  });
export const deleteWidgetFilter = (widgetId, filterId) =>
  api.delete(`/widgets/${widgetId}/filters/${filterId}`);

// --- Chat ---
export const getChatHistory = (widgetId) =>
  api.get(`/widgets/${widgetId}/chat`);
export const sendChatMessage = (widgetId, message) =>
  api.post(`/widgets/${widgetId}/chat`, { message });

/**
 * Send a chat message via SSE streaming.
 *
 * Calls the /chat/stream endpoint and returns an EventSource-
 * like interface.  The caller receives real-time agent
 * progress events.
 *
 * @param {string} widgetId  Widget UUID.
 * @param {string} message   User message text.
 * @param {object} callbacks Event handlers:
 *   - onAgentStart({agent, label, step})
 *   - onAgentDone({agent, step})
 *   - onResult(aiResponse)
 *   - onDone(finalPayload)   — messages + widget
 *   - onError(error)
 * @returns {function} abort  — call to cancel the stream.
 */
export function sendChatMessageStream(widgetId, message, callbacks = {}) {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`/api/widgets/${widgetId}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
        signal: controller.signal,
      });

      if (!res.ok) {
        callbacks.onError?.(new Error(`HTTP ${res.status}`));
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from the buffer
        const parts = buffer.split('\n\n');
        buffer = parts.pop(); // keep incomplete chunk

        for (const part of parts) {
          if (!part.trim()) continue;
          const lines = part.split('\n');
          let event = '';
          let data = '';
          for (const line of lines) {
            if (line.startsWith('event: ')) event = line.slice(7);
            if (line.startsWith('data: ')) data = line.slice(6);
          }
          if (!event || !data) continue;

          try {
            const payload = JSON.parse(data);
            switch (event) {
              case 'agent_start':
                callbacks.onAgentStart?.(payload);
                break;
              case 'agent_done':
                callbacks.onAgentDone?.(payload);
                break;
              case 'result':
                callbacks.onResult?.(payload);
                break;
              case 'done':
                callbacks.onDone?.(payload);
                break;
              case 'error':
                callbacks.onError?.(new Error(payload.message || 'Stream error'));
                break;
            }
          } catch {
            // skip malformed events
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        callbacks.onError?.(err);
      }
    }
  })();

  return () => controller.abort();
}

// --- Connections ---
export const getConnections = () => api.get('/connections');
export const getConnection = (id) => api.get(`/connections/${id}`);
export const createConnection = (data) => api.post('/connections', data);
export const updateConnection = (id, data) =>
  api.put(`/connections/${id}`, data);
export const deleteConnection = (id) => api.delete(`/connections/${id}`);
export const testConnection = (id) => api.post(`/connections/${id}/test`);
export const getConnectionSchema = (id) =>
  api.get(`/connections/${id}/schema`);

export default api;
