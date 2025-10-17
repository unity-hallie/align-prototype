import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '../store'

export default function ReflectionPage() {
  const navigate = useNavigate()
  const { sessionId } = useAppStore()
  const [promptData, setPromptData] = useState(null)
  const [response, setResponse] = useState('')

  useEffect(() => {
    if (!sessionId) {
      navigate('/')
      return
    }
    loadCurrentPrompt()
  }, [sessionId])

  const loadCurrentPrompt = async () => {
    const res = await fetch(`/api/reflection/current-prompt?session_id=${sessionId}`)
    const data = await res.json()
    if (data.status === 'complete') {
      navigate('/summary')
    } else {
      setPromptData(data)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    await fetch('/api/reflection/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, response })
    })
    setResponse('')
    loadCurrentPrompt()
  }

  if (!promptData) return <div>Loading...</div>

  return (
    <div className="card">
      <h2>Phase {promptData.phase_number} of {promptData.total_phases}</h2>
      <div className="alert alert--info">
        <strong>{promptData.current_prompt?.phase}</strong>
        <p>{promptData.current_prompt?.prompt}</p>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Your Response:</label>
          <textarea
            value={response}
            onChange={(e) => setResponse(e.target.value)}
            required
            rows={8}
          />
        </div>
        <button type="submit" className="btn btn--primary">Submit Response</button>
      </form>
    </div>
  )
}