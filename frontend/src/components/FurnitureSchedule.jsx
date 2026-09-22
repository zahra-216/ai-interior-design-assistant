import './FurnitureSchedule.css'

export default function FurnitureSchedule({ products, loading }) {
  if (loading) {
    return (
      <div className="schedule">
        <span className="schedule__label">Furniture schedule</span>
        <p className="schedule__status">Finding matching pieces...</p>
      </div>
    )
  }

  if (!products || products.length === 0) {
    return (
      <div className="schedule">
        <span className="schedule__label">Furniture schedule</span>
        <p className="schedule__status">Items will be listed once your layout is ready.</p>
      </div>
    )
  }

  const found = products.filter(p => p.found !== false)
  const missing = products.filter(p => p.found === false)

  return (
    <div className="schedule">
      <span className="schedule__label">Furniture schedule</span>
      <table className="schedule__table">
        <thead>
          <tr>
            <th>Item</th>
            <th>Product</th>
            <th>Retailer</th>
            <th className="schedule__price-col">Price</th>
          </tr>
        </thead>
        <tbody>
          {found.map((p, i) => {
            const qty = p.quantity || 1
            return (
              <tr key={i}>
                <td>
                  {p.item}
                  {qty > 1 && <span className="schedule__qty"> × {qty}</span>}
                </td>
                <td>
                  {p.product_url
                    ? <a href={p.product_url} target="_blank" rel="noreferrer">{p.product_name}</a>
                    : p.product_name}
                  {p.note && <span className="schedule__note">{p.note}</span>}
                </td>
                <td>{p.retailer}</td>
                <td className="schedule__price-col">
                  LKR {(p.price * qty).toLocaleString()}
                  {qty > 1 && <span className="schedule__note">LKR {p.price.toLocaleString()} each</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {missing.length > 0 && (
        <p className="schedule__missing">
          Not in our catalog yet (not included in the total): {missing.map(p => p.item).join(', ')}
        </p>
      )}
    </div>
  )
}
