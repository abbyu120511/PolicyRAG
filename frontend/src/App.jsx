import { useEffect, useMemo, useState } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const navItems = [
  { id: 'chat', label: '智能问答', glyph: '◌' },
  { id: 'library', label: '知识库管理', glyph: '▤' },
]

function apiUrl(path) {
  return `${API_BASE}${path}`
}

function pageFromHash() {
  const match = window.location.hash.match(/^#\/knowledge-base\/([^/]+)\/chunks$/)
  if (match) return { page: 'chunks', filename: decodeURIComponent(match[1]) }
  return { page: window.location.hash === '#/knowledge-base' ? 'library' : 'chat', filename: null }
}

function hashForPage(page) {
  return page === 'library' ? '#/knowledge-base' : '#/chat'
}

function hashForChunks(filename) {
  return `#/knowledge-base/${encodeURIComponent(filename)}/chunks`
}

function referenceHref(reference) {
  const documentUrl = apiUrl(reference.document_url)
  return reference.file_type === 'pdf' ? `${documentUrl}#page=${reference.page}` : documentUrl
}

function Status({ status }) {
  const labels = {
    enabled: '已启用',
    disabled: '已停用',
    uploaded: '待启用',
    processing: '处理中',
    failed: '处理失败',
  }
  return <span className={`status status--${status}`}>{labels[status] || status}</span>
}

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function App() {
  const [route, setRoute] = useState(pageFromHash)
  const [documents, setDocuments] = useState([])
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(true)
  const [libraryError, setLibraryError] = useState('')
  const [file, setFile] = useState(null)
  const [isUploading, setIsUploading] = useState(false)
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [isAsking, setIsAsking] = useState(false)
  const [selectedReference, setSelectedReference] = useState(null)

  const enabledCount = useMemo(() => documents.filter((document) => document.enabled).length, [documents])

  async function loadDocuments() {
    setIsLoadingDocuments(true)
    try {
      const response = await fetch(apiUrl('/documents'))
      if (!response.ok) throw new Error('无法读取知识库')
      setDocuments(await response.json())
      setLibraryError('')
    } catch (error) {
      setLibraryError(error.message)
    } finally {
      setIsLoadingDocuments(false)
    }
  }

  useEffect(() => {
    loadDocuments()
  }, [])

  useEffect(() => {
    const syncRoute = () => setRoute(pageFromHash())
    if (!window.location.hash) window.location.hash = '/chat'
    syncRoute()
    window.addEventListener('hashchange', syncRoute)
    return () => window.removeEventListener('hashchange', syncRoute)
  }, [])

  function navigate(pageId) {
    window.location.hash = hashForPage(pageId)
  }

  function inspectChunks(filename) {
    window.location.hash = hashForChunks(filename)
  }

  const page = route.page

  async function uploadDocument(event) {
    event.preventDefault()
    if (!file) return
    setIsUploading(true)
    setLibraryError('')
    try {
      const form = new FormData()
      form.append('file', file)
      const response = await fetch(apiUrl('/documents/upload'), { method: 'POST', body: form })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || '上传失败')
      setFile(null)
      event.currentTarget.reset()
      await loadDocuments()
    } catch (error) {
      setLibraryError(error.message)
    } finally {
      setIsUploading(false)
    }
  }

  async function updateDocument(filename, action) {
    setLibraryError('')
    try {
      const response = await fetch(apiUrl(`/documents/${encodeURIComponent(filename)}/${action}`), { method: 'POST' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || '操作失败')
      await loadDocuments()
    } catch (error) {
      setLibraryError(error.message)
    }
  }

  async function removeDocument(filename) {
    if (!window.confirm(`确定下架“${filename}”吗？原文件、向量和派生数据都会从本机移除。`)) return
    setLibraryError('')
    try {
      const response = await fetch(apiUrl(`/documents/${encodeURIComponent(filename)}`), { method: 'DELETE' })
      if (!response.ok) {
        const payload = await response.json()
        throw new Error(payload.detail || '下架失败')
      }
      await loadDocuments()
    } catch (error) {
      setLibraryError(error.message)
    }
  }

  async function askQuestion(event) {
    event.preventDefault()
    const trimmedQuestion = question.trim()
    if (!trimmedQuestion || isAsking) return
    setMessages((current) => [...current, { role: 'user', text: trimmedQuestion }])
    setQuestion('')
    setIsAsking(true)
    try {
      const response = await fetch(apiUrl('/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmedQuestion }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || '问答请求失败')
      setMessages((current) => [...current, { role: 'assistant', ...payload }])
      if (payload.references?.[0]) setSelectedReference(payload.references[0])
    } catch (error) {
      setMessages((current) => [...current, { role: 'error', text: error.message }])
    } finally {
      setIsAsking(false)
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="window-controls" aria-hidden="true"><i /><i /><i /></div>
        <div className="brand-lockup">
          <div className="brand-mark" aria-label="PolicyRAG Studio">P</div>
          <div className="brand-copy">
            <strong>PolicyRAG</strong>
            <span>LOCAL KNOWLEDGE</span>
          </div>
        </div>
        <nav aria-label="主导航">
          {navItems.map((item) => (
            <button key={item.id} className={`nav-item ${page === item.id || (item.id === 'library' && page === 'chunks') ? 'is-active' : ''}`} onClick={() => navigate(item.id)}>
              <span aria-hidden="true">{item.glyph}</span>{item.label}
            </button>
          ))}
        </nav>
        <div className="library-pulse">
          <span className="pulse-dot" />
          <div><b>{enabledCount}</b><small>份资料正在检索</small></div>
        </div>
        <div className="workspace-label">本地工作区<br /><strong>保险产品资料库</strong></div>
      </aside>

      <section className="work-area">
        <header className="topbar">
          <div><span className="eyebrow">POLICYRAG / WORKSPACE</span><h1>{page === 'chat' ? '智能问答' : page === 'chunks' ? '资料检视器' : '知识库管理'}</h1></div>
          <div className="local-badge"><span />本地模式</div>
        </header>

        {page === 'chat' ? (
          <ChatWorkspace
            question={question}
            setQuestion={setQuestion}
            messages={messages}
            isAsking={isAsking}
            askQuestion={askQuestion}
            selectedReference={selectedReference}
            setSelectedReference={setSelectedReference}
          />
        ) : page === 'library' ? (
          <LibraryWorkspace
            documents={documents}
            isLoading={isLoadingDocuments}
            error={libraryError}
            file={file}
            setFile={setFile}
            isUploading={isUploading}
            uploadDocument={uploadDocument}
            updateDocument={updateDocument}
            removeDocument={removeDocument}
            inspectChunks={inspectChunks}
          />
        ) : (
          <ChunkWorkspace filename={route.filename} backToLibrary={() => navigate('library')} />
        )}
      </section>
    </main>
  )
}

function ChatWorkspace({ question, setQuestion, messages, isAsking, askQuestion, selectedReference, setSelectedReference }) {
  const empty = messages.length === 0
  return <div className="chat-layout">
    <section className="conversation-panel">
      <div className="conversation-head"><div><h2>向资料库提问</h2><p>回答只基于已启用的产品资料，并附带可验证的页码依据。</p></div><span className="evidence-key">证据驱动</span></div>
      <div className={`messages ${empty ? 'messages--empty' : ''}`}>
        {empty && <div className="empty-chat"><span>⌁</span><h3>从一条事实开始</h3><p>例如：这份癌症保险的等候期是多久？</p></div>}
        {messages.map((message, index) => <article className={`message message--${message.role}`} key={`${message.role}-${index}`}>
          <span className="message-label">{message.role === 'user' ? '你的提问' : message.role === 'error' ? '请求失败' : '资料助手'}</span>
          <p>{message.text || message.answer}</p>
          {message.references?.length > 0 && <div className="inline-references">
            {message.references.map((reference) => <a key={`${reference.source_file}-${reference.page}`} href={referenceHref(reference)} target="_blank" rel="noreferrer" onClick={() => setSelectedReference(reference)}>↗ {reference.source_file.replace(/\.[^.]+$/, '')} · 第 {reference.page} 页</a>)}
          </div>}
        </article>)}
        {isAsking && <div className="thinking"><i /><i /><i /> 正在检索资料与核验证据</div>}
      </div>
      <form className="question-box" onSubmit={askQuestion}>
        <textarea value={question} onChange={(event) => setQuestion(event.target.value)} rows="2" placeholder="输入有关产品资料的问题…" aria-label="输入问题" />
        <button type="submit" disabled={!question.trim() || isAsking}>发送 <span>↗</span></button>
      </form>
    </section>
    <EvidenceRail reference={selectedReference} />
  </div>
}

function EvidenceRail({ reference }) {
  if (!reference) return <aside className="evidence-rail evidence-rail--empty"><span className="rail-index">证据轨</span><div><b>等待一条回答</b><p>命中资料后，这里会显示可点击的原始页码。</p></div></aside>
  const url = referenceHref(reference)
  return <aside className="evidence-rail">
    <span className="rail-index">证据轨 / {String(reference.page).padStart(2, '0')}</span>
    <div className="reference-meta"><span>已引用</span><h3>{reference.source_file.replace(/\.[^.]+$/, '')}</h3><p>第 {reference.page} 页 · {reference.file_type.toUpperCase()}</p></div>
    {reference.file_type === 'pdf' ? <><iframe title={`第 ${reference.page} 页 PDF`} src={url} /><a className="source-link" href={url} target="_blank" rel="noreferrer">在新标签页打开 PDF ↗</a></> : <a className="source-link" href={url} target="_blank" rel="noreferrer">打开 Markdown 原文 ↗</a>}
  </aside>
}

function LibraryWorkspace({ documents, isLoading, error, file, setFile, isUploading, uploadDocument, updateDocument, removeDocument, inspectChunks }) {
  return <div className="library-workspace">
    <section className="library-intro"><div><span className="eyebrow">KNOWLEDGE CONTROL</span><h2>资料入库前，先掌握它的状态。</h2><p>上传不等于启用。只有处理完成并启用的资料才会参与问答检索。</p></div><div className="library-rule">启用 =<br /><strong>可被回答引用</strong></div></section>
    <section className="upload-zone"><form onSubmit={uploadDocument}><div><span className="upload-glyph">↑</span><div><b>加入本地资料</b><p>支持 PDF 与 Markdown；上传后默认保持未启用状态。</p></div></div><label className="file-picker"><input type="file" accept=".pdf,.md,application/pdf,text/markdown,text/plain" onChange={(event) => setFile(event.target.files?.[0] || null)} />{file ? file.name : '选择文件'}</label><button type="submit" disabled={!file || isUploading}>{isUploading ? '正在保存…' : '上传资料'}</button></form></section>
    {error && <div className="library-error">{error}</div>}
    <section className="document-table-wrap"><div className="table-heading"><div><span className="eyebrow">DOCUMENT REGISTER</span><h2>资料清单</h2></div><span>{documents.length} 份本地资料</span></div>
      {isLoading ? <div className="table-empty">正在读取知识库…</div> : documents.length === 0 ? <div className="table-empty">还没有资料。上传第一份 PDF 或 Markdown 开始。</div> : <div className="document-table" role="table">
        <div className="document-row document-row--head" role="row"><span>资料</span><span>格式 / 规模</span><span>状态</span><span>更新时间</span><span>操作</span></div>
        {documents.map((document) => <div className="document-row" role="row" key={document.filename}><div className="doc-name"><span className="doc-type">{document.file_type === 'pdf' ? 'PDF' : 'MD'}</span><div><b>{document.filename}</b><small>{document.error || '本地私有资料'}</small></div></div><div className="doc-stats"><span>{document.page_count ? `${document.page_count} 页` : '尚未处理'}</span><small>{document.chunk_count ? `${document.chunk_count} chunks` : '—'}</small></div><Status status={document.status} /><span className="updated-at">{formatDate(document.updated_at)}</span><div className="row-actions">{document.chunk_count ? <button onClick={() => inspectChunks(document.filename)}>查看切块</button> : null}{document.enabled ? <button onClick={() => updateDocument(document.filename, 'disable')}>停用</button> : <button className="action-primary" disabled={document.status === 'processing'} onClick={() => updateDocument(document.filename, 'enable')}>{document.status === 'processing' ? '处理中' : '启用'}</button>}<button className="action-danger" onClick={() => removeDocument(document.filename)}>下架</button></div></div>)}
      </div>}
    </section>
  </div>
}

function ChunkWorkspace({ filename, backToLibrary }) {
  const [chunks, setChunks] = useState([])
  const [selectedChunkId, setSelectedChunkId] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let isCurrent = true
    async function loadChunks() {
      setIsLoading(true)
      setError('')
      try {
        const response = await fetch(apiUrl(`/documents/${encodeURIComponent(filename)}/chunks`))
        const payload = await response.json()
        if (!response.ok) throw new Error(payload.detail || '无法读取切块预览')
        if (!isCurrent) return
        setChunks(payload.chunks)
        setSelectedChunkId(payload.chunks[0]?.id || null)
      } catch (loadError) {
        if (isCurrent) setError(loadError.message)
      } finally {
        if (isCurrent) setIsLoading(false)
      }
    }
    loadChunks()
    return () => { isCurrent = false }
  }, [filename])

  const selectedChunk = chunks.find((chunk) => chunk.id === selectedChunkId) || chunks[0]
  const chunksByPage = useMemo(() => chunks.reduce((pages, chunk) => {
    const page = chunk.metadata.page
    pages[page] = [...(pages[page] || []), chunk]
    return pages
  }, {}), [chunks])
  const pageCount = Object.keys(chunksByPage).length
  const selectedPage = selectedChunk?.metadata.page
  const sourceUrl = selectedChunk
    ? `${apiUrl(`/documents/${encodeURIComponent(filename)}`)}${selectedChunk.metadata.page ? `#page=${selectedChunk.metadata.page}` : ''}`
    : apiUrl(`/documents/${encodeURIComponent(filename)}`)

  return <section className="chunk-workspace">
    <header className="chunk-intro">
      <div>
        <button className="back-link" onClick={backToLibrary}>← 返回知识库</button>
        <span className="eyebrow">CHUNK INSPECTOR</span>
        <h2>{filename}</h2>
        <p>这里展示实际用于 embedding 的切块。选择任意切块，可核查文字、页码和 metadata。</p>
      </div>
      {!isLoading && !error && <div className="chunk-summary"><strong>{chunks.length}</strong><span>chunks</span><small>覆盖 {pageCount} 页</small></div>}
    </header>

    {error ? <div className="chunk-error"><b>无法打开切块预览</b><span>{error}</span><button onClick={backToLibrary}>返回知识库</button></div>
      : isLoading ? <div className="chunk-loading"><i /><span>正在读取已清洗的资料与切块 metadata…</span></div>
        : chunks.length === 0 ? <div className="chunk-error"><b>这份资料还没有可预览的切块</b><span>请返回知识库，先启用资料完成处理。</span><button onClick={backToLibrary}>返回知识库</button></div>
          : <div className="chunk-inspector">
            <aside className="chunk-index" aria-label="切块索引">
              <div className="chunk-index-heading"><span>证据索引</span><small>按 PDF 页码排列</small></div>
              <div className="chunk-index-list">
                {Object.entries(chunksByPage).map(([page, pageChunks]) => <section className="chunk-page-group" key={page}>
                  <div><b>第 {page} 页</b><span>{pageChunks.length} chunks</span></div>
                  {pageChunks.map((chunk) => <button className={`chunk-index-item ${chunk.id === selectedChunk?.id ? 'is-selected' : ''}`} onClick={() => setSelectedChunkId(chunk.id)} key={chunk.id}>
                    <strong>Chunk {String(chunk.metadata.chunk_index).padStart(2, '0')}</strong>
                    <span>{chunk.text.replace(/\s+/g, ' ').slice(0, 68)}{chunk.text.length > 68 ? '…' : ''}</span>
                  </button>)}
                </section>)}
              </div>
            </aside>
            <article className="chunk-detail">
              <div className="chunk-detail-head">
                <div><span className="eyebrow">SELECTED EVIDENCE</span><h3>第 {selectedPage} 页 · Chunk {String(selectedChunk.metadata.chunk_index).padStart(2, '0')}</h3></div>
                <a href={sourceUrl} target="_blank" rel="noreferrer">打开原始 {selectedChunk.metadata.source_file.toLowerCase().endsWith('.pdf') ? 'PDF' : '文件'} ↗</a>
              </div>
              <section className="chunk-content"><span>实际写入 embedding 的文字</span><p>{selectedChunk.text}</p></section>
              <section className="metadata-panel">
                <div><span className="eyebrow">METADATA</span><h4>这张资料卡的标签</h4></div>
                <dl>
                  <div><dt>chunk_id</dt><dd><code>{selectedChunk.id}</code></dd></div>
                  {Object.entries(selectedChunk.metadata).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}
                </dl>
              </section>
            </article>
          </div>}
  </section>
}

export default App
