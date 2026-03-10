export default function JsonCard({ title, value, empty = "暂无数据。" }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <p className="section-kicker">Payload</p>
          <h3 className="panel-title">{title}</h3>
        </div>
      </div>
      <div className="json-card">
        <pre>{value ? JSON.stringify(value, null, 2) : empty}</pre>
      </div>
    </section>
  );
}
