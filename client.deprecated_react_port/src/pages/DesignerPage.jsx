import { useSelectedOrNewAssignment } from '../hooks/useSelectedOrNewAssignment'
import Button from '../components/Button'
import InstructionsDisplay from '../components/InstructionsDisplay'
import RubricDisplay from '../components/RubricDisplay'
import OutcomesDisplay from '../components/OutcomesDisplay'
import CanvasAssignmentLoader from '../components/CanvasAssignmentLoader'
import PromptHistoryLoader from '../components/PromptHistoryLoader'
import './DesignerPage.scss'

export default function DesignerPage() {
  const {
    currentAssignment,
    updateTempAssignmentField,
    saveTempAssignment,
    setCurrentAssignment
  } = useSelectedOrNewAssignment()

  return (
    <div className="designer-page">
      <div className="card">
        <h2>Prompt Designer</h2>

        <div className="designer-grid">
          <div className="designer-col">
            <InstructionsDisplay
              edit={true}
              assignment={currentAssignment}
              updateAssignmentField={updateTempAssignmentField}
            />
          </div>

          <div className="designer-col">
            <OutcomesDisplay
              edit={true}
              assignment={currentAssignment}
              updateAssignmentField={updateTempAssignmentField}
            />
          </div>

          <div className="designer-col">
            <RubricDisplay
              edit={true}
              assignment={currentAssignment}
              updateAssignmentField={updateTempAssignmentField}
            />
          </div>
        </div>

        <div className="designer-actions">
          <Button onClick={saveTempAssignment}>Save Assignment</Button>
        </div>

        <div className="designer-loaders">
          <CanvasAssignmentLoader />
          <PromptHistoryLoader
            currentAssignment={currentAssignment}
            setCurrentAssignment={setCurrentAssignment}
          />
        </div>
      </div>
    </div>
  )
}