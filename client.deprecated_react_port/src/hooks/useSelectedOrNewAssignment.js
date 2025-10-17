import { useState } from 'react'

/**
 * Hook for managing current assignment in Designer
 * Handles temp state for editing before save
 */
export function useSelectedOrNewAssignment() {
  const [currentAssignment, setCurrentAssignment] = useState({
    id: null,
    title: '',
    instructions: '',
    outcomes: [],
    rubric: [],
    phases: [],
    constraints: {}
  })

  const [tempChanges, setTempChanges] = useState({})

  const updateTempAssignmentField = (field, value) => {
    setTempChanges(prev => ({ ...prev, [field]: value }))
  }

  const saveTempAssignment = async () => {
    const updated = { ...currentAssignment, ...tempChanges }

    // TODO: Call API to save
    // const response = await fetch('/design/save', {
    //   method: 'POST',
    //   headers: { 'Content-Type': 'application/json' },
    //   body: JSON.stringify({ slug: updated.title, content: updated })
    // })

    setCurrentAssignment(updated)
    setTempChanges({})
    console.log('Saved assignment:', updated)
  }

  const getCurrentAssignment = () => ({
    ...currentAssignment,
    ...tempChanges
  })

  return {
    currentAssignment: getCurrentAssignment(),
    updateTempAssignmentField,
    saveTempAssignment,
    setCurrentAssignment
  }
}
