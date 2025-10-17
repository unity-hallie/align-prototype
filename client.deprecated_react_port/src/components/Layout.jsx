import { Outlet, Link } from 'react-router-dom'
import './Layout.scss'

export default function Layout() {
  return (
    <div className="layout">
      <div className="layout__container">
        <header className="layout__header">
          <h1>🧠 ALIGN Reflection System</h1>
          <nav className="layout__nav">
            <Link to="/" className="btn btn--secondary">Home</Link>
            <Link to="/designer" className="btn btn--secondary">Designer</Link>
            <Link to="/settings" className="btn btn--secondary">Settings</Link>
            <Link to="/audit" className="btn btn--secondary">Audit</Link>
          </nav>
        </header>
        <main className="layout__main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}