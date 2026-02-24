import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import ChatPanel from '../components/ChatPanel';
import ChartPreview from '../components/ChartPreview';
import ConnectionForm from '../components/ConnectionForm';
import FilterBar from '../components/FilterBar';
import {
  getWidget,
  updateWidget,
  getWidgetData,
  getChatHistory,
  sendChatMessageStream,
  getConnections,
  createConnection,
  updateConnection,
  deleteConnection,
  testConnection,
  getConnectionSchema,
  deleteWidgetFilter,
} from '../services/api';

export default function WidgetEditorPage() {
  const { id } = useParams();
  const [widget, setWidget] = useState(null);
  const [messages, setMessages] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chartData, setChartData] = useState([]);
  const [connections, setConnections] = useState([]);
  const [selectedConnId, setSelectedConnId] = useState('');
  const [showConnForm, setShowConnForm] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [filterValues, setFilterValues] = useState({});
  const [tab, setTab] = useState('chat');
  const [loading, setLoading] = useState(true);
  const [schema, setSchema] = useState(null);
  const [agentSteps, setAgentSteps] = useState([]);
  const [connSearch, setConnSearch] = useState('');
  const abortRef = useRef(null);
  const embedUrl = `${window.location.origin}/widgets/${id}/embed`;

  const fetchWidget = useCallback(async () => {
    try {
      const res = await getWidget(id);
      setWidget(res.data);
      setSelectedConnId(res.data.connection_id || '');
    } catch (err) {
      console.error('Failed to fetch widget:', err);
    }
  }, [id]);

  const fetchChatHistory = useCallback(async () => {
    try {
      const res = await getChatHistory(id);
      setMessages(res.data);
    } catch (err) {
      console.error('Failed to fetch chat:', err);
    }
  }, [id]);

  const fetchConnections = useCallback(async () => {
    try {
      const res = await getConnections();
      setConnections(res.data);
    } catch (err) {
      console.error('Failed to fetch connections:', err);
    }
  }, []);

  const fetchData = useCallback(async () => {
    if (!widget?.has_query || !widget?.connection_id) return;
    try {
      const params = {};
      Object.entries(filterValues).forEach(([key, val]) => {
        if (typeof val === 'object' && val !== null) {
          if (val.start) params[`${key}_start`] = val.start;
          if (val.end) params[`${key}_end`] = val.end;
        } else if (val) {
          params[key] = val;
        }
      });
      const res = await getWidgetData(id, params);
      setChartData(res.data);
    } catch (err) {
      console.error('Failed to fetch data:', err);
    }
  }, [id, widget?.has_query, widget?.connection_id, filterValues]);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([fetchWidget(), fetchChatHistory(), fetchConnections()]);
      setLoading(false);
    };
    init();
  }, [fetchWidget, fetchChatHistory, fetchConnections]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSendMessage = async (message) => {
    setChatLoading(true);
    setAgentSteps([]);
    setMessages((prev) => [
      ...prev,
      { id: `temp-${Date.now()}`, role: 'user', content: message },
    ]);

    abortRef.current = sendChatMessageStream(id, message, {
      onAgentStart: ({ agent, label }) => {
        setAgentSteps((prev) => [
          ...prev,
          { agent, label, status: 'running' },
        ]);
      },
      onAgentDone: ({ agent }) => {
        setAgentSteps((prev) =>
          prev.map((s) =>
            s.agent === agent ? { ...s, status: 'done' } : s,
          ),
        );
      },
      onDone: (payload) => {
        setMessages((prev) => [
          ...prev.filter((m) => !m.id?.startsWith?.('temp-')),
          ...payload.messages,
        ]);
        if (payload.widget) {
          setWidget(payload.widget);
          fetchData();
        }
        setChatLoading(false);
        setAgentSteps([]);
      },
      onError: () => {
        setMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: 'assistant',
            content: 'Sorry, something went wrong. Please try again.',
          },
        ]);
        setChatLoading(false);
        setAgentSteps([]);
      },
    });
  };

  const handleConnectionSave = async (connData) => {
    try {
      let conn;
      if (connData.id) {
        conn = await updateConnection(connData.id, connData);
      } else {
        conn = await createConnection(connData);
      }
      const savedConn = conn.data;
      await updateWidget(id, { connection_id: savedConn.id });
      setSelectedConnId(savedConn.id);
      setWidget((prev) => ({ ...prev, connection_id: savedConn.id }));
      setShowConnForm(false);
      await fetchConnections();

      // Fetch schema for AI context
      try {
        const schemaRes = await getConnectionSchema(savedConn.id);
        setSchema(schemaRes.data);
      } catch (e) {
        console.error('Failed to fetch schema:', e);
      }
    } catch (err) {
      console.error('Failed to save connection:', err);
    }
  };

  const handleTestConnection = async (connData) => {
    setIsTesting(true);
    setTestResult(null);
    try {
      if (connData.id) {
        const res = await testConnection(connData.id);
        setTestResult(res.data);
      } else {
        // Save connection first, then test
        const resolved = { ...connData };
        if (!resolved.name?.trim()) {
          resolved.name = `${resolved.host}/${resolved.database_name}`;
        }
        const conn = await createConnection(resolved);
        const res = await testConnection(conn.data.id);
        setTestResult(res.data);
      }
    } catch (err) {
      setTestResult({
        success: false,
        message: err.response?.data?.detail || 'Connection failed',
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSelectConnection = async (connId) => {
    setSelectedConnId(connId);
    await updateWidget(id, { connection_id: connId });
    setWidget((prev) => ({ ...prev, connection_id: connId }));
    if (connId) {
      try {
        const schemaRes = await getConnectionSchema(connId);
        setSchema(schemaRes.data);
      } catch (e) {
        console.error('Failed to fetch schema:', e);
      }
    }
  };

  const handleDeleteFilter = async (filterId) => {
    try {
      await deleteWidgetFilter(id, filterId);
      setWidget((prev) => ({
        ...prev,
        filters: prev.filters.filter((f) => f.id !== filterId),
      }));
    } catch (err) {
      console.error('Failed to delete filter:', err);
    }
  };

  const handleDeleteConnection = async (connId) => {
    if (!window.confirm('Delete this connection?')) return;
    try {
      await deleteConnection(connId);
      setConnections((prev) => prev.filter((c) => c.id !== connId));
      if (selectedConnId === connId) {
        setSelectedConnId('');
        setSchema(null);
        await updateWidget(id, { connection_id: null });
        setWidget((prev) => ({ ...prev, connection_id: null }));
      }
    } catch (err) {
      console.error('Failed to delete connection:', err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  if (!widget) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-500">Widget not found</p>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-7rem)]">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-gray-900">{widget.name}</h1>
        <div className="flex items-center gap-2">
          <input
            readOnly
            value={embedUrl}
            className="text-xs border border-gray-300 rounded px-2 py-1 w-64 bg-gray-50"
            onClick={(e) => {
              e.target.select();
              navigator.clipboard.writeText(embedUrl);
            }}
          />
          <span className="text-xs text-gray-400">Embed URL</span>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4 h-[calc(100%-3rem)]">
        {/* Left: Chat & Config */}
        <div className="col-span-4 bg-white rounded-lg border border-gray-200 flex flex-col overflow-hidden">
          <div className="flex border-b border-gray-200">
            <button
              onClick={() => setTab('chat')}
              className={`flex-1 px-3 py-2 text-sm font-medium ${
                tab === 'chat'
                  ? 'text-blue-600 border-b-2 border-blue-600'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Chat
            </button>
            <button
              onClick={() => setTab('connection')}
              className={`flex-1 px-3 py-2 text-sm font-medium ${
                tab === 'connection'
                  ? 'text-blue-600 border-b-2 border-blue-600'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              DB Connection
            </button>
          </div>

          <div className="flex-1 overflow-hidden">
            {tab === 'chat' ? (
              <ChatPanel
                messages={messages}
                onSend={handleSendMessage}
                isLoading={chatLoading}
                agentSteps={agentSteps}
              />
            ) : (
              <div className="p-4 overflow-y-auto h-full space-y-4">
                {/* Existing connections */}
                {connections.length > 0 && !showConnForm && (
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Select Existing Connection
                    </label>
                    {connections.length > 3 && (
                      <input
                        type="text"
                        value={connSearch}
                        onChange={(e) => setConnSearch(e.target.value)}
                        placeholder="Search connections..."
                        className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm mb-2 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    )}
                    <div className="space-y-1 max-h-48 overflow-y-auto">
                      {connections
                        .filter((c) => {
                          if (!connSearch.trim()) return true;
                          const q = connSearch.toLowerCase();
                          return (
                            c.name?.toLowerCase().includes(q) ||
                            c.host?.toLowerCase().includes(q) ||
                            c.database_name?.toLowerCase().includes(q)
                          );
                        })
                        .map((c) => (
                          <div
                            key={c.id}
                            className={`flex items-center justify-between rounded-md border px-3 py-2 text-sm cursor-pointer transition-colors ${
                              selectedConnId === c.id
                                ? 'border-blue-500 bg-blue-50 text-blue-700'
                                : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50 text-gray-700'
                            }`}
                            onClick={() => handleSelectConnection(c.id)}
                          >
                            <div className="min-w-0 flex-1">
                              <div className="font-medium truncate">{c.name}</div>
                              <div className="text-xs text-gray-400 truncate">
                                {c.host}/{c.database_name}
                              </div>
                            </div>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteConnection(c.id);
                              }}
                              className="ml-2 p-1 text-gray-400 hover:text-red-500 rounded shrink-0"
                              title="Delete connection"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          </div>
                        ))}
                    </div>
                  </div>
                )}

                <button
                  onClick={() => setShowConnForm(!showConnForm)}
                  className="text-sm text-blue-600 hover:underline"
                >
                  {showConnForm ? 'Cancel' : '+ New Connection'}
                </button>

                {showConnForm && (
                  <ConnectionForm
                    onSave={handleConnectionSave}
                    onTest={handleTestConnection}
                    isTesting={isTesting}
                    testResult={testResult}
                  />
                )}

                {schema && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-600 mb-2">
                      Database Schema
                    </h4>
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {schema.tables?.map((table) => (
                        <details key={table.name} className="text-xs">
                          <summary className="cursor-pointer font-medium text-gray-700 py-1">
                            {table.name} ({table.columns?.length} columns)
                          </summary>
                          <ul className="ml-4 mt-1 space-y-0.5 text-gray-500">
                            {table.columns?.map((col) => (
                              <li key={col.name}>
                                {col.name}{' '}
                                <span className="text-gray-400">
                                  {col.type}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </details>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right: Preview */}
        <div className="col-span-8 bg-white rounded-lg border border-gray-200 flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-700">Preview</h3>
            {widget.chart_type && (
              <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded">
                {widget.chart_type}
              </span>
            )}
          </div>

          {widget.filters?.length > 0 && (
            <div className="px-4 pt-3">
              <FilterBar
                filters={widget.filters}
                values={filterValues}
                onChange={setFilterValues}
                widgetId={id}
                onDeleteFilter={handleDeleteFilter}
              />
            </div>
          )}

          <div className="flex-1 min-h-0">
            <ChartPreview
              chartType={widget.chart_type || 'bar'}
              chartConfig={widget.chart_config}
              data={chartData}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
