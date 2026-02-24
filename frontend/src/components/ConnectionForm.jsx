import { useState } from 'react';

const EMPTY_FORM = {
  name: '',
  host: 'localhost',
  port: 3306,
  username: 'root',
  password: '',
  database_name: '',
};

export default function ConnectionForm({
  connection,
  onSave,
  onTest,
  isTesting,
  testResult,
}) {
  const [form, setForm] = useState(connection || EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: name === 'port' ? parseInt(value, 10) || '' : value,
    }));
  };

  const resolveForm = () => {
    const resolved = { ...form };
    if (!resolved.name.trim()) {
      resolved.name = `${resolved.host}/${resolved.database_name}`;
    }
    return resolved;
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave(resolveForm());
    } finally {
      setSaving(false);
    }
  };

  const inputClass =
    'w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent';

  return (
    <form onSubmit={handleSave} className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          Connection Name
        </label>
        <input
          name="name"
          value={form.name}
          onChange={handleChange}
          className={inputClass}
          placeholder={`${form.host}/${form.database_name || 'my_database'}`}
        />
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="col-span-2">
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Host
          </label>
          <input
            name="host"
            value={form.host}
            onChange={handleChange}
            className={inputClass}
            required
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Port
          </label>
          <input
            name="port"
            type="number"
            value={form.port}
            onChange={handleChange}
            className={inputClass}
            required
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Username
          </label>
          <input
            name="username"
            value={form.username}
            onChange={handleChange}
            className={inputClass}
            required
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Password
          </label>
          <input
            name="password"
            type="password"
            value={form.password}
            onChange={handleChange}
            className={inputClass}
          />
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          Database
        </label>
        <input
          name="database_name"
          value={form.database_name}
          onChange={handleChange}
          className={inputClass}
          placeholder="my_database"
          required
        />
      </div>

      {testResult && (
        <div
          className={`text-xs px-3 py-2 rounded-md ${
            testResult.success
              ? 'bg-green-50 text-green-700'
              : 'bg-red-50 text-red-700'
          }`}
        >
          {testResult.message}
        </div>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => onTest(form)}
          disabled={isTesting}
          className="flex-1 border border-gray-300 text-gray-700 px-3 py-1.5 rounded-md text-sm hover:bg-gray-50 disabled:opacity-50"
        >
          {isTesting ? 'Testing...' : 'Test Connection'}
        </button>
        <button
          type="submit"
          disabled={saving}
          className="flex-1 bg-blue-600 text-white px-3 py-1.5 rounded-md text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save Connection'}
        </button>
      </div>
    </form>
  );
}
