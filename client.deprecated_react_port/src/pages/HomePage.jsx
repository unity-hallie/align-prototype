import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '../store'
import './HomePage.scss'

export default function HomePage() {
  const navigate = useNavigate()
  const { keyPresent, llmEnabled } = useAppStore()
  const [formData, setFormData] = useState({
    studentId: 'test_student',
    assignmentType: 'search_comparison',
    assignmentContext: ''
  })

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      const response = await fetch('/api/reflection/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      })
      const data = await response.json()
      if (data.session_id) {
        navigate('/reflection')
      }
    } catch (error) {
      console.error('Failed to start session:', error)
    }
  }

  return (
    <div className="home-page">
      <div className="card">
        {!keyPresent || !llmEnabled ? (
          <div className="alert alert--error">
            <strong>LLM key required</strong> — AI features are disabled.
            <a href="/settings" className="btn btn--primary" style={{marginTop: '1rem'}}>
              Open Settings
            </a>
          </div>
        ) : null}

        <h2>Start Reflection Session</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="studentId">Student ID:</label>
            <input
              type="text"
              id="studentId"
              value={formData.studentId}
              onChange={(e) => setFormData({...formData, studentId: e.target.value})}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="assignmentType">Assignment Type:</label>
            <select
              id="assignmentType"
              value={formData.assignmentType}
              onChange={(e) => setFormData({...formData, assignmentType: e.target.value})}
            >
              <option value="search_comparison">Search Comparison (DB vs Google)</option>
              <option value="generic">Generic Assignment</option>
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="assignmentContext">Assignment Context (optional):</label>
            <textarea
              id="assignmentContext"
              value={formData.assignmentContext}
              onChange={(e) => setFormData({...formData, assignmentContext: e.target.value})}
              placeholder="Describe the assignment or paste rubric details..."
            />
          </div>

          <button type="submit" className="btn btn--primary" disabled={!keyPresent || !llmEnabled}>
            Start Reflection Session
          </button>
        </form>
      </div>
    </div>
  )
}