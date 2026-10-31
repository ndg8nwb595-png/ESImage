import { PlusOutlined } from '@ant-design/icons'
import { Button, Empty } from 'antd'

import { useWorkspaceStore } from '../store'

/** 左栏：会话列表。 */
export default function SessionList() {
  const sessions = useWorkspaceStore((s) => s.sessions)
  const currentSessionId = useWorkspaceStore((s) => s.currentSessionId)
  const openSession = useWorkspaceStore((s) => s.openSession)
  const newSession = useWorkspaceStore((s) => s.newSession)

  return (
    <aside className="ws-col ws-session">
      <div className="ws-session-header">
        <Button type="primary" block icon={<PlusOutlined />} onClick={newSession}>
          新建会话
        </Button>
      </div>
      <div className="ws-session-list">
        {sessions.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无会话"
            style={{ marginTop: 40 }}
          />
        ) : (
          sessions.map((s) => (
            <div
              key={s.session_id}
              className={`ws-session-item ${s.session_id === currentSessionId ? 'active' : ''}`}
              onClick={() => openSession(s.session_id)}
            >
              <div className="ws-session-title">{s.title}</div>
              <div className="ws-session-preview">{s.last_message_preview ?? '暂无消息'}</div>
            </div>
          ))
        )}
      </div>
    </aside>
  )
}
