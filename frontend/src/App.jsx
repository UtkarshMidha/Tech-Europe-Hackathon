import { useEffect, useMemo, useRef, useState } from 'react'
import { fallback } from './fallback.js'
import { asNumber, buildWaterfall, formatLocator, money } from './model.js'

const token = new URLSearchParams(window.location.search).get('token') || ''
const api = (path) => `${path}${path.includes('?') ? '&' : '?'}${token ? `token=${encodeURIComponent(token)}` : ''}`.replace(/[?&]$/, '')
const aiExtras = (ai) => ai?.vision_passages ? ` · ${ai.vision_passages} vision` : ''
const aiStatus = (ai, fallback) => ai?.status === 'enhanced'
  ? `AI review · ${ai.accepted || 0} reviewed · ${ai.candidates || 0} new${aiExtras(ai)}`
  : ai?.status === 'offline' ? 'Deterministic mode'
    : ai?.status === 'rejected' ? `AI review · no claims passed${aiExtras(ai)}`
      : ai?.status === 'unavailable' ? `AI unavailable · ${(ai.detail || 'request failed').split(':')[0]}`
        : fallback

async function jsonFetch(path, options) {
  const response = await fetch(api(path), options)
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `Request failed: ${response.status}`)
  return response.json()
}

function Badge({ children, tone = 'neutral' }) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

function AuditContext({ payload }) {
  return <section className="audit-context">
    <div><span className="eyebrow">Cortea Audit Manager</span><h1>{payload.run.engagement || 'Uploaded engagement'}</h1><p>FY {payload.run.fiscal_year || '—'} · {Number(payload.run.row_count || 0).toLocaleString()} rows · {payload.run.files} source files</p></div>
    <div className="context-status"><span><i />{payload.run.integrity} integrity</span><span>{payload.metrics.citation_coverage}% cited</span><span>{payload.metrics.unsupported_claims || 0} unsupported claims</span></div>
  </section>
}

function FindingQueue({ findings, selected, onSelect, heldBack = 0 }) {
  return (
    <aside className="case-queue panel" aria-label="Ranked findings">
      <div className="panel-heading">
        <div><span className="eyebrow">Precision queue</span><h2>Review first</h2></div>
        <Badge tone="green">{findings.length} promoted</Badge>
      </div>
      <div className="queue-list">
        {findings.map((finding, index) => (
          <button key={finding.id} className={`case-card severity-${finding.severity} ${selected === finding.id ? 'selected' : ''}`} onClick={() => onSelect(finding)}>
            <span className="rank">0{index + 1}</span>
            <span className="case-copy">
              <span className="case-kicker">{finding.category}</span>
              <strong>{finding.title}</strong>
              <span className="case-meta">
                <Badge tone={finding.system_status === 'exception' ? 'red' : 'amber'}>{finding.system_status}</Badge>
                <span>{finding.confidence} evidence</span>
              </span>
            </span>
            <span className="case-amount">{finding.source === 'ai_investigation' ? 'AI lead' : finding.amounts?.gross ? money(finding.amounts.gross, true) : money(Math.abs(asNumber(finding.amounts?.pnl_effect)), true)}</span>
          </button>
        ))}
      </div>
      <div className="cleared-note">
        <span className="shield">✓</span>
        <div><strong>{heldBack} signal{heldBack === 1 ? '' : 's'} held back</strong><p>Unresolved or contradictory items stay outside the accusation queue.</p></div>
      </div>
    </aside>
  )
}

function EvidenceGraph({ graph, evidenceIds = [], evidence = {}, onEvidence }) {
  const nodes = graph?.nodes || []
  const edges = graph?.edges || []
  const resolveEvidence = (node, index) => {
    const terms = String(node.label).toLowerCase().split(/\W+/).filter((term) => term.length > 2)
    const ranked = evidenceIds.map((id) => ({ item: evidence[id], score: terms.reduce((score, term) => score + Number(JSON.stringify(evidence[id] || {}).toLowerCase().includes(term)), 0) })).filter(({ item }) => item)
    return ranked.sort((a, b) => b.score - a.score)[0]?.score ? ranked[0].item : ranked[index % Math.max(ranked.length, 1)]?.item
  }
  return (
    <div className="graph-shell">
      <div className="section-label"><span>Evidence chain</span><small>Read left to right · every relationship is source-backed</small></div>
      <div className="evidence-flow" role="group" aria-label="Evidence relationship chain">
        {nodes.map((node, index) => {
          const incoming = edges.filter((edge) => edge.target === node.id)
          const relation = incoming[0]
          const source = nodes.find((item) => item.id === relation?.source)
          const sourceEvidence = resolveEvidence(node, index)
          return <div className="flow-step" key={node.id}>
            {index > 0 && <div className="flow-connector" title={source ? `${source.label} ${relation?.label || 'links to'} ${node.label}` : relation?.label}>
              <span>{relation?.label || 'linked to'}</span><i /><b>›</b>
            </div>}
            <button className={`flow-node node-${node.type}`} onClick={() => sourceEvidence && onEvidence(sourceEvidence)} disabled={!sourceEvidence} title={sourceEvidence ? `Inspect: ${sourceEvidence.label}` : node.label}>
              <span className="flow-index">{String(index + 1).padStart(2, '0')}</span>
              <small>{node.type}</small>
              <strong>{node.label}</strong>
              {incoming.length > 1 && <em>+{incoming.length - 1} linked relation{incoming.length > 2 ? 's' : ''}</em>}
            </button>
          </div>
        })}
      </div>
      <div className="flow-legend"><span><i /> Entity or control</span><span><i /> Money movement</span><strong>{nodes.length} entities · {edges.length} verified links</strong></div>
    </div>
  )
}

function EvidenceRegister({ finding, evidence, onEvidence }) {
  const support = (finding.evidence_ids || []).map((id) => ({ ...evidence[id], id, role: 'Supporting' })).filter((item) => item.file)
  const counter = (finding.counter_evidence_ids || []).map((id) => ({ ...evidence[id], id, role: 'Counter-evidence' })).filter((item) => item.file)
  const rows = [...support, ...counter]
  return <section className="evidence-register">
    <div className="section-label"><span>Case evidence register</span><small>{support.length} supporting · {counter.length} counter-evidence</small></div>
    <div className="register-table"><table><thead><tr><th>Role</th><th>Evidence</th><th>Source</th><th>Location</th><th /></tr></thead><tbody>{rows.map((item) => <tr key={item.id}><td><Badge tone={item.role === 'Supporting' ? 'green' : 'neutral'}>{item.role}</Badge></td><td><strong>{item.label}</strong><small>{item.excerpt}</small></td><td>{item.file}</td><td>{formatLocator(item.locator)}</td><td><button onClick={() => onEvidence(item)}>Verify rows</button></td></tr>)}</tbody></table></div>
  </section>
}

function SourceViewer({ evidence, runId }) {
  if (!evidence) return <aside className="source-viewer panel empty"><p>Select an evidence chip to inspect its source.</p></aside>
  const path = evidence.file.split('/').map(encodeURIComponent).join('/')
  const page = evidence.locator?.page ? `#page=${evidence.locator.page}` : ''
  const sourceUrl = `${api(`/api/runs/${runId}/source/${path}`)}${page}`
  return (
    <aside className="source-viewer panel" aria-live="polite">
      <div className="proof-index"><span>Proof object</span><strong>{evidence.id?.replace(/^.*-/, '#')}</strong></div>
      <div className="source-topline"><Badge tone="green">Hash locked</Badge><span className="source-kind">{evidence.kind}</span></div>
      <h2>{evidence.label}</h2>
      <div className="file-name">{evidence.file}</div>
      <div className="locator">{formatLocator(evidence.locator)}</div>
      <div className="document-sheet">
        <div className="doc-toolbar"><span>Cited passage</span><span>{formatLocator(evidence.locator)}</span></div>
        <blockquote>{evidence.excerpt}</blockquote>
        {Object.keys(evidence.fields || {}).length > 0 && <dl className="source-fields">
          {Object.entries(evidence.fields).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{String(value)}</dd></div>)}
        </dl>}
      </div>
      <div className="hash-row"><span>SHA-256</span><code>{evidence.sha256?.slice(0, 18)}…</code></div>
      <a className="source-link" href={sourceUrl} target="_blank" rel="noreferrer">Open original source ↗</a>
      <p className="source-note">Locator and digest travel with the claim, so the passage remains independently reproducible.</p>
    </aside>
  )
}

function EvidenceOverlay({ evidence, runId, onClose }) {
  const closeRef = useRef(null)
  const [context, setContext] = useState(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!evidence) return undefined
    setContext(null); setCopied(false)
    jsonFetch(`/api/runs/${runId}/evidence/${evidence.id}/context`).then(setContext).catch(() => setContext(null))
    closeRef.current?.focus()
    const close = (event) => event.key === 'Escape' && onClose()
    document.addEventListener('keydown', close)
    return () => document.removeEventListener('keydown', close)
  }, [evidence, onClose, runId])
  if (!evidence) return null
  const path = evidence.file.split('/').map(encodeURIComponent).join('/')
  const page = evidence.locator?.page ? `#page=${evidence.locator.page}` : ''
  const sourceUrl = `${api(`/api/runs/${runId}/source/${path}`)}${page}`
  const fields = Object.entries(evidence.fields || {})
  const fallbackRows = fields.length ? fields : String(evidence.excerpt || '').split(/\s*[·;]\s*/).filter(Boolean).map((part, index) => {
    const split = part.indexOf(':')
    return split > 0 ? [part.slice(0, split), part.slice(split + 1)] : [`Observation ${index + 1}`, part]
  })
  return <div className="evidence-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="evidence-overlay" role="dialog" aria-modal="true" aria-labelledby="evidence-title">
      <header><div><span className="eyebrow">Source evidence</span><h2 id="evidence-title">{evidence.label}</h2><p>{evidence.file} · {formatLocator(evidence.locator)}</p></div><button ref={closeRef} onClick={onClose} aria-label="Close evidence">×</button></header>
      <div className="evidence-trust"><Badge tone="green">Hash verified</Badge><span>{evidence.kind}</span><code>SHA-256 {evidence.sha256?.slice(0, 22)}…</code></div>
      <div className="evidence-table-wrap">{context?.rows?.length ? <table className="context-table"><thead><tr><th>Row</th>{context.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{context.rows.map((row) => <tr className={row.relevant ? 'relevant-row' : ''} key={row.position}><th>{row.position}{row.relevant && <span>Relevant</span>}</th>{context.columns.map((column) => <td key={column}>{String(row.values[column] ?? '')}</td>)}</tr>)}</tbody></table> : <table><thead><tr><th>Field</th><th>Source value</th></tr></thead><tbody>{fallbackRows.map(([key, value], index) => <tr key={`${key}-${index}`}><th>{String(key).replaceAll('_', ' ')}</th><td>{String(value)}</td></tr>)}</tbody></table>}</div>
      <div className="evidence-passage"><span>Exact cited passage</span><blockquote>{evidence.excerpt}</blockquote></div>
      <footer><p>This view presents the cited row with its immediate source context.</p><div><button onClick={() => navigator.clipboard?.writeText(`${evidence.label} — ${evidence.file}, ${formatLocator(evidence.locator)} — SHA-256 ${evidence.sha256}`).then(() => setCopied(true))}>{copied ? 'Citation copied' : 'Copy citation'}</button><a href={sourceUrl} target="_blank" rel="noreferrer">Open original if needed ↗</a></div></footer>
    </section>
  </div>
}

function MoneyStrip({ amounts }) {
  const entries = [['Net basis', amounts?.net], ['Input VAT', amounts?.tax], ['Gross cash', amounts?.gross], ['Potential P&L', amounts?.pnl_effect]]
  const visible = entries.filter(([, value]) => value != null)
  return <div className={`money-strip money-columns-${visible.length}`}>{visible.map(([label, value]) => <div key={label}><span>{label}</span><strong className={asNumber(value) < 0 ? 'negative' : ''}>{money(value)}</strong></div>)}</div>
}

function CaseDetail({ finding, evidence, onEvidence, onReview }) {
  return (
    <section className="case-detail panel">
      <div className="case-header">
        <div>
          <span className="case-file-label">Active investigation · {finding.category}</span>
          <div className="title-badges"><Badge tone={finding.severity === 'critical' ? 'red' : 'amber'}>{finding.severity}</Badge>{finding.source === 'ai_investigation' && <Badge tone="green">AI discovered</Badge>}<Badge>{finding.confidence} evidence</Badge><Badge tone={finding.auditor_status === 'confirmed' ? 'green' : 'neutral'}>{finding.auditor_status}</Badge></div>
          <h1>{finding.title}</h1>
          <div className="case-summary"><span>What the evidence shows</span><p>{finding.summary}</p></div>
        </div>
        <button className="icon-button" title="Print this investigation" onClick={() => window.print()}>↗</button>
      </div>
      <MoneyStrip amounts={finding.amounts} />
      <EvidenceGraph graph={finding.graph} evidenceIds={[...(finding.evidence_ids || []), ...(finding.counter_evidence_ids || [])]} evidence={evidence} onEvidence={onEvidence} />
      <div className="case-lower">
        <div>
          <div className="section-label"><span>Observed facts</span><small>Values render from source-backed facts</small></div>
          <div className="fact-grid">
            {(finding.facts || []).map((fact) => <button key={`${fact.label}-${fact.value}`} className="fact" onClick={() => fact.evidence_id && onEvidence(evidence[fact.evidence_id])}><span>{fact.label}</span><strong>{fact.format === 'currency' ? money(fact.value) : fact.value}</strong></button>)}
          </div>
        </div>
        <div>
          <div className="section-label"><span>Evidence</span><small>{finding.evidence_ids.length} supporting sources</small></div>
          <div className="evidence-chips">
            {finding.evidence_ids.map((id) => evidence[id] && <button key={id} onClick={() => onEvidence(evidence[id])}><span>{evidence[id].kind}</span>{evidence[id].label}</button>)}
          </div>
          {finding.counter_evidence_ids?.length > 0 && <><div className="counter-title">Counter-evidence</div><div className="evidence-chips counter">{finding.counter_evidence_ids.map((id) => evidence[id] && <button key={id} onClick={() => onEvidence(evidence[id])}>{evidence[id].label}</button>)}</div></>}
        </div>
      </div>
      <EvidenceRegister finding={finding} evidence={evidence} onEvidence={onEvidence} />
      {finding.ai_narrative && <div className="ai-review"><div><span className="pulse-dot" /><span><strong>AI evidence reviewer</strong><small>Structured output passed the claim firewall</small></span></div><p>{finding.ai_narrative.summary}</p><ul>{finding.ai_narrative.rationale.map((item) => <li key={item}>{item}</li>)}</ul><div className="evidence-chips">{finding.ai_narrative.evidence_ids.map((id) => evidence[id] && <button key={id} onClick={() => onEvidence(evidence[id])}><span>cited</span>{evidence[id].label}</button>)}</div></div>}
      <div className="judgement-grid">
        <div className="caveat"><span>Professional judgement</span><p>{finding.caveats?.join(' ')}</p></div>
        <div className="next-step"><span>Next audit procedure</span><p>{finding.next_step}</p></div>
      </div>
      <div className="review-bar"><span>Auditor conclusion</span><div><button className="button-secondary" onClick={() => onReview('dismissed')}>Dismiss with reason</button><button className="button-primary" onClick={() => onReview('confirmed')}>Confirm exception</button></div></div>
    </section>
  )
}

function Waterfall({ run, findings }) {
  if (run.reported_profit == null) return <section className="impact-panel panel empty-state" tabIndex="-1"><span className="eyebrow">Calculation unavailable</span><h1>No sourced trial balance was mapped</h1><p>Cortea Audit Manager will not invent a zero baseline. Upload a supported trial-balance workbook to activate the profit bridge.</p></section>
  const data = buildWaterfall(run, findings)
  const max = Math.max(data.reported, ...data.items.map((item) => Math.abs(item.delta)), 1)
  return <section className="impact-panel panel" tabIndex="-1">
    <div className="panel-heading"><div><span className="eyebrow">Financial impact</span><h2>Proposed profit bridge</h2></div><Badge tone="amber">Auditor review required</Badge></div>
    <p className="impact-lead">The bridge keeps classification and cut-off assumptions visible instead of presenting a false certainty.</p>
    <div className="impact-overview"><div><span>Reported</span><strong>{money(data.reported)}</strong></div><i>→</i><div className="impact-adjusted"><span>Evidence-adjusted</span><strong>{money(data.adjusted)}</strong></div><div className="impact-delta"><span>Proposed movement</span><strong>{money(data.adjusted - data.reported)}</strong></div></div>
    <div className="waterfall">
      <div className="waterfall-row total"><span>Reported draft profit</span><div><i style={{ width: `${(data.reported / max) * 100}%` }} /></div><strong>{money(data.reported)}</strong></div>
      {data.items.map((item) => <div className="waterfall-row adjustment" key={item.id}><span>{item.label}</span><div><i style={{ width: `${(Math.abs(item.delta) / max) * 100}%` }} /></div><strong>{money(item.delta)}</strong></div>)}
      <div className="waterfall-row adjusted"><span>Proposed adjusted profit</span><div><i style={{ width: `${(data.adjusted / max) * 100}%` }} /></div><strong>{money(data.adjusted)}</strong></div>
    </div>
    <div className="impact-foot"><div><strong>{money(Math.abs(data.reported - data.adjusted))}</strong><span>combined proposed adjustment</span></div><div><strong>Assumption-aware</strong><span>every adjustment remains subject to auditor review</span></div></div>
  </section>
}

function CorpusSearch({ runId }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [message, setMessage] = useState('Search PDF pages, Word paragraphs, and source rows.')
  const search = async (event) => {
    event.preventDefault()
    if (query.trim().length < 2) return
    setMessage('Searching the sealed local corpus…')
    try {
      const data = await jsonFetch(`/api/runs/${runId}/search?q=${encodeURIComponent(query)}`)
      setResults(data.results); setMessage(`${data.results.length} reproducible match${data.results.length === 1 ? '' : 'es'}`)
    } catch (error) { setResults([]); setMessage(error.message) }
  }
  return <div className="corpus-search">
    <div><span className="eyebrow">Evidence search</span><h3>Search the complete dossier</h3><p>{message}</p></div>
    <form onSubmit={search}><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. bank account, approval, December service" aria-label="Search source corpus" /><button>Search sources</button></form>
    {results.length > 0 && <div className="search-results">{results.map((result, index) => {
      const path = result.file.split('/').map(encodeURIComponent).join('/')
      const page = result.locator?.page ? `#page=${result.locator.page}` : ''
      return <a key={`${result.file}-${index}`} href={`${api(`/api/runs/${runId}/source/${path}`)}${page}`} target="_blank" rel="noreferrer"><span>{result.file} · {formatLocator(result.locator)}</span><p>{result.excerpt}</p></a>
    })}</div>}
  </div>
}

function Manifest({ payload }) {
  const formats = [...new Set(payload.manifest.map((file) => file.kind))]
  return <section className="manifest-panel panel" tabIndex="-1"><div className="panel-heading"><div><span className="eyebrow">Chain of custody</span><h2>Dossier manifest</h2></div><div className="manifest-badges"><Badge tone="green">{payload.run.files} files hashed</Badge>{payload.run.legacy_conversions > 0 && <Badge tone="amber">Converted {payload.run.legacy_conversions} legacy files</Badge>}{payload.run.adaptive_sources > 0 && <Badge tone="amber">AI mapped {payload.run.adaptive_sources}</Badge>}{(payload.ai?.vision_passages || payload.run.vision_passages) > 0 && <Badge tone="amber">Vision read {payload.ai?.vision_passages || payload.run.vision_passages}</Badge>}</div></div>
    <div className="source-overview"><div><span>Originals sealed</span><strong>{payload.run.files}</strong><small>SHA-256 fingerprints</small></div><div><span>Formats understood</span><strong>{formats.length}</strong><small>{formats.join(' · ')}</small></div><div><span>Claims cited</span><strong>{payload.metrics.citation_coverage}%</strong><small>click through to source</small></div><div><span>Claim firewall</span><strong>{payload.metrics.unsupported_claims || 0}</strong><small>unsupported promoted</small></div></div>
    <CorpusSearch runId={payload.run.id} />
    {payload.signals?.length > 0 && <div className="held-signals"><div><span className="eyebrow">Precision guardrail</span><h3>Held-back signals</h3></div>{payload.signals.map((signal) => <article key={signal.id}><Badge>{signal.status}</Badge><strong>{signal.title}</strong><p>{signal.disposition}</p><div>{signal.evidence_ids.map((id) => {
      const item = payload.evidence[id]
      if (!item) return null
      const path = item.file.split('/').map(encodeURIComponent).join('/')
      return <a key={id} href={api(`/api/runs/${payload.run.id}/source/${path}`)} target="_blank" rel="noreferrer">{item.label} ↗</a>
    })}</div></article>)}</div>}
    <div className="manifest-table"><div className="manifest-head"><span>Source</span><span>Type</span><span>Records</span><span>Status</span></div>{payload.manifest.map((file) => <div className="manifest-row" key={file.path}><span>{file.path}</span><span>{file.kind}</span><span>{file.records ?? '—'}</span><span className="parsed">✓ {file.status}</span></div>)}</div>
  </section>
}

function AskBar({ runId, onResult, evidence, onEvidence, disabled }) {
  const [question, setQuestion] = useState('Who could create and pay a vendor?')
  const [answer, setAnswer] = useState(null)
  const [busy, setBusy] = useState(false)
  const ask = async (value = question) => {
    setQuestion(value); setBusy(true)
    try {
      const result = await jsonFetch(`/api/runs/${runId || 'sample'}/ask`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: value }) })
      setAnswer(result); onResult(result)
    } catch (error) {
      setAnswer({ error: error.message })
    } finally { setBusy(false) }
  }
  return <section className="ask-panel panel">
    <div className="ask-title"><span className="pulse-dot" /><div><span className="eyebrow">Ask the ledger</span><h2>Questions become reproducible procedures</h2></div></div>
    <form onSubmit={(event) => { event.preventDefault(); ask() }}><input disabled={disabled} aria-label="Ask the ledger" value={question} onChange={(event) => setQuestion(event.target.value)} /><button disabled={busy || disabled}>{busy ? 'Tracing…' : 'Trace answer'}</button></form>
    <div className="prompt-chips">{['Who could create and pay a vendor?', 'Show payments below the approval limit', 'Trace the profit adjustment'].map((item) => <button disabled={disabled} key={item} onClick={() => ask(item)}>{item}</button>)}</div>
    {answer && <div className={`answer ${answer.error ? 'answer-error' : ''}`}><span>{answer.error ? 'Trace unavailable' : answer.method === 'openai_grounded' ? 'AI answer · grounded in dossier evidence' : 'Evidence-backed answer'}</span><p>{answer.error || answer.answer}</p>{!answer.error && <div className="answer-citations">{(answer.evidence_ids || []).map((id) => { const item = answer.evidence?.[id] || evidence[id]; return item && <button key={id} onClick={() => onEvidence(item)}>{item.label}</button> })}</div>}</div>}
  </section>
}

function App() {
  const [payload, setPayload] = useState(fallback)
  const [selectedFinding, setSelectedFinding] = useState(fallback.findings[0].id)
  const [selectedEvidence, setSelectedEvidence] = useState(null)
  const [view, setView] = useState('investigation')
  const [status, setStatus] = useState('Loading live analysis…')
  const [uploading, setUploading] = useState(false)
  const [aiBusy, setAiBusy] = useState(false)
  const inputRef = useRef(null)
  const zipRef = useRef(null)

  const runAI = async (runId = payload.run.id) => {
    setAiBusy(true); setStatus('AI review running · searching evidence…')
    try {
      const reviewed = await jsonFetch(`/api/runs/${runId}/ai-review`, { method: 'POST' })
      setPayload(reviewed)
      if (reviewed.findings.length && !reviewed.findings.some((item) => item.id === selectedFinding)) {
        setSelectedFinding(reviewed.findings[0].id)
        setView('investigation')
      }
      setStatus(aiStatus(reviewed.ai, 'AI review complete'))
    } catch (error) { setStatus(`AI unavailable · ${error.message}`) } finally { setAiBusy(false) }
  }

  useEffect(() => {
    const controller = new AbortController()
    jsonFetch('/api/demo', { signal: controller.signal }).then((data) => {
      setPayload(data)
      if (data.findings.length) {
        setSelectedFinding(data.findings[0].id)
      } else {
        setSelectedFinding(null); setSelectedEvidence(null); setView('manifest')
      }
      setStatus('Live dossier')
      runAI('sample')
    }).catch(() => setStatus('Demo snapshot'))
    return () => controller.abort()
  }, [])

  const finding = useMemo(() => payload.findings.find((item) => item.id === selectedFinding) || payload.findings[0], [payload, selectedFinding])
  const chooseFinding = (item) => { setSelectedFinding(item.id); setSelectedEvidence(null); setView('investigation') }
  const goToView = (next) => {
    setView(next)
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const selector = next === 'investigation' ? '.workspace' : next === 'impact' ? '.impact-panel' : '.manifest-panel'
      const target = document.querySelector(selector)
      target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      target?.focus({ preventScroll: true })
    }))
  }

  const upload = async (files) => {
    if (!files?.length) return
    setUploading(true); setStatus(`Hashing ${files.length} files…`)
    const uploadBytes = Array.from(files).reduce((total, file) => total + file.size, 0)
    const progressTimers = uploadBytes > 20 * 1024 * 1024 ? [
      setTimeout(() => setStatus('Large dossier · normalizing source tables…'), 12000),
      setTimeout(() => setStatus('Large dossier · reconciling ledger populations…'), 45000),
      setTimeout(() => setStatus('Large dossier · running evidence-backed audit tests…'), 90000),
    ] : []
    if (progressTimers.length) setStatus('Large dossier · validating archive…')
    const body = new FormData()
    Array.from(files).forEach((file) => body.append('files', file, file.webkitRelativePath || file.name))
    try {
      const created = await jsonFetch('/api/runs', { method: 'POST', body })
      const data = await jsonFetch(`/api/runs/${created.run_id}`)
      setPayload(data)
      if (data.findings.length) {
        setSelectedFinding(data.findings[0].id); setSelectedEvidence(null); setStatus(aiStatus(data.ai, 'Fresh dossier analyzed'))
      } else {
        setSelectedFinding(null); setSelectedEvidence(null); setStatus('No supportable finding promoted'); setView('manifest')
      }
      runAI(created.run_id)
    } catch (error) { setStatus(error.message) } finally { progressTimers.forEach(clearTimeout); setUploading(false); if (inputRef.current) inputRef.current.value = ''; if (zipRef.current) zipRef.current.value = '' }
  }

  const review = async (reviewStatus) => {
    if (!finding) return
    let note = ''
    if (reviewStatus === 'dismissed') {
      const entered = window.prompt('Why is this finding being dismissed? The reason becomes part of the audit trail.')
      if (entered === null) return
      note = entered.trim()
      if (!note) { setStatus('A dismissal reason is required'); return }
    }
    try {
      await jsonFetch(`/api/findings/${finding.id}/review`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_id: payload.run.id, status: reviewStatus, note }) })
      setPayload((current) => ({ ...current, findings: current.findings.map((item) => item.id === finding.id ? { ...item, auditor_status: reviewStatus, review_note: note } : item) }))
      setStatus(`Finding ${reviewStatus}`)
    } catch (error) { setStatus(`Review not saved: ${error.message}`) }
  }

  const onAskResult = (result) => {
    if (result.finding_id) setSelectedFinding(result.finding_id)
  }

  return <div className="app-shell">
    <header className="topbar">
      <a className="cortea-brand" href={`${window.location.pathname}${window.location.search}`} aria-label="Cortea Audit Manager home"><img src="https://cdn.prod.website-files.com/6978eb8068291edea0b8b01f/69b14b3dbc0c312737382a11_Favicon.png" alt="" /><span><strong>cortea</strong><small>Audit Manager</small></span></a>
      <nav aria-label="Workspace views"><button className={view === 'investigation' ? 'active' : ''} aria-current={view === 'investigation' ? 'page' : undefined} onClick={() => goToView('investigation')}>Investigation</button><button className={view === 'impact' ? 'active' : ''} aria-current={view === 'impact' ? 'page' : undefined} onClick={() => goToView('impact')}>Materiality</button><button className={view === 'manifest' ? 'active' : ''} aria-current={view === 'manifest' ? 'page' : undefined} onClick={() => goToView('manifest')}>Sources</button></nav>
      <div className="top-actions"><span className="mode" title={status}><i />{status}</span><input ref={inputRef} hidden type="file" multiple webkitdirectory="" directory="" onChange={(event) => upload(event.target.files)} /><input ref={zipRef} hidden type="file" accept=".zip,application/zip" onChange={(event) => upload(event.target.files)} /><button className="button-ai" disabled={aiBusy || uploading} onClick={() => runAI()}>{aiBusy ? 'Reviewing…' : 'Refresh AI'}</button><button className="button-zip" disabled={uploading} onClick={() => zipRef.current?.click()}>Open ZIP</button><button className="button-upload" disabled={uploading} onClick={() => inputRef.current?.click()}>{uploading ? 'Analyzing…' : 'Open folder'}</button></div>
    </header>

    <main>
      <AuditContext payload={payload} />

      {view === 'investigation' && <>
        <div className="workspace" tabIndex="-1"><FindingQueue findings={payload.findings} selected={finding?.id} onSelect={chooseFinding} heldBack={payload.metrics.cleared_signals || 0} />{finding ? <CaseDetail finding={finding} evidence={payload.evidence} onEvidence={setSelectedEvidence} onReview={review} /> : <section className="case-detail panel empty-state"><span className="eyebrow">Precision over noise</span><h1>No supportable finding was promoted</h1><p>Review the source manifest and mapping coverage before adding a hypothesis.</p></section>}</div>
        <AskBar runId={payload.run.id} onResult={onAskResult} evidence={payload.evidence} onEvidence={setSelectedEvidence} disabled={!finding} />
      </>}
      {view === 'impact' && <Waterfall run={payload.run} findings={payload.findings} />}
      {view === 'manifest' && <Manifest payload={payload} />}
    </main>
    <EvidenceOverlay evidence={selectedEvidence} runId={payload.run.id} onClose={() => setSelectedEvidence(null)} />
    <footer><span>Cortea Audit Manager · AI supports, auditors decide.</span><a href={api(`/api/runs/${payload.run.id}/report`)} target="_blank" rel="noreferrer">Open printable evidence report ↗</a></footer>
  </div>
}

export default App
