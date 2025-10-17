import { useState, useEffect } from 'react'

export default function PromptHistoryLoader({ currentAssignment, setCurrentAssignment }) {
  const [examples, setExamples] = useState([])

  useEffect(() => {
    loadExamples()
  }, [])

  const loadExamples = async () => {
    try {
      const res = await fetch('/design/examples')
      const data = await res.json()
      setExamples(data.examples || [])
    } catch (error) {
      console.error('Failed to load examples:', error)
    }
  }

  const loadExample = async (slug) => {
    try {
      const res = await fetch(`/design/example/${slug}`)
      const data = await res.json()
      setCurrentAssignment({
        title: data.title || '',
        instructions: data.assignment_instructions || '',
        outcomes: data.outcomes || [],
        rubric: data.rubric || [],
        phases: data.phases || [],
        constraints: data.constraints || {}
      })
    } catch (error) {
      console.error('Failed to load example:', error)
    }
  }

  return (
    <details className="prompt-history">
      <summary>Load Template / Example</summary>
      <div style={{ marginTop: '1rem' }}>
        {examples.length === 0 ? (
          <p>No templates found</p>
        ) : (
          <ul>
            {examples.map(ex => (
              <li key={ex.slug}>
                <button
                  onClick={() => loadExample(ex.slug)}
                  className="btn btn--secondary"
                >
                  {ex.title} ({ex.source}, {ex.phases_count} phases)
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  )
}