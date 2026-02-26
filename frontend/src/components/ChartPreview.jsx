import { useEffect, useRef } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  RadialLinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Filler,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import {
  Bar, Line, Pie, Doughnut, Scatter,
  Radar, PolarArea, Bubble,
} from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  RadialLinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Filler,
  Title,
  Tooltip,
  Legend
);

const CHART_COMPONENTS = {
  bar: Bar,
  line: Line,
  pie: Pie,
  doughnut: Doughnut,
  scatter: Scatter,
  area: Line,
  radar: Radar,
  polarArea: PolarArea,
  bubble: Bubble,
};

/** Chart types that display slices rather than axes. */
const PIE_TYPES = new Set(['pie', 'doughnut', 'polarArea']);

/** Chart types that use radial scales instead of linear. */
const RADIAL_TYPES = new Set(['radar', 'polarArea']);

/** Chart types that need {x, y} point objects. */
const POINT_TYPES = new Set(['scatter', 'bubble']);

const DEFAULT_COLORS = [
  '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
  '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1',
];

/**
 * Build Chart.js data object from raw query rows.
 *
 * Supports:
 * - Single dataset:  y_axis = "column_name"
 * - Multi-dataset:   y_axis = ["col1", "col2", ...]
 * - Scatter:         {x, y} point objects
 * - Bubble:          {x, y, r} point objects (needs r_axis)
 */
function buildChartData(data, chartConfig, chartType) {
  if (!data || !data.length || !chartConfig) {
    return { labels: [], datasets: [] };
  }

  const colors = chartConfig.colors?.length
    ? chartConfig.colors
    : DEFAULT_COLORS;
  const isPieType = PIE_TYPES.has(chartType);

  // --- Bubble chart: {x, y, r} points -----------------------
  if (chartType === 'bubble') {
    const rAxis = chartConfig.r_axis;
    const points = data.map((row) => ({
      x: Number(row[chartConfig.x_axis]),
      y: Number(row[chartConfig.y_axis]),
      r: rAxis ? Number(row[rAxis]) : 5,
    }));
    return {
      labels: [],
      datasets: [{
        label: chartConfig.y_axis,
        data: points,
        backgroundColor: colors[0] + '80',
        borderColor: colors[0],
        borderWidth: 1,
      }],
    };
  }

  // --- Scatter chart: {x, y} points --------------------------
  if (chartType === 'scatter') {
    const points = data.map((row) => ({
      x: Number(row[chartConfig.x_axis]),
      y: Number(row[chartConfig.y_axis]),
    }));
    return {
      labels: [],
      datasets: [{
        label: chartConfig.y_axis,
        data: points,
        backgroundColor: colors[0],
        borderColor: colors[0],
        borderWidth: 1,
      }],
    };
  }

  const labels = data.map((row) => row[chartConfig.x_axis]);

  // --- Multi-dataset: y_axis is an array ---------------------
  const yAxes = Array.isArray(chartConfig.y_axis)
    ? chartConfig.y_axis
    : [chartConfig.y_axis];

  const datasets = yAxes.map((col, idx) => {
    const values = data.map((row) => row[col]);
    const color = colors[idx % colors.length];

    return {
      label: col,
      data: values,
      backgroundColor: isPieType
        ? colors.slice(0, labels.length)
        : color,
      borderColor: isPieType
        ? colors.slice(0, labels.length)
        : color,
      borderWidth: isPieType ? 1 : 2,
      fill: chartType === 'area',
      tension: 0.3,
    };
  });

  return { labels, datasets };
}

/**
 * Build Chart.js options, including stacked axes and
 * radial-scale awareness.
 */
function buildChartOptions(chartConfig, chartType) {
  const isRadial = RADIAL_TYPES.has(chartType);
  const stacked = chartConfig?.stacked ?? false;

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: chartConfig?.legend?.display ?? true,
        position: chartConfig?.legend?.position || 'top',
      },
      title: {
        display: chartConfig?.title?.display ?? false,
        text: chartConfig?.title?.text || '',
      },
    },
  };

  // Radial charts (radar, polarArea) have no cartesian axes.
  if (!isRadial && !PIE_TYPES.has(chartType)) {
    options.indexAxis = chartConfig?.indexAxis || 'x';
    options.scales = {
      x: { stacked },
      y: { stacked },
    };
  }

  return options;
}

export default function ChartPreview({ chartType, chartConfig, data }) {
  const ChartComponent = CHART_COMPONENTS[chartType] || Bar;

  if (!data || !data.length) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        <div className="text-center">
          <p className="text-4xl mb-2">📊</p>
          <p>No data to display</p>
          <p className="text-xs mt-1">Chat with AI to generate a chart</p>
        </div>
      </div>
    );
  }

  const chartData = buildChartData(data, chartConfig, chartType);
  const options = buildChartOptions(chartConfig, chartType);

  return (
    <div className="w-full h-full p-4">
      <ChartComponent data={chartData} options={options} />
    </div>
  );
}
