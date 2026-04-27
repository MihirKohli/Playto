export default function Badge({ label, filled }) {
  return <span className={`badge ${filled ? "filled" : ""}`}>{label}</span>;
}
