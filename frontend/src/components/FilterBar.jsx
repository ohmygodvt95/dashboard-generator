import { useState, useEffect, useRef, useCallback } from 'react';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import { getFilterOptions } from '../services/api';

/**
 * Convert a "YYYY-MM-DD" string to a Date object.
 * Returns null when the input is empty or invalid.
 */
function parseDate(str) {
  if (!str) return null;
  const d = new Date(str + 'T00:00:00');
  return isNaN(d.getTime()) ? null : d;
}

/**
 * Format a Date object to "YYYY-MM-DD" string.
 * Returns empty string when the input is null.
 */
function formatDate(date) {
  if (!date) return '';
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export default function FilterBar({
  filters,
  values,
  onChange,
  widgetId,
  onDeleteFilter,
}) {
  if (!filters || !filters.length) return null;

  const handleChange = (paramName, value) => {
    onChange({ ...values, [paramName]: value });
  };

  return (
    <div className="flex flex-wrap gap-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
      {filters.map((filter) => (
        <div key={filter.id} className="flex items-end gap-1">
          <FilterField
            filter={filter}
            widgetId={widgetId}
            value={
              filter.filter_type === 'date_range'
                ? (values[filter.param_name] || { start: '', end: '' })
                : (values[filter.param_name] ?? filter.default_value ?? '')
            }
            onChange={(val) => handleChange(filter.param_name, val)}
          />
          {onDeleteFilter && (
            <button
              type="button"
              onClick={() => onDeleteFilter(filter.id)}
              className="mb-0.5 p-1 text-gray-400 hover:text-red-500 transition-colors"
              title="Remove filter"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-4 w-4"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M4.293 4.293a1 1 0 011.414 0L10
                   8.586l4.293-4.293a1 1 0 111.414
                   1.414L11.414 10l4.293 4.293a1 1 0
                   01-1.414 1.414L10 11.414l-4.293
                   4.293a1 1 0 01-1.414-1.414L8.586
                   10 4.293 5.707a1 1 0 010-1.414z"
                  clipRule="evenodd"
                />
              </svg>
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function FilterField({ filter, widgetId, value, onChange }) {
  const labelClass =
    'block text-xs font-medium text-gray-600 mb-1';
  const inputClass =
    'rounded-md border border-gray-300 px-2 py-1 text-sm ' +
    'focus:outline-none focus:ring-2 focus:ring-blue-500';

  switch (filter.filter_type) {
    case 'select':
      return (
        <SearchableSelect
          filter={filter}
          widgetId={widgetId}
          value={value}
          onChange={onChange}
          labelClass={labelClass}
          inputClass={inputClass}
        />
      );

    case 'date':
      return (
        <div>
          <label className={labelClass}>{filter.label}</label>
          <DatePicker
            selected={parseDate(value)}
            onChange={(date) => onChange(formatDate(date))}
            dateFormat="yyyy-MM-dd"
            isClearable
            placeholderText="Select date"
            className={inputClass}
          />
        </div>
      );

    case 'date_range': {
      const rangeVal = typeof value === 'object' ? value : {};
      const startDate = parseDate(rangeVal.start);
      const endDate = parseDate(rangeVal.end);
      return (
        <div className="flex gap-2 items-end">
          <div>
            <label className={labelClass}>
              {filter.label} (Start)
            </label>
            <DatePicker
              selected={startDate}
              onChange={(date) =>
                onChange({ ...rangeVal, start: formatDate(date) })
              }
              selectsStart
              startDate={startDate}
              endDate={endDate}
              maxDate={endDate}
              dateFormat="yyyy-MM-dd"
              isClearable
              placeholderText="Start date"
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>
              {filter.label} (End)
            </label>
            <DatePicker
              selected={endDate}
              onChange={(date) =>
                onChange({ ...rangeVal, end: formatDate(date) })
              }
              selectsEnd
              startDate={startDate}
              endDate={endDate}
              minDate={startDate}
              dateFormat="yyyy-MM-dd"
              isClearable
              placeholderText="End date"
              className={inputClass}
            />
          </div>
        </div>
      );
    }

    case 'number':
      return (
        <div>
          <label className={labelClass}>{filter.label}</label>
          <input
            type="number"
            value={value}
            min={filter.config?.min}
            max={filter.config?.max}
            step={filter.config?.step}
            onChange={(e) => onChange(e.target.value)}
            placeholder={filter.config?.placeholder || ''}
            className={`${inputClass} w-24`}
          />
        </div>
      );

    case 'slider':
      return (
        <SliderField
          filter={filter}
          value={value}
          onChange={onChange}
          labelClass={labelClass}
        />
      );

    default:
      return (
        <div>
          <label className={labelClass}>{filter.label}</label>
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={filter.config?.placeholder || filter.label}
            className={inputClass}
          />
        </div>
      );
  }
}

/**
 * Range slider with current value display.
 */
function SliderField({ filter, value, onChange, labelClass }) {
  const cfg = filter.config || {};
  const min = cfg.min ?? 0;
  const max = cfg.max ?? 100;
  const step = cfg.step ?? 1;
  const current = value === '' || value === undefined ? '' : Number(value);

  return (
    <div className="min-w-[160px]">
      <label className={labelClass}>
        {filter.label}
        {current !== '' && (
          <span className="ml-1 text-blue-600 font-semibold">
            {current}
          </span>
        )}
      </label>
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-gray-400 shrink-0">{min}</span>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={current === '' ? min : current}
          onChange={(e) => onChange(e.target.value)}
          className="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
        />
        <span className="text-[10px] text-gray-400 shrink-0">{max}</span>
      </div>
    </div>
  );
}

/**
 * Select filter with server-side search.
 *
 * Loads initial options on mount, then fetches filtered
 * results as the user types in the search box.
 */
function SearchableSelect({
  filter,
  widgetId,
  value,
  onChange,
  labelClass,
  inputClass,
}) {
  const [options, setOptions] = useState(filter.options || []);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const wrapperRef = useRef(null);
  const debounceRef = useRef(null);

  // Fetch options from the server
  const fetchOptions = useCallback(
    async (term = '') => {
      if (!widgetId) return;
      setLoading(true);
      try {
        const res = await getFilterOptions(
          widgetId,
          filter.id,
          { search: term || undefined, limit: 50 },
        );
        setOptions(res.data);
      } catch {
        // Fall back to static options on error
        setOptions(filter.options || []);
      } finally {
        setLoading(false);
      }
    },
    [widgetId, filter.id, filter.options],
  );

  // Load initial options on mount
  useEffect(() => {
    fetchOptions();
  }, [fetchOptions]);

  // Debounced search
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchOptions(search);
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [search, fetchOptions]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClick = (e) => {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(e.target)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () =>
      document.removeEventListener('mousedown', handleClick);
  }, []);

  const selectedLabel =
    options.find((o) => o.value === value)?.label || value;

  return (
    <div ref={wrapperRef} className="relative">
      <label className={labelClass}>{filter.label}</label>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`${inputClass} min-w-[140px] text-left flex items-center justify-between gap-2`}
      >
        <span className={value ? '' : 'text-gray-400'}>
          {value ? selectedLabel : 'All'}
        </span>
        <svg
          className="h-3 w-3 text-gray-400 shrink-0"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10
             11.168l3.71-3.938a.75.75 0 111.08
             1.04l-4.25 4.5a.75.75 0 01-1.08
             0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full min-w-[200px] bg-white border border-gray-200 rounded-md shadow-lg">
          <div className="p-1.5">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search..."
              className="w-full rounded border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              autoFocus
            />
          </div>
          <ul className="max-h-48 overflow-y-auto py-1">
            <li>
              <button
                type="button"
                onClick={() => {
                  onChange('');
                  setOpen(false);
                  setSearch('');
                }}
                className={`w-full text-left px-3 py-1.5 text-sm hover:bg-blue-50 ${
                  !value ? 'font-medium text-blue-600' : 'text-gray-700'
                }`}
              >
                All
              </button>
            </li>
            {loading && (
              <li className="px-3 py-1.5 text-xs text-gray-400">
                Loading...
              </li>
            )}
            {!loading && options.length === 0 && (
              <li className="px-3 py-1.5 text-xs text-gray-400">
                No results
              </li>
            )}
            {options.map((opt) => (
              <li key={opt.value}>
                <button
                  type="button"
                  onClick={() => {
                    onChange(opt.value);
                    setOpen(false);
                    setSearch('');
                  }}
                  className={`w-full text-left px-3 py-1.5 text-sm hover:bg-blue-50 ${
                    value === opt.value
                      ? 'font-medium text-blue-600'
                      : 'text-gray-700'
                  }`}
                >
                  {opt.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
