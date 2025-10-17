export default function OutcomesDisplay({ edit, assignment, updateAssignmentField }) {
  const outcomes = assignment?.outcomes || []

  const handleOutcomesChange = (e) => {
    // Parse newline-separated list
    const newOutcomes = e.target.value
      .split('\n')
      .map(o => o.trim())
      .filter(Boolean)
    updateAssignmentField('outcomes', newOutcomes)
  }

  return (
    <div className="outcomes-display">
      <h3>Learning Outcomes</h3>
      {edit ? (
        <textarea
          value={outcomes.join('\n')}
          onChange={handleOutcomesChange}
          placeholder="One outcome per line..."
          rows={6}
        />
      ) : (
        <ul>
          {outcomes.length === 0 ? (
            <em>No outcomes yet</em>
          ) : (
            outcomes.map((outcome, i) => <li key={i}>{outcome}</li>)
          )}
        </ul>
      )}
    </div>
  )
}