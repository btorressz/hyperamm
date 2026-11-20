import { useDisplayStore } from '../stores/display';
import { experienceModes, type ExperienceMode } from '../utils/navigation';

export function ExperienceModeSwitch() {
  const mode = useDisplayStore(state => state.experienceMode);
  const setMode = useDisplayStore(state => state.setExperienceMode);
  return <label className="experienceMode">
    Workspace mode
    <select id="workspace-mode" value={mode} onChange={event => setMode(event.target.value as ExperienceMode)}>
      {experienceModes.map(item => <option key={item}>{item}</option>)}
    </select>
  </label>;
}
