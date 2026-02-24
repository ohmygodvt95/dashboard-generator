import { useEffect, useRef } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Filler,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { Bar, Line, Pie, Doughnut, Scatter } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
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
};

const DEFAULT_COLORS = [
  '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
  '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1',
];

function buildChartData(data, chartConfig, chartType) {
  if (!data || !data.length || !chartConfig) {
    return { labels: [], datasets: [] };
  }

  const labels = data.map((row) => row[chartConfig.x_axis]);
  const values = data.map((row) => row[chartConfig.y_axis]);
  const colors = chartConfig.colors?.length ? chartConfig.colors : DEFAULT_COLORS;

  const isPieType = chartType === 'pie' || chartType === 'doughnut';

  return {
    labels,
    datasets: [
      {
        label: chartConfig.y_axis,
        data: values,
        backgroundColor: isPieType
          ? colors.slice(0, labels.length)
          : colors[0],
        borderColor: isPieType
          ? colors.slice(0, labels.length)
          : colors[0],
        borderWidth: isPieType ? 1 : 2,
        fill: chartType === 'area',
        tension: 0.3,
      },
    ],
  };
}

function buildChartOptions(chartConfig) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: chartConfig?.indexAxis || 'x',
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
  const options = buildChartOptions(chartConfig);

  return (
    <div className="w-full h-full p-4">
      <ChartComponent data={chartData} options={options} />
    </div>
  );
}
