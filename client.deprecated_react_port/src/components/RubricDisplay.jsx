export default function RubricDisplay({ edit, assignment, updateAssignmentField }) {
  const rubric = assignment?.rubric || []

  const handleAddCriterion = () => {
    const newRubric = [...rubric, { id: `crit_${rubric.length + 1}`, description: '' }]
    updateAssignmentField('rubric', newRubric)
  }

  const handleUpdateCriterion = (index, value) => {
    const newRubric = [...rubric]
    newRubric[index].description = value
    updateAssignmentField('rubric', newRubric)
  }

  const handleRemoveCriterion = (index) => {
    const newRubric = rubric.filter((_, i) => i !== index)
    updateAssignmentField('rubric', newRubric)
  }

  return (
    <div className="rubric-display">
      <h3>Rubric Criteria</h3>
      {rubric.length === 0 && !edit ? (
        <em>No rubric criteria yet</em>
      ) : (
        <ul className="rubric-list">
          {rubric.map((criterion, index) => (
            <li key={criterion.id || index} className="rubric-item">
              {edit ? (
                <div className="rubric-item-edit">
                  <input
                    type="text"
                    value={criterion.description}
                    onChange={(e) => handleUpdateCriterion(index, e.target.value)}
                    placeholder="Criterion description..."
                  />
                  <button
                    onClick={() => handleRemoveCriterion(index)}
                    className="btn btn--secondary"
                  >
                    Remove
                  </button>
                </div>
              ) : (
                <span>{criterion.description}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {edit && (
        <button onClick={handleAddCriterion} className="btn btn--secondary">
          + Add Criterion
        </button>
      )}
    </div>
  )
}