import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import HomePage from './pages/HomePage'
import ReflectionPage from './pages/ReflectionPage'
import SummaryPage from './pages/SummaryPage'
import DesignerPage from './pages/DesignerPage'
import SettingsPage from './pages/SettingsPage'
import AuditPage from './pages/AuditPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="reflection" element={<ReflectionPage />} />
        <Route path="summary" element={<SummaryPage />} />
        <Route path="designer" element={<DesignerPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="audit" element={<AuditPage />} />
      </Route>
    </Routes>
  )
}

export default App