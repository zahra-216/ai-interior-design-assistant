import './CostSummary.css'

const lkr = n => `LKR ${Math.round(n).toLocaleString()}`

export default function CostSummary({ cost, loading, proposal, optimizing, onOptimize, onApply, onDismiss }) {
  if (loading) {
    return (
      <div className="cost-summary">
        <p className="cost-summary__status">Calculating total...</p>
      </div>
    )
  }

  if (!cost) {
    return null
  }

  const isOver = cost.budget_status === 'over budget'

  return (
    <div className="cost-summary">
      <div className="cost-summary__row">
        <div className="cost-summary__figure">
          <span className="cost-summary__label">Total</span>
          <span className="cost-summary__amount">{lkr(cost.total_cost)}</span>
        </div>
        <div className="cost-summary__figure">
          <span className="cost-summary__label">Budget</span>
          <span className="cost-summary__amount">{lkr(cost.budget)}</span>
        </div>
        <div className={`cost-summary__status-pill ${isOver ? 'cost-summary__status-pill--over' : ''}`}>
          {cost.budget_status}
        </div>
        {isOver && !proposal && (
          <button className="btn cost-summary__fit" onClick={onOptimize} disabled={optimizing}>
            {optimizing ? 'Finding cheaper options...' : 'Fit to my budget'}
          </button>
        )}
      </div>

      {!proposal && <p className="cost-summary__suggestion">{cost.suggestion}</p>}

      {proposal && (
        <div className="cost-summary__proposal">
          <p className="cost-summary__message">{proposal.message}</p>

          {proposal.optimized_items.length > 0 && (
            <ul className="cost-summary__swaps">
              {proposal.optimized_items.map((s, i) => (
                <li key={i}>
                  <div>
                    <strong>{s.item}{s.quantity > 1 ? ` × ${s.quantity}` : ''}:</strong>{' '}
                    {s.original_product} → {s.product_url
                      ? <a href={s.product_url} target="_blank" rel="noreferrer">{s.optimized_product}</a>
                      : s.optimized_product}{' '}
                    <span className="cost-summary__retailer">({s.retailer})</span>
                  </div>
                  <div className="cost-summary__swap-meta">
                    Saves {lkr(s.saving)}{s.note ? ` · ${s.note}` : ''}
                  </div>
                </li>
              ))}
            </ul>
          )}

          {proposal.suggestions?.length > 0 && (
            <ul className="cost-summary__ideas">
              {proposal.suggestions.map((t, i) => <li key={i}>{t}</li>)}
            </ul>
          )}

          <div className="cost-summary__actions">
            {proposal.optimized_items.length > 0 && (
              <button className="btn" onClick={onApply}>
                Use these ({lkr(proposal.optimized_total)})
              </button>
            )}
            <button className="btn-secondary cost-summary__keep" onClick={onDismiss}>
              Keep my picks
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
