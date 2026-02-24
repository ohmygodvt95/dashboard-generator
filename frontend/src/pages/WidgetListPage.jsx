import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { getWidgets, createWidget, deleteWidget } from '../services/api';

export default function WidgetListPage() {
  const [widgets, setWidgets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const navigate = useNavigate();

  const fetchWidgets = async () => {
    try {
      const res = await getWidgets();
      setWidgets(res.data);
    } catch (err) {
      console.error('Failed to fetch widgets:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWidgets();
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newName.trim()) return;
    try {
      const res = await createWidget({ name: newName.trim() });
      navigate(`/widgets/${res.data.id}`);
    } catch (err) {
      console.error('Failed to create widget:', err);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this widget?')) return;
    try {
      await deleteWidget(id);
      setWidgets((prev) => prev.filter((w) => w.id !== id));
    } catch (err) {
      console.error('Failed to delete widget:', err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-500">Loading widgets...</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Widgets</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
        >
          + New Widget
        </button>
      </div>

      {showCreate && (
        <form
          onSubmit={handleCreate}
          className="mb-6 p-4 bg-white rounded-lg border border-gray-200 flex gap-3"
        >
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Widget name..."
            className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            autoFocus
          />
          <button
            type="submit"
            className="bg-blue-600 text-white px-4 py-2 rounded-md text-sm hover:bg-blue-700"
          >
            Create
          </button>
          <button
            type="button"
            onClick={() => {
              setShowCreate(false);
              setNewName('');
            }}
            className="border border-gray-300 text-gray-600 px-4 py-2 rounded-md text-sm hover:bg-gray-50"
          >
            Cancel
          </button>
        </form>
      )}

      {widgets.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-lg border border-gray-200">
          <p className="text-4xl mb-3">📊</p>
          <p className="text-gray-500 text-sm">No widgets yet</p>
          <p className="text-gray-400 text-xs mt-1">
            Create your first widget to get started
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {widgets.map((widget) => (
            <div
              key={widget.id}
              className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between mb-2">
                <Link
                  to={`/widgets/${widget.id}`}
                  className="text-base font-semibold text-gray-900 hover:text-blue-600"
                >
                  {widget.name}
                </Link>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    widget.is_active
                      ? 'bg-green-100 text-green-700'
                      : 'bg-gray-100 text-gray-500'
                  }`}
                >
                  {widget.is_active ? 'Active' : 'Draft'}
                </span>
              </div>
              <p className="text-sm text-gray-500 mb-3">
                {widget.description || 'No description'}
              </p>
              <div className="flex items-center justify-between text-xs text-gray-400">
                <span>{widget.chart_type || 'Not configured'}</span>
                <div className="flex gap-2">
                  <Link
                    to={`/widgets/${widget.id}`}
                    className="text-blue-600 hover:underline"
                  >
                    Edit
                  </Link>
                  <button
                    onClick={() => handleDelete(widget.id)}
                    className="text-red-500 hover:underline"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
