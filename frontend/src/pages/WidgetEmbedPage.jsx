import { useState, useEffect, useCallback } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import ChartPreview from '../components/ChartPreview';
import FilterBar from '../components/FilterBar';
import { getWidget, getWidgetData } from '../services/api';

export default function WidgetEmbedPage() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const [widget, setWidget] = useState(null);
  const [chartData, setChartData] = useState([]);
  const [filterValues, setFilterValues] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Initialize filter values from URL params
  useEffect(() => {
    const initialFilters = {};
    searchParams.forEach((value, key) => {
      initialFilters[key] = value;
    });
    setFilterValues(initialFilters);
  }, [searchParams]);

  const fetchWidget = useCallback(async () => {
    try {
      const res = await getWidget(id);
      setWidget(res.data);
    } catch (err) {
      setError('Widget not found');
      console.error('Failed to fetch widget:', err);
    }
  }, [id]);

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
      await fetchWidget();
      setLoading(false);
    };
    init();
  }, [fetchWidget]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-white">
        <p className="text-gray-400 text-sm">Loading...</p>
      </div>
    );
  }

  if (error || !widget) {
    return (
      <div className="flex items-center justify-center h-screen bg-white">
        <p className="text-gray-500 text-sm">{error || 'Widget not found'}</p>
      </div>
    );
  }

  return (
    <div
      className="h-screen w-screen flex flex-col bg-white"
      style={{
        padding: widget.layout_config?.padding || '16px',
        backgroundColor: widget.layout_config?.background_color || '#ffffff',
      }}
    >
      {widget.filters?.length > 0 && (
        <div className="mb-3">
          <FilterBar
            filters={widget.filters}
            values={filterValues}
            onChange={setFilterValues}
            widgetId={id}
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
  );
}
