import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Overview from './pages/Overview'
import Documents from './pages/Documents'
import DocumentDetail from './pages/DocumentDetail'
import Runs from './pages/Runs'
import RunDetail from './pages/RunDetail'
import Analytics from './pages/Analytics'
import Export from './pages/Export'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="documents" element={<Documents />} />
        <Route path="documents/:id" element={<DocumentDetail />} />
        <Route path="runs" element={<Runs />} />
        <Route path="runs/:runId" element={<RunDetail />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="export" element={<Export />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
