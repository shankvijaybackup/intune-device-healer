import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [config, setConfig] = useState({
    atomicworkUrl: '',
    atomicworkApiKey: '',
    azureClientId: '',
    azureTenantId: '',
    azureClientSecret: '',
  })
  const [status, setStatus] = useState('Checking connectivity...')
  const [isSaving, setIsSaving] = useState(false)

  const [deployment, setDeployment] = useState(null)

  useEffect(() => {
    // Fetch current server health on mount
    const checkHealth = async () => {
      try {
        const res = await fetch('/healthz')
        if (res.ok) {
          setStatus('Auto-Heal Engine: Online')
        } else {
          setStatus('Auto-Heal Engine: Error')
        }
      } catch (err) {
        setStatus('Auto-Heal Engine: Offline')
      }
    }
    checkHealth()
  }, [])

  const handleChange = (e) => {
    const { name, value } = e.target
    setConfig(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setIsSaving(true)
    try {
      // Obfuscated Payload Pattern (Zero-Visibility)
      const encodedConfig = {
        ...config,
        atomicworkApiKey: btoa(config.atomicworkApiKey),
        azureClientId: btoa(config.azureClientId),
        azureTenantId: btoa(config.azureTenantId),
        azureClientSecret: btoa(config.azureClientSecret),
      }

      const response = await fetch('/api/v1/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(encodedConfig)
      })
      const data = await response.json()
      if (response.ok) {
        setDeployment(data.deployment)
        alert('Configuration saved successfully!')
      } else {
        alert('Failed to save configuration.')
      }
    } catch (err) {
      alert('Error connecting to server.')
    } finally {
      setIsSaving(false)
    }
  }

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    alert('Copied to clipboard!')
  }

  return (
    <div className="glass-card">
      <h1>Auto-Heal Dashboard</h1>
      <p className="subtitle">System Configuration & Intelligent Monitoring</p>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Atomicwork Account URL</label>
          <input
            type="text"
            name="atomicworkUrl"
            value={config.atomicworkUrl}
            onChange={handleChange}
            placeholder="https://your-domain.atomicwork.com"
            required
          />
        </div>

        <div className="form-group">
          <label>Atomicwork API Key</label>
          <input
            type="password"
            name="atomicworkApiKey"
            value={config.atomicworkApiKey}
            onChange={handleChange}
            placeholder="aw_..."
            required
          />
        </div>

        <div className="form-group">
          <label>Azure Client ID</label>
          <input
            type="text"
            name="azureClientId"
            value={config.azureClientId}
            onChange={handleChange}
            placeholder="00000000-0000-0000-0000-000000000000"
            required
          />
        </div>

        <div className="form-group">
          <label>Azure Tenant ID</label>
          <input
            type="text"
            name="azureTenantId"
            value={config.azureTenantId}
            onChange={handleChange}
            placeholder="00000000-0000-0000-0000-000000000000"
            required
          />
        </div>

        <div className="form-group">
          <label>Azure Client Secret</label>
          <input
            type="password"
            name="azureClientSecret"
            value={config.azureClientSecret}
            onChange={handleChange}
            placeholder="••••••••••••"
            required
          />
        </div>

        <button type="submit" disabled={isSaving}>
          {isSaving ? 'Saving...' : 'Update Configuration'}
        </button>
      </form>

      {deployment && (
        <div className="deployment-info">
          <h3>🚀 Deployment Insights</h3>
          <p>Your cloud engine is configured. Use the following details for your Atomicwork webhook:</p>
          
          <label>Webhook URL <span className="copy-badge" onClick={() => copyToClipboard(deployment.webhook_url)}>Copy</span></label>
          <code>{deployment.webhook_url}</code>

          <label>Sample JSON Payload <span className="copy-badge" onClick={() => copyToClipboard(JSON.stringify(deployment.payload_format, null, 2))}>Copy</span></label>
          <pre style={{ margin: '8px 0' }}>
            <code>{JSON.stringify(deployment.payload_format, null, 2)}</code>
          </pre>

          <p style={{ marginTop: '12px', fontSize: '11px', fontStyle: 'italic' }}>
            {deployment.instructions}
          </p>
        </div>
      )}

      <div className="status-indicator">
        <div className={`dot ${status.includes('Online') ? '' : 'error'}`} 
             style={{ backgroundColor: status.includes('Online') ? 'var(--success)' : 'var(--error)',
                      boxShadow: status.includes('Online') ? '0 0 8px var(--success)' : '0 0 8px var(--error)' }}></div>
        <span>{status}</span>
      </div>
    </div>
  )
}

export default App
