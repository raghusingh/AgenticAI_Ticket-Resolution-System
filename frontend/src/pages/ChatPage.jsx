import { useContext, useEffect, useRef, useState } from 'react'
import { ThemeContext } from '../context/ThemeContext'
import { searchTickets, closeTicket, getClosedTickets } from '../api/chatApi'
import RagSetupPage from "./RagSetupPage";
import '../App.css'

import { useNavigate } from 'react-router-dom'

function Header({ user, onLogout, view, setView }) {
  
  const { theme, toggleTheme } = useContext(ThemeContext)

  return (
    <div className="app-header">
      <div className="header-left">
        <div className="app-title">Ticket Search Bot</div>
      </div>

      <div className="header-right">
        <span className="user-chip">User: {user.username}</span>
        <span className="session-chip">Session: {user.session_id}</span>

        <button
          className="admin-btn"
          onClick={() => setView(view === "chat" ? "rag" : "chat")}
        >
          {view === "chat" ? "⚙ RAG Setup" : "💬 Back to Chat"}
        </button>

        <button className="theme-btn" onClick={toggleTheme}>
          {theme === 'light' ? '🌙 Dark' : '☀️ Light'}
        </button>

        <button className="logout-btn" onClick={onLogout}>
          Logout
        </button>
      </div>
    </div>
  )
}

function Sidebar({ onNewChat, chats, activeChatId, onSelectChat }) {
  return (
    <div className="sidebar">
      <button className="new-chat-btn" onClick={onNewChat}>
        + New Chat
      </button>

      <div className="chat-list">
        {chats.map((chat) => (
          <div
            key={chat.id}
            className={`chat-item ${activeChatId === chat.id ? 'active' : ''}`}
            onClick={() => onSelectChat(chat.id)}
          >
            {chat.title}
          </div>
        ))}
      </div>
    </div>
  )
}

function ProgressBar({ loading }) {
  if (!loading) return null

  return (
    <div className="progress-wrap">
      <div className="progress-bar"></div>
      <div className="progress-text">Searching...</div>
    </div>
  )
}

function CloseTicketForm({ onConfirm, onCancel, closing }) {
  const [ticketId, setTicketId] = useState('')
  const [resolution, setResolution] = useState('')
  const [closedTickets, setClosedTickets] = useState([])
  const [loadingClosed, setLoadingClosed] = useState(true)
  const [selectedClosed, setSelectedClosed] = useState('')

  useEffect(() => {
    getClosedTickets('client-a')
      .then(data => setClosedTickets(data.tickets || []))
      .catch(() => setClosedTickets([]))
      .finally(() => setLoadingClosed(false))
  }, [])

  const handleDropdownChange = (e) => {
    const val = e.target.value
    setSelectedClosed(val)
    if (val) {
      const found = closedTickets.find(t => t.ticket_id === val)
      setResolution(found?.resolution || found?.reason || '')
    } else {
      setResolution('')
    }
  }

  const canSubmit = ticketId.trim() && resolution && !closing

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
    }}>
      <div style={{
        background: '#fff', borderRadius: '10px', padding: '28px 32px',
        width: '500px', boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
      }}>
        <h3 style={{ margin: '0 0 6px', color: '#1e293b', fontSize: '17px' }}>
          🔒 Close Open Ticket
        </h3>
        <p style={{ margin: '0 0 20px', color: '#64748b', fontSize: '13px' }}>
          Enter the open ticket ID and select a resolution from a previously closed ticket.
        </p>

        {/* Open Ticket ID */}
        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '6px' }}>
            Open Ticket ID <span style={{ color: '#ef4444' }}>*</span>
          </label>
          <input
            type="text"
            placeholder="e.g. SCRUM-25"
            value={ticketId}
            onChange={(e) => setTicketId(e.target.value)}
            autoFocus
            style={{
              width: '100%', padding: '9px 12px', borderRadius: '6px',
              border: '1.5px solid #cbd5e1', fontSize: '14px',
              outline: 'none', boxSizing: 'border-box', color: '#1e293b',
            }}
            onKeyDown={(e) => { if (e.key === 'Escape') onCancel() }}
          />
        </div>

        {/* Closed Ticket Dropdown */}
        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '6px' }}>
            Select Resolution from Closed Ticket <span style={{ color: '#ef4444' }}>*</span>
          </label>
          {loadingClosed ? (
            <div style={{ fontSize: '13px', color: '#94a3b8' }}>Loading closed tickets...</div>
          ) : (
            <select
              value={selectedClosed}
              onChange={handleDropdownChange}
              style={{
                width: '100%', padding: '9px 12px', borderRadius: '6px',
                border: '1.5px solid #cbd5e1', fontSize: '13px',
                color: '#1e293b', background: '#fff', boxSizing: 'border-box', outline: 'none',
              }}
            >
              <option value="">— Select a closed ticket —</option>
              {closedTickets.length === 0 && <option disabled>No closed tickets found</option>}
              {closedTickets.map((t) => (
                <option key={t.ticket_id} value={t.ticket_id}>
                  {t.ticket_id} — {(t.resolution || t.reason || 'No resolution').slice(0, 60)}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Resolution — read only, auto-filled from dropdown */}
        <div style={{ marginBottom: '22px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '6px' }}>
            Resolution{' '}
            <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 400 }}>(auto-filled from selected ticket)</span>
          </label>
          <div style={{
            padding: '9px 12px', borderRadius: '6px',
            border: '1.5px solid #e2e8f0', background: '#f8fafc',
            fontSize: '13px', color: resolution ? '#475569' : '#94a3b8',
            minHeight: '40px', lineHeight: '1.5',
          }}>
            {resolution || 'Select a closed ticket above'}
          </div>
        </div>

        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
          <button onClick={onCancel} disabled={closing}
            style={{ padding: '8px 20px', borderRadius: '6px', border: '1px solid #cbd5e1', background: '#fff', color: '#475569', cursor: 'pointer', fontSize: '14px', fontWeight: '500' }}>
            Cancel
          </button>
          <button
            onClick={() => canSubmit && onConfirm(ticketId.trim(), resolution)}
            disabled={!canSubmit}
            style={{
              padding: '8px 20px', borderRadius: '6px', border: 'none',
              background: canSubmit ? '#2563eb' : '#93c5fd',
              color: '#fff', cursor: canSubmit ? 'pointer' : 'not-allowed',
              fontSize: '14px', fontWeight: '600',
            }}>
            {closing ? 'Closing...' : 'Close Ticket'}
          </button>
        </div>
      </div>
    </div>
  )
}

function ResultsTable({ tickets }) {
  const [showForm, setShowForm] = useState(false)
  const [closing, setClosing] = useState(false)
  const [toast, setToast] = useState(null)

  if (!tickets?.length) return null

  const closedStatuses = new Set(['done', 'closed', 'resolved', 'fixed'])

  const showToast = (msg, success = true) => {
    setToast({ msg, success })
    setTimeout(() => setToast(null), 3500)
  }

  const handleCloseConfirm = async (openTicketId, resolution) => {
    setClosing(true)
    try {
      await closeTicket({
        tenant_id: 'client-a',
        ticket_id: openTicketId,
        reason: resolution,
      })
      showToast(`✅ Ticket ${openTicketId} closed successfully.`, true)
    } catch (err) {
      showToast(`❌ Failed: ${err?.response?.data?.detail || err.message}`, false)
    } finally {
      setClosing(false)
      setShowForm(false)
    }
  }

  return (
    <div className="results-wrapper">
      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', top: '20px', right: '20px', zIndex: 2000,
          background: toast.success ? '#dcfce7' : '#fee2e2',
          border: `1px solid ${toast.success ? '#86efac' : '#fca5a5'}`,
          color: toast.success ? '#166534' : '#991b1b',
          padding: '12px 20px', borderRadius: '8px',
          fontWeight: '500', fontSize: '14px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
        }}>
          {toast.msg}
        </div>
      )}

      {/* Close form dialog */}
      {showForm && (
        <CloseTicketForm
          onConfirm={handleCloseConfirm}
          onCancel={() => setShowForm(false)}
          closing={closing}
        />
      )}

      <div className="results-title">Relevant Tickets</div>
      <div className="results-table-scroll">
        <table className="results-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Ticket Id</th>
              <th>Description</th>
              <th>Resolution</th>
              <th>Root Cause</th>
              <th>Type</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Confidence</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((t, idx) => (
              <tr key={`${t.ticket_id || 'row'}-${idx}`}>
                <td>{t.source || '-'}</td>
                <td>{t.ticket_id || '-'}</td>
                <td>{t.ticket_description || '-'}</td>
                <td>{t.resolution || '-'}</td>
                <td>{t.root_cause || '-'}</td>
                <td>{t.issue_type || '-'}</td>
                <td>{t.status || '-'}</td>
                <td>{t.priority || '-'}</td>
                <td>
                  {typeof t.confidence_score === 'number'
                    ? t.confidence_score.toFixed(3)
                    : '-'}
                </td>
                <td>
                  {!closedStatuses.has((t.status || '').toLowerCase()) ? (
                    <button
                      onClick={() => setShowForm(true)}
                      style={{
                        padding: '4px 12px', borderRadius: '5px',
                        border: '1px solid #2563eb', background: '#eff6ff',
                        color: '#2563eb', cursor: 'pointer',
                        fontSize: '12px', fontWeight: '600',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      🔒 Close
                    </button>
                  ) : (
                    <span style={{ fontSize: '12px', color: '#64748b', fontStyle: 'italic' }}>
                      Closed
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ChatWindow({ messages, loading }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  return (
    <div className="chat-window">
      {messages.map((msg) => (
        <div key={msg.id} className={`message-row ${msg.role}`}>
          <div className="message-bubble">
            {msg.type === 'tickets' ? (
              <ResultsTable tickets={msg.tickets} />
            ) : (
              <div>{msg.content}</div>
            )}
          </div>
        </div>
      ))}

      <ProgressBar loading={loading} />
      <div ref={bottomRef}></div>
    </div>
  )
}

function SearchBox({ value, setValue, onSearch, loading }) {
  return (
    <div className="search-box">
      <input
        type="text"
        placeholder="Search tickets..."
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && value.trim() && !loading) {
            onSearch()
          }
        }}
      />
      <button onClick={onSearch} disabled={!value.trim() || loading}>
        {loading ? 'Searching...' : 'Search'}
      </button>
    </div>
  )
}

function createEmptyChat(index = 1) {
  return {
    id: Date.now() + Math.random(),
    title: `New Chat ${index}`,
    messages: [],
  }
}

export default function ChatPage({ user, onLogout }) {
    const [query, setQuery] = useState('')
    const [loading, setLoading] = useState(false)
    const [chats, setChats] = useState([createEmptyChat(1)])
    const [activeChatId, setActiveChatId] = useState(null)
    const [view, setView] = useState("chat")

  useEffect(() => {
    if (chats.length && !activeChatId) {
      setActiveChatId(chats[0].id)
    }
  }, [chats, activeChatId])

  const activeChat = chats.find((c) => c.id === activeChatId)

  const updateActiveChatMessages = (updater) => {
    setChats((prev) =>
      prev.map((chat) =>
        chat.id === activeChatId
          ? {
              ...chat,
              messages:
                typeof updater === 'function' ? updater(chat.messages) : updater,
            }
          : chat
      )
    )
  }

  const handleNewChat = () => {
    const newChat = createEmptyChat(chats.length + 1)
    setChats((prev) => [newChat, ...prev])
    setActiveChatId(newChat.id)
    setQuery('')
  }

  const handleSearch = async () => {
    if (!query.trim() || !activeChatId) return

    const userQuestion = query.trim()

    updateActiveChatMessages((prev) => [
      ...prev,
      {
        id: Date.now(),
        role: 'user',
        type: 'text',
        content: userQuestion,
      },
    ])

    setQuery('')
    setLoading(true)

    try {
      const data = await searchTickets({
        tenant_id: 'client-a',
        question: userQuestion,
        generate_answer: false,
      })

      const ticketRows =
        data?.tickets?.length > 0
          ? data.tickets
          : Array.isArray(data?.sources)
            ? data.sources
            : []

      updateActiveChatMessages((prev) => {
        const next = [...prev]

        if (ticketRows.length) {
          next.push({
            id: Date.now() + 1,
            role: 'assistant',
            type: 'tickets',
            tickets: ticketRows,
          })
        }

        if (data?.answer) {
          next.push({
            id: Date.now() + 2,
            role: 'assistant',
            type: 'text',
            content: data.answer,
          })
        }

        if (!ticketRows.length && !data?.answer) {
          next.push({
            id: Date.now() + 3,
            role: 'assistant',
            type: 'text',
            content: 'No results found.',
          })
        }

        return next
      })
    } catch (err) {
      updateActiveChatMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 4,
          role: 'assistant',
          type: 'text',
          content: err?.response?.data?.detail || 'Search failed.',
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app-shell">
      <Sidebar
        onNewChat={handleNewChat}
        chats={chats}
        activeChatId={activeChatId}
        onSelectChat={setActiveChatId}
      />

      <div className="main-panel">
      <Header user={user} onLogout={onLogout} view={view} setView={setView} />
      {view === "chat" ? (
        <>
          <ChatWindow messages={activeChat?.messages || []} loading={loading} />
          <SearchBox
            value={query}
            setValue={setQuery}
            onSearch={handleSearch}
            loading={loading}
          />
        </>
      ) : (
        <RagSetupPage tenantId="client-a" />
      )}
      </div>
    </div>
  )
}