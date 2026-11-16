import { Route, Routes } from 'react-router-dom'
import { ComparePage } from './pages/compare/ComparePage'
import { PerfPage } from './pages/dev/PerfPage'
import { LandingPage } from './pages/landing/LandingPage'
import { MapPage } from './pages/map/MapPage'
import { ProgressPage } from './pages/progress/ProgressPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/jobs/:jobId" element={<ProgressPage />} />
      <Route path="/jobs/:jobId/map" element={<MapPage />} />
      <Route path="/jobs/:jobId/divergences/:divergenceId" element={<ComparePage />} />
      {import.meta.env.DEV && <Route path="/dev/perf" element={<PerfPage />} />}
    </Routes>
  )
}
