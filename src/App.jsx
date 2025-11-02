import { useState, useEffect } from 'react'
import './App.css'

/* ---------- LOGO ---------- */
function Logo() {
  // use image placed in public/sld.png
  return <img src="/sld.png" alt="SigmaBoy AI" className="logo-img" />;
}

/* ---------- MAIN APP ---------- */
function App() {
	const [chats, setChats] = useState({})
	const [currentChatId, setCurrentChatId] = useState(null)
	const [messages, setMessages] = useState([])
	const [inputMessage, setInputMessage] = useState('')
	const [isBotTyping, setIsBotTyping] = useState(false)

	// new: menu / delete confirm state
	const [menuOpenFor, setMenuOpenFor] = useState(null)
	const [confirmDeleteFor, setConfirmDeleteFor] = useState(null)
	const [menuPositions, setMenuPositions] = useState({})

	/* ---------- STORAGE HELPERS ---------- */
	const loadChats = () => JSON.parse(localStorage.getItem('chats') || '{}')
	const saveChats = (data) => localStorage.setItem('chats', JSON.stringify(data))

	// close menus on outside click
	useEffect(() => {
		const onDocClick = () => setMenuOpenFor(null)
		document.addEventListener('click', onDocClick)
		return () => document.removeEventListener('click', onDocClick)
	}, [])

	/* ---------- LOAD SAVED CHATS ---------- */
	useEffect(() => {
		setChats(loadChats())
	}, [])

	/* ---------- CREATE NEW CHAT ---------- */
	const createNewChat = (titleText) => {
		const newChatId = Date.now().toString()
		const newChat = {
			id: newChatId,
			title: titleText?.substring(0, 30) || 'New Chat',
			messages: []
		}

		const updated = { ...chats, [newChatId]: newChat }
		setChats(updated)
		saveChats(updated)

		setCurrentChatId(newChatId)
		setMessages([])
		return newChatId
	}

	/* ---------- ADD & SAVE MESSAGE ---------- */
	const addMessage = (chatId, msg) => {
		setMessages((prev) => [...prev, msg])

		const saved = loadChats()
		const target = saved[chatId] || { id: chatId, title: 'Chat', messages: [] }
		target.messages = [...(target.messages || []), msg]
		if (!target.title || target.title === 'New Chat') {
			target.title = target.messages[0]?.text?.substring(0, 30) || 'Chat'
		}

		saved[chatId] = target
		saveChats(saved)
		setChats(saved)
	}

	/* ---------- SEND MESSAGE ---------- */
	const sendMessage = (e) => {
		e?.preventDefault()
		const text = inputMessage.trim()
		if (!text) return

		let chatId = currentChatId
		if (!chatId) {
			chatId = createNewChat(text)
			setMessages([])
		}

		const userMsg = { text, sender: 'user', timestamp: Date.now() }
		addMessage(chatId, userMsg)
		setInputMessage('')

		// Simulated bot reply
		setIsBotTyping(true)
		setTimeout(() => {
			const botMsg = {
				text: 'This is a simulated response.',
				sender: 'bot',
				timestamp: Date.now()
			}
			addMessage(chatId, botMsg)
			setIsBotTyping(false)
		}, 800)
	}

	/* ---------- HERO SUBMIT ---------- */
	const handleHeroSubmit = (e) => {
		e.preventDefault()
		const text = inputMessage.trim()
		if (!text) return
		const chatId = createNewChat(text)

		const userMsg = { text, sender: 'user', timestamp: Date.now() }
		addMessage(chatId, userMsg)
		setInputMessage('')

		setIsBotTyping(true)
		setTimeout(() => {
			const botMsg = { text: 'This is a simulated response.', sender: 'bot', timestamp: Date.now() }
			addMessage(chatId, botMsg)
			setIsBotTyping(false)
		}, 800)
	}

	/* ---------- LOAD CHAT ---------- */
	const loadChat = (chatId) => {
		setCurrentChatId(chatId)
		setMessages(chats[chatId]?.messages || [])
	}

	/* ---------- CLEAR ALL CHATS ---------- */
	const clearAll = () => {
		localStorage.removeItem('chats')
		setChats({})
		setMessages([])
		setCurrentChatId(null)
	}

	// toggle menu for a chat and compute popup position so it can be fixed on screen
	const toggleMenu = (chatId, btnEl) => {
		setMenuOpenFor((prev) => (prev === chatId ? null : chatId))
		if (btnEl && btnEl.getBoundingClientRect) {
			const rect = btnEl.getBoundingClientRect()
			const dropdownWidth = 140
			const left = Math.min(Math.max(8, rect.right - dropdownWidth), window.innerWidth - dropdownWidth - 8)
			const top = rect.bottom + 8 + window.scrollY
			setMenuPositions((prev) => ({ ...prev, [chatId]: { left, top } }))
		}
	}

	// save/archive chat (toggle archived flag)
	const handleSaveChat = (chatId) => {
		const saved = loadChats()
		if (!saved[chatId]) return
		saved[chatId].archived = !saved[chatId].archived
		saveChats(saved)
		setChats(saved)
		setMenuOpenFor(null)
	}

	// request delete (show confirm modal)
	const requestDelete = (chatId) => {
		setMenuOpenFor(null)
		setConfirmDeleteFor(chatId)
	}

	// perform delete after confirm
	const performDelete = () => {
		if (!confirmDeleteFor) return
		const saved = loadChats()
		delete saved[confirmDeleteFor]
		saveChats(saved)
		setChats(saved)
		// if currently viewing this chat, go to hero
		if (currentChatId === confirmDeleteFor) {
			setCurrentChatId(null)
			setMessages([])
		}
		setConfirmDeleteFor(null)
	}

	const cancelDelete = () => setConfirmDeleteFor(null)

	/* ---------- UI ---------- */
	return (
		<div className="app-root">
			<header className="topbar">
				<div className="topbar-left">
					<Logo />
					<span className="brand">SigmaBoy AI</span>
				</div>
				<div className="topbar-right">
					<button className="btn-ghost">Log in</button>
					<button className="btn-primary">Sign up for free</button>
				</div>
			</header>

			<div className="app">
				{/* ---------- SIDEBAR ---------- */}
				<aside className="sidebar">
					<button
						className="new-chat"
						onClick={() => {
							// show hero/landing: clear current selection and messages
							setCurrentChatId(null)
							setMessages([])
							setInputMessage('')
						}}
					>
						+ New Chat
					</button>

					<div className="chat-history">
						{Object.values(chats).length === 0 && <p className="empty">No chats yet</p>}
						{Object.values(chats)
							.sort((a, b) => b.id - a.id)
							.map((chat) => (
								// row container to host item + menu
								<div
									key={chat.id}
									className={`chat-item-row ${currentChatId === chat.id ? 'active-row' : ''}`}
								>
									<div
										className={`chat-item ${currentChatId === chat.id ? 'active' : ''}`}
										onClick={() => {
											loadChat(chat.id)
											setMenuOpenFor(null)
										}}
									>
										{chat.title}
										{chat.archived && <span className="archived-badge"> • Đã lưu</span>}
									</div>

									{/* menu button */}
									<div className="chat-menu" onClick={(e) => e.stopPropagation()}>
										<button
											className="menu-btn"
											onClick={(e) => {
												e.stopPropagation()
												// pass button element so we can compute fixed position
												toggleMenu(chat.id, e.currentTarget)
											}}
											aria-label="Menu"
										>
											⋯
										</button>

										{menuOpenFor === chat.id && (
											<div
												className="menu-dropdown"
												onClick={(e) => e.stopPropagation()}
												style={{
													position: 'fixed',
													top: (menuPositions[chat.id]?.top ?? 0) + 'px',
													left: (menuPositions[chat.id]?.left ?? 0) + 'px',
													zIndex: 9999,
												}}
											>
												<button className="menu-action" onClick={() => handleSaveChat(chat.id)}>
													{chat.archived ? 'Bỏ lưu trữ' : 'Lưu trữ'}
												</button>
												<button className="menu-action danger" onClick={() => requestDelete(chat.id)}>
													Xóa
												</button>
											</div>
										)}
									</div>
								</div>
							))}
					</div>

					<button className="btn-clear" onClick={clearAll}>
						Clear All
					</button>
				</aside>

				{/* ---------- MAIN CONTENT ---------- */}
				<main className="main-content">
					{!currentChatId && messages.length === 0 ? (
						/* HERO LANDING */
						<section className="hero">
							<h1 className="hero-title">Hello! Can I help you?</h1>

							<form className="hero-box" onSubmit={handleHeroSubmit}>
								<div className="hero-input-row">
									<input
										className="hero-input"
										value={inputMessage}
										onChange={(e) => setInputMessage(e.target.value)}
										placeholder="Ask anything"
									/>
									<button type="submit" className="hero-send" aria-label="Send">
										<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
											<path d="M22 2L11 13" />
											<path d="M22 2L15 22l-4-9-9-4 20-7z" />
										</svg>
									</button>
								</div>

								<div className="hero-chips">
									<div className="chips">
										{['Attach', 'Search', 'Study'].map((text) => (
											<button
												key={text}
												type="button"
												className="chip"
												onClick={() => setInputMessage(text)}
											>
												{text}
											</button>
										))}
									</div>
								</div>
							</form>
						</section>
					) : (
						/* CHAT WINDOW */
						<div className="chat-container">
							<div className="messages">
								{messages.map((msg, idx) => (
									<div key={idx} className={`message ${msg.sender}-message`}>
										{/* bot avatar on left */}
										{msg.sender === 'bot' && (
											<div className="avatar bot-avatar">
												<img src="/sld.png" alt="bot" />
											</div>
										)}

										<div className="message-content">{msg.text}</div>

										{/* user avatar (simple circle) on right */}
										{msg.sender === 'user' && (
											<div className="avatar user-avatar" />
										)}
									</div>
								))}
								{isBotTyping && (
									<div className="message bot-message typing">
										<div className="message-content">...</div>
									</div>
								)}
							</div>

							<div className="input-container">
								<form className="input-form" onSubmit={sendMessage}>
									<div className="input-row">
										<textarea
											value={inputMessage}
											onChange={(e) => setInputMessage(e.target.value)}
											placeholder="Send a message..."
											rows="1"
											onKeyDown={(e) => {
												if (e.key === 'Enter' && !e.shiftKey) {
													e.preventDefault()
													sendMessage(e)
												}
											}}
										/>
										<button className="send-button" type="submit" aria-label="Send">
											<svg stroke="currentColor" fill="none" viewBox="0 0 24 24" width="20" height="20">
												<path d="M4 12h16m-7-7l7 7-7 7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
											</svg>
										</button>
									</div>
								</form>
							</div>
						</div>
					)}
				</main>

				{/* Confirm delete modal */}
				{confirmDeleteFor && (
					<div className="confirm-modal" role="dialog" aria-modal="true">
						<div className="confirm-box" onClick={(e) => e.stopPropagation()}>
							<p className="confirm-text">Có chắc chắn xóa đoạn chat không?</p>
							<div className="confirm-actions">
								<button className="btn" onClick={performDelete}>Có</button>
								<button className="btn ghost" onClick={cancelDelete}>Không</button>
							</div>
						</div>
					</div>
				)}
			</div>
		</div>
	)
}

export default App
