import { useEffect } from 'react'

import ChatPanel from '../components/ChatPanel'
import ControlPanel from '../components/ControlPanel'
import ResultPanel from '../components/ResultPanel'
import SessionList from '../components/SessionList'
import { useWorkspaceStore } from '../store'
import '../workspace.css'

/** 创作工作台：三栏布局（会话列表 | 聊天 | 参数/上传/结果）。 */
export default function WorkspacePage() {
  const loadSessions = useWorkspaceStore((s) => s.loadSessions)
  const restoreUploads = useWorkspaceStore((s) => s.restoreUploads)

  useEffect(() => {
    void loadSessions()
    void restoreUploads()
  }, [loadSessions, restoreUploads])

  return (
    <div className="workspace">
      <SessionList />
      <ChatPanel />
      <div className="ws-col ws-right">
        <ControlPanel />
        <ResultPanel />
      </div>
    </div>
  )
}
