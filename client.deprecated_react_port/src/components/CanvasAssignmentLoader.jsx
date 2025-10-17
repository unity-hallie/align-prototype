import { useState } from 'react'

export default function CanvasAssignmentLoader() {
  const [courses, setCourses] = useState([])
  const [selectedCourse, setSelectedCourse] = useState('')
  const [assignments, setAssignments] = useState([])

  const loadCourses = async () => {
    try {
      const res = await fetch('/canvas/courses')
      const data = await res.json()
      setCourses(data.courses || [])
    } catch (error) {
      console.error('Failed to load courses:', error)
    }
  }

  const loadAssignments = async (courseId) => {
    try {
      const res = await fetch(`/canvas/assignments/${courseId}`)
      const data = await res.json()
      setAssignments(data.assignments || [])
    } catch (error) {
      console.error('Failed to load assignments:', error)
    }
  }

  return (
    <details className="canvas-loader">
      <summary>Import from Canvas</summary>
      <div style={{ marginTop: '1rem' }}>
        <button onClick={loadCourses} className="btn btn--secondary">
          Load Courses
        </button>
        {courses.length > 0 && (
          <select
            value={selectedCourse}
            onChange={(e) => {
              setSelectedCourse(e.target.value)
              if (e.target.value) loadAssignments(e.target.value)
            }}
          >
            <option value="">Select a course...</option>
            {courses.map(c => (
              <option key={c.id} value={c.id}>
                {c.course_code} - {c.name}
              </option>
            ))}
          </select>
        )}
        {assignments.length > 0 && (
          <ul>
            {assignments.map(a => (
              <li key={a.id}>{a.name}</li>
            ))}
          </ul>
        )}
      </div>
    </details>
  )
}