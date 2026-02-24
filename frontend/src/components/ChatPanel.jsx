import { useState, useRef, useEffect } from 'react';

export default function ChatPanel({ messages, onSend, isLoading, agentSteps }) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, agentSteps]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    onSend(input.trim());
    setInput('');
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 bg-white">
        <h3 className="text-sm font-semibold text-gray-700">AI Assistant</h3>
        <p className="text-xs text-gray-500">
          Describe the chart you want to create
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 text-sm mt-8">
            <p>👋 Start by describing the chart you want.</p>
            <p className="mt-2 text-xs">
              Example: "Show monthly revenue as a bar chart"
            </p>
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-800'
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-lg px-3 py-2 text-sm text-gray-600 min-w-[200px]">
              <AgentProgress steps={agentSteps} />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSubmit} className="p-3 border-t border-gray-200 bg-white">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Describe your chart..."
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}

const AGENT_ICONS = {
  summarizer: '📝',
  request_analyzer: '🔍',
  schema_analyzer: '🗄️',
  query_builder: '⚙️',
  filter_builder: '🔧',
  chart_builder: '📊',
};

function AgentProgress({ steps }) {
  if (!steps || steps.length === 0) {
    return <span className="animate-pulse">Thinking…</span>;
  }

  return (
    <div className="space-y-1.5">
      {steps.map((step, idx) => {
        const icon = AGENT_ICONS[step.agent] || '⏳';
        const isActive = step.status === 'running';
        const isDone = step.status === 'done';

        return (
          <div
            key={`${step.agent}-${idx}`}
            className={`flex items-center gap-2 text-xs ${
              isDone ? 'text-gray-400' : 'text-gray-700'
            }`}
          >
            <span>{icon}</span>
            <span className={isActive ? 'font-medium' : ''}>
              {step.label || step.agent}
            </span>
            {isActive && (
              <span className="animate-spin inline-block w-3 h-3 border border-gray-400 border-t-transparent rounded-full" />
            )}
            {isDone && (
              <svg className="w-3 h-3 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            )}
          </div>
        );
      })}
    </div>
  );
}
