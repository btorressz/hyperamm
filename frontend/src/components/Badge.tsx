import type { ReactNode } from 'react'
export function Badge({children,tone='neutral'}:{children:ReactNode,tone?:'good'|'bad'|'blue'|'warn'|'neutral'}){return <span className={`badge ${tone}`}>{children}</span>}
