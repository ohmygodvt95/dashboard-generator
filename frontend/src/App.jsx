import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import WidgetListPage from './pages/WidgetListPage';
import WidgetEditorPage from './pages/WidgetEditorPage';
import WidgetEmbedPage from './pages/WidgetEmbedPage';
import Layout from './components/Layout';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/widgets" replace />} />
        <Route element={<Layout />}>
          <Route path="/widgets" element={<WidgetListPage />} />
          <Route path="/widgets/:id" element={<WidgetEditorPage />} />
        </Route>
        <Route path="/widgets/:id/embed" element={<WidgetEmbedPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
