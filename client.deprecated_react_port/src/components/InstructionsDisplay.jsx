export default function InstructionsDisplay({ edit, assignment, updateAssignmentField }) {
  const handleChange = (e) => {
    if (edit && updateAssignmentField) {
      updateAssignmentField('instructions', e.target.value)
    }
  }

  return (
    <div className="instructions-display">
      <h3>Assignment Instructions</h3>
      {edit ? (
        <textarea
          value={assignment?.instructions || ''}
          onChange={handleChange}
          placeholder="Paste assignment instructions here..."
          rows={8}
        />
      ) : (
        <div className="instructions-content">
          {assignment?.instructions || <em>No instructions yet</em>}
        </div>
      )}
    </div>
  )
}