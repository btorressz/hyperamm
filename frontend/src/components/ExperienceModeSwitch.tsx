import { useDisplayStore } from '../stores/display';
import { experienceModes } from '../utils/navigation';

export function ExperienceModeSwitch() {
  const mode = useDisplayStore(state => state.experienceMode);
  const setMode = useDisplayStore(state => state.setExperienceMode);
  return <div className="experienceMode" role="group" aria-label="Workspace mode">
    {experienceModes.map(item => <button key={item} type="button" id={`workspace-mode-${item.toLowerCase()}`}
      aria-pressed={mode === item} onClick={() => setMode(item)}>{item}</button>)}
  </div>;
}
